# C2 trusted wire contract

Status: preparation with coordinator-accepted identity/cap boundaries; source feasibility and independent admission remain pending. No capability is activated. H24 owns the trusted adapter. A later kernel worker owns the implementation in the approved kernel allowlist.

Contract ID: xswap-independent-v1. Protocol revision: 9. Kernel observation schema: 1. Guest evidence schema: 2. Baseline A is 5e84ca928deeacb4eee656806a003f27d1eca82f. K is 7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad. The future exact candidate C must be frozen before reservation. The [execution brief](C2-execution-brief.md), [validation contract](C2-validation-contract.md) and [coordinator decisions](C2-coordinator-decisions.md) own architecture and acceptance.

## Names, scope and lifetime

Keep the existing /sys/kernel/debug/xswap/typeN file and its metadata counters unchanged. Add a private debugfs directory /sys/kernel/debug/xswap/frontend. It contains:
- typeN: read-only current frontend snapshot, present only for a live XSwap type.
- control: per-open command/response file for cap changes; debug commands exist only with CONFIG_XSWAP_TEST=y.
- events: read-only bounded debug event journal, CONFIG_XSWAP_TEST only.
- completions: read-only bounded terminal snapshots retained after frontend destruction.

These are experiment diagnostics, not a public ABI. Existing type* globbing at the parent remains compatible. No memory.zswap control changes and no new cgroup file are permitted.

Each actual frontend activation attempt receives a monotonically increasing, nonzero u64 generation after assigning its real logical type and before allocating its pool. Generation never repeats within a boot, including failed activation and type reuse. type is the actual logical swp_type; generation is the ownership identity. Pool ID is the same generation because C2 has exactly one immutable pool per frontend. A type path alone cannot identify an object.

An open typeN read must materialize a scalar snapshot while holding a valid device/frontend reference, then release that reference before returning bytes. Later reads from that open file consume the materialized buffer, not a freed pointer. A snapshot captures one sequence and records inflight; arithmetic requiring balance is checked only at quiescent phases with inflight=0. The implementation must not sleep under cluster/index/LRU spinlocks. Final destruction copies scalars into a terminal record after the actual pool-destroy function returns. No post-destroy read dereferences the frontend.

Keep up to 64 unacknowledged terminal records and a 4096-entry journal. Capture is explicitly targeted to the selected key/range/token operation and its required peers; it never records every operation of an 8192-page workload. Refuse a new test window or device creation if its required retained record cannot be reserved; do not overwrite unread evidence. A journal overflow sets lost>0 and invalidates the active subcase. Explicit ack below may remove a terminal record only after the guest has copied it to serial. Normal non-test timing has no per-operation event tracing.

## Scalar snapshot grammar

All records are ASCII, newline-terminated, no trailing fields. Unsigned fields are canonical decimal integers, without signs or leading zeroes except 0. Identifiers use [a-z][a-z0-9_-]{0,63}. No kernel pointers or host paths are exposed. Unknown, duplicate, missing, non-finite or out-of-range fields are rejected by the trusted parser.

A current or terminal record has exactly this envelope:

    XSWAP_FRONTEND_BEGIN schema=1 type=T generation=G pool=G snapshot=S state=active|destroyed|init_failed codec=lzo driver=DRIVER test=0|1
    KEY UNSIGNED_VALUE
    ...
    XSWAP_FRONTEND_END schema=1 type=T generation=G snapshot=S

The fixed key set is:

| Group | Exact keys | Meaning |
| --- | --- | --- |
| Admission | ram_pages, cap_pages, cap_updates, cap_rejects, bypasses, incompressible_rejects, raw_admitted | cap_pages is in actual allocator backing pages; default floor(ram_pages*20/100). raw_admitted must remain zero. |
| Live ownership | entries_live, compressed_live, raw_live, handles_live, index_live, lru_live, stored_bytes, owner_refs, charged_bytes, inflight, store_token_active, store_token_peak, store_retries, retained_folios_live, retained_folio_gets, retained_folio_puts | compressed_live counts only objects with 0 < stored length < PAGE_SIZE. |
| Allocation | pool_backing_pages, peak_backing_pages, allocator_chain_pages, cap_headroom_pages, entry_allocs, entry_frees, handle_allocs, handle_frees, published, retired, rollback_objects | Counters advance at completed named transitions, not requested operations. |
| Generic accounting | charge_calls, charge_ok, charge_fail, charge_injected, charged_total_bytes, uncharge_calls, uncharged_total_bytes | charge_calls counts actual obj_cgroup_charge calls; injected refusal before the call increments only charge_injected. |
| Load | compressed_loads, raw_loads, load_misses, decode_errors | Success follows completed library load; errors are separate from fallback. |
| Physical backing | backing_live, backing_allocs, backing_frees, backing_charge_denials, read_submitted, write_submitted, read_completed, write_completed, read_errors, write_errors | Actual logical-to-physical associations and real BIO completion owners; submission is never completion. |
| Lifecycle | pool_create_ok, pool_destroy_returned, test_windows, events_lost | pool_destroy_returned is set only after the real destructor returns; retained terminal state supplies this field. |

During quiescent published residence, entries_live=compressed_live+raw_live=index_live=lru_live=handles_live, raw_live=raw_admitted=0, store_token_active=0, store_token_peak<=1, and compressed_live <= stored_bytes < compressed_live*PAGE_SIZE when compressed_live>0. charged_bytes=charged_total_bytes-uncharged_total_bytes and ownership references balance the implementation's reviewed per-entry representation. During inflight operations, tentative handles/charges may differ and must be visible rather than mislabeled as published state.

The cap is an admission boundary on published residence. One nonblocking per-device store token spans the complete folio store, all subpage publication and rollback. Actual token acquisition/release drives store_token_active; store_token_peak must be at most one. Contention increments store_retries and returns RETRY with the locked input still authoritative. This serializes write-side admission and its throughput cost belongs in the comparison. New admission must not increase published residence above the active cap; undo an unpublished allocation that would breach that condition. Lowering the cap below existing residence blocks new admissions until usage falls without evicting existing data. allocator_chain_pages is the exact configured zsmalloc maximum chain size M. With observed registered pages B below cap C before each allocation and one token, registered pages are bounded by C+M. A cap decrease with B0 already registered retains a bound max(B0,C+M); cap_headroom_pages is that bound minus C. This describes registered pool pages, including deferred releases still registered by the allocator, and is not an exact instantaneous physical-RAM bound. peak_backing_pages records observed registered-page peaks. A bounded zero-poll occurs only after users and handles are drained. Timeout preserves the actual nonzero value, marks evidence INCOMPLETE and still permits safe real destruction to flush deferred frees; no post-free read fabricates zero. A zero cap returns FALLBACK before compressed or raw publication and increments bypasses. Existing objects remain readable after a cap change. C2 performs no eviction on a cap update.

retained_folios_live=retained_folio_gets-retained_folio_puts counts only the debug preparation's actual extra folio pins, separately from objcg owner_refs. It must be zero at normal phase reset; terminal gets=puts. A pin timeout aborts/reinserts the still-active device before users are killed, rather than waiting behind a device reference owned by the same control operation.

Destroyed state requires every live-ownership field and backing_live to be zero, handle_allocs=handle_frees, charged_total_bytes=uncharged_total_bytes, published=retired, pool_destroy_returned=1 and inflight=0. pool_backing_pages is the last valid pre-destroy observation, not a fabricated read after free; require it to be zero after all handles were freed. An init_failed record reports the exact reserved generation and every successful preceding allocation/unwind, with zero remaining ownership and no guest-eligible frontend.

## Control requests and acknowledgements

Each write is one complete line, at most 512 bytes. Parsing is exact; extra/missing/duplicate words fail with EINVAL. Read from the same open control file returns exactly one response for that write. Unknown generation/type returns ESTALE. Only guest root may write. No control command searches for a process or changes a host resource.

Common-build command:

    cap type=T generation=G pages=P

Success response:

    XSWAP_CONTROL schema=1 command=cap type=T generation=G status=ok pages=P

The guest reads typeN again and checks cap_pages before allocation. The physical regression and disk/zram timing arms use P=0 for C. Compressed arms use the default finite cap. A keeps the existing ZSwap max_pool_percent=20 with observed readback.

Debug-only commands:

    begin type=T generation=G token=U key=K count=N
    arm type=T generation=G token=U point=POINT key=K count=N order=O subpage=I errno=E
    hold type=T generation=G token=U point=POINT key=K count=N timeout_ms=1000
    release type=T generation=G token=U
    end type=T generation=G token=U
    ack generation=G
    ack_events token=U last=L
    cancel_create token=U
    prepare_create token=U point=pool_create errno=ENOMEM
    retain_write type=T generation=G token=U key=K count=1 timeout_ms=1000
    rewrite_retained type=T generation=G token=U key=K pattern_generation=V timeout_ms=1000
    release_retained type=T generation=G token=U key=K

Live-device responses use XSWAP_CONTROL schema=1 command=COMMAND type=T generation=G token=U status=ok plus echoed command-specific fields. prepare_create instead returns XSWAP_CONTROL schema=1 command=prepare_create token=U status=armed, without type or generation. The ticket belongs to that open control file and its creator tgid. The next actual activation by the same tgid while the file remains open consumes it once, assigns the real type and nonzero generation before allocation, and records the real result. cancel_create returns XSWAP_CONTROL schema=1 command=cancel_create token=U status=cancelled and produces no frontend/init-failure snapshot. Closing an unused ticket also cancels it. Other callers cannot consume the ticket.

begin accepts only a quiescent generation with no armed hook and starts one targeted journal window. Its key/count selects the actual operation range. next is allowed only until the first matching store resolves that range. For a large folio, detailed subpage events cover only the selected failure subpage and one preceding witness; op_end carries actual whole-operation allocated/charged/published/retired/rollback totals. Required intersecting peers are also selected. Lifetime counters still cover every operation. A token is a guest-selected nonzero u64 nonce unique within the boot. A fresh begin resets test-window bookkeeping, never lifetime resource counters. Only one arm or hold may be active per generation. count is an exact positive nth matching operation, not a retry count. key is an exact logical offset, or next only for the first store before a PTE can expose an offset; the first matched event resolves next to a concrete key and all later records must agree. order and subpage are exact numeric selectors. First/middle/last large-folio cases use observed input order>0 and I=0, nr_pages/2, nr_pages-1; hooks cannot manufacture order.

Each arm is consumed at most once. A miss, stale generation, timeout or skipped operation is INCOMPLETE. end requires no armed/held hook, no pending operation from its token and zero lost events. release only releases a matching hold; it cannot assert a test outcome. ack removes only a copied terminal record, never a live frontend. ack_events is accepted only after end, after all selected operations finish, and when last exactly matches the closed window. The guest copies the full interval to serial before acknowledging it. A new begin cannot clear an unacknowledged window; gaps/overflow stay invalid.

retain_write arms coordinated debug preparation, bound to the same open control file, token, generation and resolved logical key. The real fallback path takes exactly one extra folio reference immediately before __swap_writeout, after the pageout eligibility check. A real successful original write BIO must complete before rewrite_retained runs. The process-context rewrite waits only with bounded cancelable lifetime rules, locks and revalidates the same real swap-cache folio/key/generation, uptodate state, unmapped state and positive real swapcount, writes the named deterministic data generation, and calls the actual swap_writeout path at the restored nonzero cap. Its evidence requires real compressed publication and no second physical-write completion. It never edits xs_table, a PTE or a counter directly. release_retained, close, cancel, timeout and teardown each use the same exactly-once actual put path. They leave any authoritative data under existing real ownership. Responses echo the selected key and pattern_generation where applicable.

prepare_create is the sole pre-device exception. It binds the control file, caller and token; a generation begins only at actual activation. It cannot simulate a successful pool, alter another caller's create or satisfy a live-generation test.

## Debug event grammar and actual hook locations

The journal read is a non-destructive scalar snapshot:

    XSWAP_EVENTS_BEGIN schema=1 first=F last=L lost=Z
    XSWAP_EVENT schema=1 seq=S token=U type=T generation=G op=Q kind=KIND event=EVENT stage=STAGE key=K count=N order=O subpage=I peer=R result=E length=B owner=H requested_nid=RN actual_node_mask=NM node_pages=NP allocated=A charged=C published=P retired=D rollback=RB physical_type=PT physical_key=PK data_generation=V flags=FLAGS
    ...
    XSWAP_EVENTS_END schema=1 first=F last=L lost=Z

Only selected events advance seq, which increases strictly across the boot; op is a nonzero per-generation operation ID. kind is init, store, load, invalidate, destroy, backing_swapoff or control; stage names the exact reviewed location within that operation. Physical submit/completion direction follows its store/load kind. Absent peer/owner/physical fields are 0; flags is a numeric bitmask defined below. No value is inferred from a later typeN instance. data_generation is zero when not applicable; retained rewrite and its resulting store carry the actual deterministic generation. Control operations never substitute for a store/load completion. The parser requires a complete captured seq interval for each window, lost=0, exact token/type/generation, unique op transitions and complete begin/end pairs.

Events are: op_begin, store_alloc, charge_call, charge_return, publish, detach, release, decode_return, backing_alloc, backing_free, bio_submit, bio_complete, hook_hit, hold_enter, hold_release, overlap, op_end, pool_create_return, pool_destroy_return, retained_folio_get, retained_folio_put, retained_rewrite_begin, retained_rewrite_end, folio_redirty, folio_uptodate, folio_end_writeback, folio_unlock, completion_owner_return. Every event is emitted after observing the named operation or at its explicitly named entry; a request to perform an operation is not an event proving its completion.

owner is a scalar current cgroup inode identity observed through the held objcg in the guest cgroup namespace, never a raw pointer or an inferred stable objcg ID. Reparent/offline observations record the actual current owner before and after the transition; the held objcg may survive while its owner changes. The guest checks those IDs against its actual cgroup and parent inodes. requested_nid is only a request. actual_node_mask/node_pages come from the selected object's real allocator backing pages; affinity/requested nid cannot populate them. Required node phases need nonzero actual backing pages on the intended node. The per-operation allocated/charged/published/retired/rollback fields are actual transition totals, not requested work.

flags bits: 0 folio_locked; 1 folio_uptodate; 2 folio_dirty; 3 folio_writeback; 4 injected; 5 actual_core_call; 6 actual_bio_completion; 7 old_physical_present; 8 compressed_source_preserved; 9 input_authoritative. A set bit must reflect the actual state at that event. result is signed decimal for return/errno or original BIO status; hook_hit reports the injected errno. For completion injection, bio_complete records the original status and an immediately adjacent hook_hit records the injected status for the same op/key/direction before the real completion branch executes.

The exact failpoints are:

| POINT | Real transition and required evidence |
| --- | --- |
| pool_create | The frontend activation calls the real initialization path, consumes a pre-create ticket, refuses before pool creation, and unwinds earlier state. A separate successful create must exercise actual page_compress_create. |
| entry_alloc | Refuse the selected real frontend entry allocation. Prior objects/charges and locked input remain observable; rollback reaches zero tentative ownership. |
| charge | Refuse at the checked generic-charge boundary before the actual core call. hook_hit has injected=1 and actual_core_call=0. Separate charge_call/charge_return events and positive lifetime counters prove real successful core charging. |
| publish | Refuse immediately before selected index publication after a real initialized/charged handle exists. Rollback must free and uncharge it and prior subpages. |
| decode | Inject a terminal -EIO at the real selected compressed load. The existing newer compressed object stays owned; no physical read follows even if old_physical_present=1. |
| bio_write_complete | Change the selected real completed BIO's status once before its existing completion owner handles it. Require observed dirty/writeback-end/lock transfer and recovery after the hook clears. |
| bio_read_complete | Same for a real read completion. Require not-uptodate/unlock and expected failed child fault; never fabricate a successful read. |

Allowed errno values are fixed by point: ENOMEM for pool_create/entry_alloc, ENOMEM for charge, ENOMEM for publish, EIO for decode and the two BIO completion points. The journal distinguishes injected refusal from real core return or storage failure. Completion action events name the actual owner transition in order for the same operation. The observer retains immutable scalar operation metadata before folio_unlock/folio_end_writeback or mempool release can end the accessed object's lifetime. Later completion_owner_return/op_end uses those scalars and cannot dereference the released folio/sio or fabricate final flags from an earlier protected sample. Error write coverage requires actual redirty and end_writeback calls; error read coverage requires actual unlock without an uptodate action. Successful recovery is a separate actual completion.

Hold points are load_after_lookup, store_before_publish, destroy_before_unuse and backing_swapoff_enter. They are permitted only at reviewed sleepable points with no cluster/index/LRU spinlock held. A hold pins every object/device it may use later; it times out after 1000 ms and records failure. No hold is placed inside invalidate_range or a completion callback. Non-sleeping invalidation/completion paths may emit bounded events only. No wait disables watchdogs, scheduler checks or diagnostics.

An overlap is real only when two distinct op_begin/op_end intervals intersect in the journal, their generation/ranges match the prescribed case, and the overlap event names the other still-active op as peer. Merely starting two user-space threads, observing a barrier flag or incrementing an overlap counter is insufficient. A blocked operation may count as an entered kernel operation, but the event must name its exact stage and the eventual result; the report cannot call it simultaneous mutation. Legacy-only pool/offline intervals need actual existing-function entry/return observations bound to the ordinary device epoch and the same test token; independent-frontend events cannot stand in for them. The old-pool release worker can begin only after that pool reaches zero references. The legacy_pool_offline overlap therefore pairs actual old-pool release-worker entry with actual zswap_memcg_offline_cleanup for the named owner and ordinary epoch; separate current-pool ordinary objects and independent objects may remain live. It never claims that a held object from the same old pool overlaps its zero-ref release. The separate legacy event block and exact source placements remain a kernel/capability review item before c-race-common is considered implemented. If a safe hold point or the required same-key overlap cannot exist under the implemented ownership design, the kernel worker must report that feasibility blocker before changing the test.

## Guest serial envelope and source binding

Revision 9 adds these frozen command-line values: bench.contract_id=xswap-independent-v1, bench.source_role=baseline|candidate, bench.source_commit=FULL_SHA, bench.frontend=legacy|independent|physical|mixed, bench.observer=pid_kretprobe_frontend_v2, plus the existing configuration/case/topology values. The host derives role from the build manifest's exact source: baseline_commit for A, reviewed candidate_commit for C. A free-form environment variable cannot select the symbol.

The compression driver receives the same bound arguments from guest-init/bench.sh. Each ordered subcase writes:

    COMPRESS_BEGIN schema=2 contract=xswap-independent-v1 role=ROLE source=SHA case=CASE phase=PHASE frontend=FRONTEND type=T generation=G token=U
    COMPRESS_SNAPSHOT phase=PHASE point=before|effect|after|reset
    [exact copied kernel snapshot or preserved legacy observation block]
    COMPRESS_SNAPSHOT_END phase=PHASE point=POINT
    COMPRESS_RESIDENCY phase=PHASE frontend=FRONTEND pattern=nonzero|zero|incompressible pattern_generation=V pages=N swapped=N nonresident=N type=T key_first=K key_last=K
    [copied complete debug event window where required]
    COMPRESS_DATA phase=PHASE checked_words=N corrupt_words=N completed_faults=N child_signal=N
    COMPRESS_RESET schema=2 case=CASE phase=PHASE status=PASS|FAIL|INCOMPLETE
    COMPRESS_END schema=2 case=CASE phase=PHASE status=PASS|FAIL|INCOMPLETE

Per-phase raw topology is copied without interpretation between COMPRESS_SWAPS phase=PHASE point=before|effect|after|reset and COMPRESS_SWAPS_END phase=PHASE point=POINT; its contents are the complete current /proc/swaps header and rows. Effect topology binds the resident targets; reset must be empty after all owned devices are removed.

Preserved ordinary-frontend evidence is wrapped between COMPRESS_LEGACY_BEGIN epoch=E type=T and a matching COMPRESS_LEGACY_END. Its body is the existing exact schema-1 compression record(s), with the trusted old case mapping, complete counter/data/reset evidence and no invented independent generation. The complete old physical-regression serial body is wrapped in COMPRESS_PHYSICAL_BEGIN / COMPRESS_PHYSICAL_END. Library-unit phases retain the existing COMPRESS_KTAP_BEGIN suite=page_compress / COMPRESS_KTAP_END suite=page_compress block. Wrappers preserve the existing parser's gates.

The parser computes outcomes from raw observations; printed PASS never overrides a missing effect, identity, complete event interval, verified data or reset. Phase order and exact phase set are frozen per trusted group. Duplicated or unknown phases, fields, counters, events or keys fail closed. Snapshots/events are raw kernel output copied unchanged between unambiguous markers. Kernel diagnostics remain independently parsed across the full serial log.

Independent generations must be nonzero kernel generations. A and ordinary legacy ZSwap have no such kernel interface; their wrappers use generation=0 with frontend=legacy and an explicit per-boot swapon epoch in the legacy observation block. That epoch binds observed create/use/destroy order and actual PTE type; it never satisfies an independent generation or teardown gate. This preserves the immutable old anchor while keeping its limitation explicit.

## Required phase sets

The twelve exact boots remain those in the validation contract. Their concrete ordered phases are:

| Group | Phases |
| --- | --- |
| b-regression / c-regression | physical_regression (preserves the existing data/fork/COW/concurrent/live-swapoff outcomes) |
| b-legacy | legacy_roundtrip |
| c-legacy | legacy_roundtrip, legacy_codec_switch, legacy_invalid_codec, legacy_memcg_balance, legacy_memcg_offline, legacy_memcg_limit |
| c-independent | independent_roundtrip, zero_control |
| c-coexistence | xswap_legacy_disabled, xswap_legacy_quota_zero, ordinary_legacy_disabled, ordinary_legacy_quota_zero, both_live |
| c-fallback | cap_bound, incompressible_fallback, physical_fallback |
| c-debug-common | library_unit, legacy_lifecycle, independent_large_folio |
| c-debug-independent | incompressible_control, no_target_retention, swap_charge_denied, init_refusal, entry_refusal, charge_refusal, publish_refusal, rollback_first, rollback_middle, rollback_last, decode_old_backing, write_completion_error, read_completion_error, reused_slot, live_destroy |
| c-numa-independent | independent_node0, independent_node1, live_cpu_hotplug, owner_balance |
| c-race-common | mixed_load_free, legacy_pool_offline, mixed_live_destroy |
| c-race-independent | fault_cow_invalidate, reused_slot_overlap, live_destroy_overlap, backing_swapoff_overlap |

Each phase finishes complete cleanup before the next starts; both_live deliberately keeps both frontends resident within that one phase. Policy, event and codec controls are restored and temporary cgroups removed. Failure or missing reset stops later phases in that boot. Deterministic patterns carry a separate data generation so type/key reuse cannot validate an old occupant.

Positive independent proof requires exclusive logical XSwap with no lower device, nonzero short compressed objects, actual successful generic charge calls with MEMCG=y/ZSWAP=n, nonresident swapped targets of the intended type, successful decoder deltas, verified data and terminal balanced teardown. Zero or incompressible controls prove their distinct route and must not pass this positive predicate. Incompressible fallback and physical regression require cap/raw policy readback, real backing associations and real completion deltas.

decode_old_backing must first observe an older completed physical version, then a newer compressed version of the same logical key. It records actual old_physical_present before injection, terminal fault/SIGBUS, preserved compressed source and zero physical-read delta for that failed load. A merely allocated physical slot cannot substitute for the older completed version. Physical completion-error phases must prove a real request completed and reached the existing owner, including recovery after once-only write injection.

The NUMA group uses a separately cataloged c2-numa2-nehalem-v1 identity with the now runtime-valid C1 CPU/SMP/memory layout (R5 NUMA result SHA-256 7dd104b94dee2b7c0cf769ef5e825ac8d686c8ddd147be81f66f5dfb553ee59a); both actual nodes, Intel CPU0 numeric identity and hotplug/reset remain required. Existing C1 IDs keep their original resolver rules.

## Matched timing observer

The one revision-9 observer is pid_kretprobe_frontend_v2. A maps to symbol zswap_load with success return 0. C maps to xswap_load_folio with success return 0. The driver validates the observed kprobe registration text and bound symbol; there is no symbol fallback. It prints the exact symbol, return predicate, source role, source SHA and contract alongside the existing tracing identity.

Keep r64, one PID filter, 16-KiB trace buffer, CLOCK_MONOTONIC_RAW, 128-MiB compressed target, order-zero policy, fixed sample ordering, the 90-percent eligibility threshold and the existing t0/volatile-touch/t1 interval. Registration/readback/residency/trace parsing stay outside that interval. Exactly one successful return and no dropped/missed event is required per timed target. A uses legacy stored/incompressible observations; C uses its real frontend snapshots. Both require zero raw and fallback traffic. Cap percentage alone does not certify nonbinding residence: recorded cap rejection and physical-fallback deltas must be zero.

## Review questions and limits

The coordinator accepted legacy generation=0 plus observed epoch and the published-residence cap boundary, conditioned on a finite source-reviewed in-flight-store bound and allocator-derived transient headroom before freeze. Cap changes do not evict existing data and this is not a hard total-RAM quota. Cancellation is control bookkeeping, never fabricated init-failure evidence.

The failpoint and overlap names are concrete, but their real-path feasibility remains source-review and runtime work. A hook request, synthetic fixture, successful build or parser PASS cannot establish an exercised failure/overlap. The native adapter must remain incomplete on missing real events. C1 correctness and independent C2 review still gate integration, activation and runtime.


## Raw policy, CPU and ordinary frontend observations

The following direct readbacks complete the guest framing; they never replace actual operation events.

    COMPRESS_POLICY phase=P point=before|effect|after|reset zswap_present=0|1 zswap_enabled=0|1|absent zswap_pool_percent=U|absent zswap_shrinker=0|1|absent zswap_codec=CODEC|absent zswap_quota=U|max|absent swap_quota=U|max|absent cgroup_inode=U parent_inode=U cgroup_errno=0|2 memory_current=U|absent memory_swap_current=U|absent

Read the actual ZSwap parameter and temporary-cgroup files. Only convert observed Y/N to 1/0. With ZSWAP=n, zswap_present=0 and all five ZSwap fields are absent. Successful reset removal is stat ENOENT: cgroup_errno=2, cgroup_inode=0, and removed cgroup values are absent. Module readback remains actual; parent_inode is the actual parent cgroup inode. memory.current is a convergence observation, not byte-exact charge equality.

    COMPRESS_CPU phase=P point=before|offline|online|reset target=N online=LIST

LIST is the exact /sys/devices/system/cpu/online range list. Observe all four points, target 1..3, with real compressed residence across offline/online and original CPU set restored.

    COMPRESS_LEGACY_STATE phase=P point=before|effect|after epoch=E type=T stored_pages=S pool_bytes=B incompressible_pages=I zswpin=ZI zswpout=ZO pswpin=PI pswpout=PO zswap_bytes=ZB zswapped_bytes=ZP owner=H

Use actual ordinary swapped-PTE type, observed swapon epoch, existing debugfs/VM/cgroup counters and actual owner inode. Independent separation requires no legacy storage/decode delta. Ordinary disabled/quota-zero phases require real physical traffic and no legacy store/decode. both_live/mixed race phases require separate ordinary and independent compressed residence and data.

The residency record includes frontend immediately after phase:

    COMPRESS_RESIDENCY phase=P frontend=independent|legacy|physical pattern=nonzero|zero|incompressible pattern_generation=V pages=N swapped=N nonresident=N type=T key_first=K key_last=K

Mixed phases have one record per actual frontend/type, with distinct types. The independent correctness region is 32 MiB (8192 pages); timing remains 128 MiB. Preserved schema-1 and physical-regression workloads retain existing sizes.

Legacy overlap uses a separate test-only journal:

    XSWAP_LEGACY_EVENTS_BEGIN schema=1 token=U epoch=E type=T pool=P owner=H first=F last=L lost=0
    XSWAP_LEGACY_EVENT schema=1 seq=S token=U epoch=E type=T op=Q kind=pool_release|memcg_offline event=op_begin|hold_enter|hold_release|overlap|op_end stage=STAGE pool=P owner=H peer=R result=E
    ...
    XSWAP_LEGACY_EVENTS_END schema=1 token=U epoch=E type=T pool=P owner=H first=F last=L lost=0

pool is a nonzero boot-unique debug lifetime ID, never a pointer/reusable slot. pool_release_enter/pool_release_returned bracket the real zero-ref old-pool worker; memcg_offline_enter/memcg_offline_returned bracket the actual owner's legacy offline cleanup. overlap names the other still-active op. Hold only at the real worker entry without a spinlock. Separate current-pool ordinary and independent objects supply mixed live residence. This cannot claim same-old-pool live-object mutation or replace independent identity.

    legacy_begin type=T epoch=E token=U owner=H
    legacy_hold type=T epoch=E token=U point=pool_release_enter pool=P timeout_ms=1000
    legacy_release type=T epoch=E token=U
    legacy_end type=T epoch=E token=U
    legacy_ack token=U last=L

Responses are XSWAP_CONTROL schema=1 command=COMMAND type=T epoch=E token=U status=ok plus echoed selectors. legacy_begin binds the current ordinary device and actual owner. The old pool is discovered from real codec-switch observer output, not guessed; exact scalar discovery placement remains a kernel implementation-review item. End/ack require no pending operation/loss and copy-before-ack. Close cancels/releases and records failure if it cannot drain.

Both retain_write and rewrite_retained carry timeout_ms=1000; missed real paths are INCOMPLETE and remain counted.


### Legacy pool discovery

The test-only read path /sys/kernel/debug/xswap/frontend/legacy_pool returns exactly one scalar record for the active legacy_begin window:

    XSWAP_LEGACY_POOL schema=1 token=U epoch=E type=T owner=H pool=P codec=CODEC

The kernel obtains P from the actual current pool under its real lifetime protection; IDs are nonzero, boot-unique pool lifetimes. Copy scalars before releasing protection. Guest copies this line unchanged inside:

    COMPRESS_LEGACY_POOL_BEGIN phase=P point=before|switched
    XSWAP_LEGACY_POOL ...
    COMPRESS_LEGACY_POOL_END phase=P point=before|switched

Observe the old current pool while its real entries remain live, switch codec through the real legacy control, observe a distinct current pool/codec, and arm legacy_hold for the observed old pool before retiring those entries. A missing/stale/identical pool observation is INCOMPLETE.

Ordinary epoch is driver-assigned only after observing actual successful swapon, using a nonzero boot-unique phase-token-derived value. legacy_begin verifies that the selected type is currently a live ordinary device and binds that observed epoch/owner for this window. It never turns the epoch into an independent kernel generation. Immutable baseline A uses only the observed epoch and preserved schema-1 evidence; it cannot supply the test-only pool overlap.


### Ordinary store binding and exact control responses

The test-only /sys/kernel/debug/xswap/frontend/legacy_store captures the first matching successful fully initialized ordinary entry/LRU publication under the real folio protection:

    XSWAP_LEGACY_STORE schema=1 token=U epoch=E type=T owner=H pool=P key=K order=O length=B

Copy unchanged inside COMPRESS_LEGACY_STORE_BEGIN phase=P / COMPRESS_LEGACY_STORE_END phase=P. Require 0<B<PAGE_SIZE, the observed old pool and matching type/epoch/owner/token, and a key in the ordinary target range. Retain until end/ack. Never walk a bare xa_load entry from debugfs; legacy index publication precedes some initialization. Both current-pool reads are quiescent around the real codec switch.

Successful responses are exact. K may be next only for begin/arm/hold/retain_write before a real event resolves it; rewrite/release_retained use the concrete key.

    XSWAP_CONTROL schema=1 command=cap type=T generation=G status=ok pages=P
    XSWAP_CONTROL schema=1 command=begin type=T generation=G token=U status=ok key=K count=N
    XSWAP_CONTROL schema=1 command=arm type=T generation=G token=U status=ok point=POINT key=K count=N order=O subpage=I errno=ERRNO
    XSWAP_CONTROL schema=1 command=hold type=T generation=G token=U status=ok point=POINT key=K count=N timeout_ms=1000
    XSWAP_CONTROL schema=1 command=release type=T generation=G token=U status=ok
    XSWAP_CONTROL schema=1 command=retain_write type=T generation=G token=U status=ok key=K count=1 timeout_ms=1000
    XSWAP_CONTROL schema=1 command=rewrite_retained type=T generation=G token=U status=ok key=K pattern_generation=V timeout_ms=1000
    XSWAP_CONTROL schema=1 command=release_retained type=T generation=G token=U status=ok key=K
    XSWAP_CONTROL schema=1 command=end type=T generation=G token=U status=ok last=L
    XSWAP_CONTROL schema=1 command=ack generation=G status=ok
    XSWAP_CONTROL schema=1 command=ack_events token=U status=ok last=L
    XSWAP_CONTROL schema=1 command=prepare_create token=U status=armed
    XSWAP_CONTROL schema=1 command=cancel_create token=U status=cancelled
    XSWAP_CONTROL schema=1 command=legacy_begin type=T epoch=E token=U status=ok owner=H
    XSWAP_CONTROL schema=1 command=legacy_hold type=T epoch=E token=U status=ok point=pool_release_enter pool=P timeout_ms=1000
    XSWAP_CONTROL schema=1 command=legacy_release type=T epoch=E token=U status=ok
    XSWAP_CONTROL schema=1 command=legacy_end type=T epoch=E token=U status=ok last=L
    XSWAP_CONTROL schema=1 command=legacy_ack token=U status=ok last=L

ERRNO is symbolic ENOMEM or EIO exactly as selected. Rejected commands return real errno and no success record; retain actual failure observations. end/ack_events after actual destruction are allowed only on the same open file owning retained generation/window metadata, with no live-device reference or pending selected operation. They include actual destroy op_end/pool_destroy_return. They cannot arm/access a destroyed frontend. ack removes the copied terminal only after its window ends and copied events are acknowledged. Other destroyed-generation commands fail ESTALE. Never resolve a later typeN instance.

For correctness, completed_faults counts successful first touches rechecked swapped and nonresident immediately before touch. Require a positive count and actual decoder delta, the existing 90-percent initial nonresident coverage, and complete data verification; readahead-satisfied touches are verified but not counted as new demand completions. Timing retains exact per-target decoder proof.

Pre-freeze placement correction: the complete incompressible_control, no_target_retention and swap_charge_denied phases now run first in c-debug-independent, retaining all real operation-owner and locked authoritative-input predicates. The non-test independent group keeps positive/zero; the non-test fallback group keeps cap/incompressible physical fallback/physical roundtrip. There are still twelve boots and nine candidate configurations, with no timing test hooks. Retained rewrite is one base page using the coordinator-approved existing word_pattern(0, word, generation): stamp=0xa5c31f7200000001 XOR (generation<<40), word0=stamp, word1=~stamp, later words=0x636f6d7072657373 XOR (generation*0x0101010101010101), all unsigned 64-bit.


### Actual same-key reuse observation

The reused_slot and reused_slot_overlap phases additionally copy one exact guest observation:

    COMPRESS_REUSE phase=P type=T generation=G old_key=K new_key=K old_pattern_generation=V new_pattern_generation=W old_nonresident=1 new_nonresident=1 checked_old_words=512 checked_new_words=512 corrupt_words=0

Each key is obtained from the actual swapped PTE and each nonresident state from mincore before that selected page's verified fault. Both complete base pages must match their actual filled pattern, with 0<V<W. The final residency record uses W. The parser binds the equal observed logical keys to actual same-generation publication, intervening release, and new publication events. A virtual-address match, missing observation or unchanged pattern cannot prove reuse.

### Revision-9 observer isolation

The matched timing observer pins isolation_strategy=mlockall_current_future_target_munlock_v1 and isolation_proof=raw_smaps_v1. After all target/control allocations it calls mlockall(MCL_CURRENT|MCL_FUTURE), then munlock on exactly the 128 MiB target. Success records are:

    COMPRESSED_ISOLATION_SETUP mlockall=0 munlock=0 flags=current_future target_bytes=134217728
    COMPRESSED_ISOLATION_BEGIN phase=P strategy=mlockall_current_future_target_munlock_v1 target_start=U target_bytes=134217728 bytes=N encoding=hex
    [exact bounded /proc/self/smaps bytes encoded in 64-byte hex lines]
    COMPRESSED_ISOLATION_END phase=P locked_mappings=N locked_mapping_bytes=N locked_resident_bytes=N target_mappings=N target_unlocked_bytes=134217728 special_mappings=N inaccessible_mappings=N

Exactly before_reclaim and after_measurement are required, with fewer than 262143 raw bytes each and the same actual target. Replay requires complete contiguous anonymous rw-p target VMAs, no lo/lf, nh present, AnonHugePages=0, and KernelPageSize=MMUPageSize=4 kB. Every accessible private non-target mapping must have lo and no lf. VMA header read/write/execute/shared permission bits must agree exactly with rd/wr/ex/sh VmFlags. Only exact [vvar], [vvar_vclock], [vdso], [vsyscall] mappings are exempt. Accessible shared mappings are rejected. PROT_NONE mappings are counted separately. Derived VMA counts, lengths and summed Locked kB must equal the end record; syscall success alone is insufficient.

The matched observer header is exact:

    COMPRESSED_OBSERVER id=pid_kretprobe_frontend_v2 instrumented=1 clock=monotonic_raw maxactive=64 contract=xswap-independent-v1 role=ROLE source=SHA frontend=FRONTEND symbol=SYMBOL buffer_kb=16 success_return=0

Copy raw setup files in this exact order: kprobe_events, current_tracer, buffer_size_kb, event_filter, event_enable, tracing_on, event_format, trace_options. Each has this envelope and fewer than 65535 bytes:

    COMPRESSED_PROBE_READBACK_BEGIN phase=setup name=NAME bytes=N encoding=hex
    [raw bytes in 64-byte hex lines]
    COMPRESSED_PROBE_READBACK_END name=NAME

The selected registration is exactly r64:swap_next_timing/decode_return SYMBOL ret=$retval:s64. The actual filter is common_pid == PID; the guest checks PID against its real process. The event is decode_return with signed s64 ret at offset 24 and size 8. The instance is nop, 16 KiB, event enabled and tracing on; trace options require context-info, nolatency-format, nohex, nobin, noraw and noverbose.

Candidate timing emits unchanged XSWAP_FRONTEND snapshots inside COMPRESSED_FRONTEND_BEGIN phase=before|stored|after / COMPRESSED_FRONTEND_END phase=P. Its normalized COMPRESSED_STATE maps stored_pages=compressed_live, pool_bytes=pool_backing_pages*4096 and incompressible_pages=raw_live. The host requires stable actual type/generation/pool/driver/cap, increasing snapshot sequence, no raw/cap/fallback/test activity, an initially empty frontend, real short compressed residence, and successful decoder delta covering all exact per-target samples.

Baseline timing retains COMPRESSED_STATE for the same three phases and adds:

    COMPRESSED_LEGACY_CONFIG phase=P codec=lzo max_pool_percent=20 ram_pages=N cap_pages=N shrinker_enabled=0
    COMPRESSED_LEGACY_LIMITS phase=P pool_limit_hit=N written_back_pages=N reject_compress_poor=N

Actual RAM/cap/config stay fixed, pool use stays below the cap, and limit/writeback/poor-compression counters do not advance. Both roles retain exact per-target decode/no-loss/data/order-zero/90-percent/128-MiB evidence. Source selection comes from the retained build and exact command-line identity, never an environment-selected arm. Revision-9 disk/zram timing remains blocked pending its separate actual source/cap-zero adapter; this preparation does not activate the profile.

### Immutable event-operation identity

For every XSWAP_EVENT after op_begin, kind, type, key, count and order must equal that same generation/op's recorded begin values, including op_end and overlap. Count is a positive nth-match selector, never a range length. The logical folio span is [key, key + 2^order), must fit the unsigned 64-bit key space, and overlap is derived from the two actual op_begin spans. Subpage may vary within that fixed folio span. Stage, result, flags, owner, allocation/accounting counters and the other actual transition fields retain their changing semantics. A later event cannot substitute a key, selector or order to manufacture overlap.


### Control selection and the first actual operation

The begin, arm and hold count fields are canonical positive u64 selectors. retain_write accepts exactly count=1 for its single base-page preparation. Except for prepare_create, the first journal op_begin is the opening control's selected operation: generation, type and count must match begin, and an explicit key must match that operation's actual key. A begin with key=next must start at a real store op_begin and resolves once to its actual key. Later arm/hold selectors using next refer to that same resolved key; next is never a wildcard for a later operation. Each arm/hold count must match its actual selected operation. Intersecting peer operations retain their own observed keys, counts and orders, so different folio bases and valid subpage changes remain permitted.
