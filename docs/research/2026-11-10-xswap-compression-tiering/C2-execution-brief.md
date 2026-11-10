# C2 execution brief: independent XSwap compressed frontend

Status: preparation only; dependent on C1 correctness and a reviewed C2 capability contract.
Owner: coordinator; preparer: tier_migration_research (P2).
Kernel interface/reference tree: `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, tree `8b085adc109e3b5467c3de998f11b04517f052a5`.
Common comparison anchor: `5e84ca928deeacb4eee656806a003f27d1eca82f`.
All kernel line anchors in this brief name the interface/reference commit above.

## Decision and acceptance boundary

Implement one synchronous XSwap frontend in `mm/xswap.c`, with private declarations in `mm/xswap.h`. Select its folio operations through the logical device's `swap_ops` before legacy ZSwap interception. Keep its compressed index, pool, references, object-cgroup ownership and LRU separate from ZSwap. Retain stable logical `swp_entry_t` identity and the existing `xs_table` physical association.

The coordinator's C2 accounting decision is fixed: `memory.zswap.*`, their statistics and their `CONFIG_ZSWAP` guards remain ZSwap-owned. XSwap charges stored bytes with generic `obj_cgroup_charge()` / `obj_cgroup_uncharge()`, keeps explicit objcg references, and exposes private experimental frontend statistics. Existing `memory.swap.max` continues to govern the physical-slot charging path. No new cgroup file, repurposed ZSwap control, pressure demotion, promotion or selected-target migration belongs to C2.

A successful C2 capability result requires actual compressed objects and successful decoder calls for nonzero data with `CONFIG_XSWAP=y, CONFIG_ZSWAP=n`, no lower backing device, correct data, and balanced teardown. Mixed-mode coexistence and ordinary physical fallback are separate tests. The old anchor is an expected negative control for the independent configuration; performance comparisons retain a matched common configuration.

Source-placement confidence is high. The proposed callback/lifetime implementation has medium confidence until exact-tree review and runtime coverage. A changed C1 API or a race/charge failure in the named tests requires revision before dependent execution. [PLAN.md](PLAN.md), [compression.md](compression.md), [migration.md](migration.md) and [validation.md](validation.md) own the wider architecture and capability requirements.

## Exact hook and caller allocation

| Location at the interface commit | C2 change and caller obligation |
| --- | --- |
| `mm/Kconfig:22-25,140-147`; `mm/Makefile` | XSWAP selects PAGE_COMPRESS independently; remove its ZSWAP dependency. Select an available XSwap codec independently of `CONFIG_ZSWAP_COMPRESSOR_DEFAULT`. Add `xswap.o`; retain C1 library CPU-hotplug initialization. |
| `include/linux/swap_ops.h:18-39` | Add optional synchronous `store_folio`, `load_folio` and non-sleeping `invalidate_range` operations with the contract below. Preserve physical `can_merge`, `submit_write`, `submit_read` signatures and explicit physical entries. No migration/completion transaction API is required in C2. |
| `include/linux/swap.h:242-253,283`; new `mm/xswap.h` | Attach an XSwap-private frontend pointer to the XSwap device. Publish declarations for frontend activation/deactivation, operations and the non-sleeping compressed-range query. Keep implementation types private. |
| `mm/swapfile.c:xswap_create():5476-5478,5515-5535` | Remove the `zswap_is_enabled()` creation gate, assign XSwap's operations instead of `swap_bdev_ops`, and replace `zswap_swapon()` for this device with XSwap frontend activation. Complete pool/index/LRU initialization before `enable_swap_info():5542`. Ordinary swapon's `zswap_swapon():5756` remains. |
| `mm/swapfile.c:xswap_create():5551-5560` | Unwind any successfully initialized frontend before cluster metadata is freed. Initialize its pointer before any failure exit; destroy no uninitialized pool and publish no half-ready device. |
| `mm/page_io.c:swap_writeout():204-275` | After architecture preparation and zeromap handling, resolve the logical device from `folio->swap` and invoke its optional store operation before line 238. An XSwap-owned result never falls through to `zswap_store()` or the ZSwap permission check at line 244. Physical fallback still uses `xswap_backend_alloc()` and `__swap_writeout(ctx, folio, phys)`. |
| `mm/page_io.c:swap_read_folio():478-544` | After zeromap, invoke the logical device's optional load operation before line 507. An XSwap miss proceeds only to its physical association lookup, never to `zswap_load()`. A compressed decode error is terminal for this read, including when an older physical association exists. Keep the `finish` delay-accounting exit on every branch. |
| `mm/page_io.c:535-537` | Do not feed XSwap fallback reads into `zswap_folio_swapin()` or legacy ZSwap reclaim feedback. Leave the legacy call on ordinary device traffic. |
| `mm/swapfile.c:swap_range_free():1644-1670` | Route invalidation to the selected frontend, otherwise legacy ZSwap. This precedes the release barrier and slot-usage decrement. The caller can hold a cluster spinlock; index detach and normal handle/charge release must not sleep. |
| `mm/swapfile.c:__swapoff():4090-4152` | Keep frontend reads available through `try_to_unuse()`. On its failure, restore the active device with its frontend intact. Only after successful unuse, device-user/RCU drain and work flushing replace the XSwap branch of `zswap_swapoff()` with frontend teardown, before descriptor/cluster unmap. Keep ordinary ZSwap teardown. |
| `mm/swapfile.c:folio_alloc_swap():2115-2123`; fast/slow allocator gates at `1714-1717,1742-1747` | Remove XSwap admission's dependence on `obj_cgroup_may_zswap()`. Name any retained advisory gate for XSwap readiness, not ZSwap permission. `memory.zswap.max=0` must not silently disable this independent frontend. Actual byte charging remains mandatory at object publication. |
| `mm/memcontrol.c:mem_cgroup_get_nr_swap_pages():6131-6146` | Replace the XSwap virtual-capacity dependency on `zswap_is_enabled()` / `mem_cgroup_may_zswap()`. Report available XSwap capability under the C2 policy, with actual memory and physical-slot charges enforced at their real points. This advisory margin is not a compressed-memory reservation. |
| `mm/swap_state.c:__swap_cache_add_check():210-217`; `mm/swapfile.c:xswap_check_backing():4532-4555` | Keep compressed/mixed ranges on order-zero read allocation. A non-sleeping whole-range compressed-index query must also exclude ranges whose physical mapping is still present but whose latest data is compressed. This is the justified `swap_state.c` edit; no readahead or unrelated swap-in tuning. |
| `mm/memcontrol.c:mem_cgroup_css_offline():4458-4478` | Existing objcg reparenting remains authoritative. Add no XSwap offline hook merely by analogy with ZSwap's shrinker cursor. If the implementation retains a raw memcg pointer or per-memcg LRU state, it must supply and review its actual offline/reparent path before use. |

The ordinary-device path has no new frontend callbacks and retains ZSwap's existing store/load/unlock semantics. Select a frontend by the logical device, not `ctx->sis`: the latter describes an existing physical batch and can be unset or refer to a different physical device (`page_io.c:355-375`). A successful RAM operation must neither overwrite nor flush that unrelated pending batch.

## Folio result and completion contract

Use an `int` result with named nonnegative statuses, for example `DONE=0`, `FALLBACK=1`, `RETRY=2`, and negative errno for a terminal error. The names are local implementation choices; the meanings and ownership below are required. Both new callbacks are synchronous, may sleep for codec completion, and return with the folio locked on every outcome. They never start/end folio writeback, unlock a folio, allocate a swap I/O batch, or submit physical I/O.

| Result | Store callback and `swap_writeout()` | Load callback and `swap_read_folio()` |
| --- | --- | --- |
| DONE | Every base-page object for the folio is initialized, charged and published. Callback returns locked; page_io unlocks once and returns success. No PG_writeback is fabricated for RAM storage. | Whole requested content is valid. While locked, the callback marks the folio uptodate and dirty before retiring the compressed object: the swap-cache folio becomes authoritative. Callback returns locked; page_io unlocks once and reaches `finish`. |
| FALLBACK | All tentative objects/charges and stale compressed copies for this rewritten range have been removed. The locked input folio is authoritative. Page_io tries physical allocation; no target/charge returns dirty + `AOP_WRITEPAGE_ACTIVATE`, still locked. A physical target goes directly to `__swap_writeout()` using its explicit physical entry. | No current compressed object exists anywhere in the requested range. Callback leaves folio contents and lock alone. Page_io uses the physical association; a missing association is a failed read, never zero data or success. |
| RETRY | Temporary refusal with no published new object; the locked input remains authoritative. Page_io marks dirty and returns `AOP_WRITEPAGE_ACTIVATE`, still locked, without spinning or trying ZSwap. | Not a permitted C2 outcome. The current function returns `void` and has no retry channel to its callers. With no migration worker in C2, resolve synchronously to DONE, FALLBACK or error. Any design needing read retry requires an explicit caller/API revision before implementation. |
| Negative error | Undo tentative state and preserve/redirty the input. Page_io unlocks once and returns the error; it does not label it a store or silently use an older compressed/physical copy. | Preserve the compressed source, leave the folio not uptodate, unlock once and reach `finish`. Never downgrade decode failure to a cache miss and read a stale physical copy. |

`mm/vmscan.c:729-747` already treats `AOP_WRITEPAGE_ACTIVATE` as the locked-folio retain/reactivate result. No vmscan edit is needed. A physical write transfers protection through `__swap_writeout():395-412` from folio lock to PG_writeback; `swap_write_end():547-560` redirties on actual completion failure and ends writeback. Physical read completion marks uptodate only on success and unlocks in `swap_read_end():595-614`. Preserve these owners and do not treat submission as completion.

The new RAM callbacks' locked-return contract deliberately differs from legacy `zswap_load()`, which returns integer 0 on success and -EIO on a terminal decode/range failure, with the folio unlocked in both cases; -ENOENT retains the lock for physical fallback (`mm/zswap.c:1440-1454,1493-1511`). The existing caller continues physical fallback only for -ENOENT (`mm/page_io.c:507-508`). The dispatch branches must not share an unconditional unlock after both APIs. Read callers to check are `swap_cache_read_folio():747`, `swapin_sync():789-790` and `xswap_unuse_rmap():3549`.

## State, publication and release

For the first candidate, prefer one independently created pool per XSwap device with a fixed available codec and finite admission cap recorded by the test. Match the actual codec/cap in the common-config comparison. Dynamic XSwap codec switching is not required to establish independence. C1's separate library lifecycle coverage remains required.

| Resource | Owner and protection | Publication/release rule |
| --- | --- | --- |
| Frontend and library pool | XSwap device; existing device-user lifetime plus locked swap-cache/entry lifetime during synchronous I/O. Any observer whose lifetime escapes that call needs its own documented pin. | Fully initialize before device enable. Drain users, pending releases and objects before `page_compress_destroy()`. Do not resolve this pool through ZSwap's registry. |
| Compressed entry/handle | XSwap's index entry, with handle, stored length, logical key, objcg ownership and LRU membership. A per-device immutable pool avoids an extra pool pointer/refcount on every object. | Obtain successful library result, charge and metadata first; publish index next; expose on LRU last. Each published handle is freed once. No library-level object wrapper/refcount is added. |
| Logical entry | Existing swap references and swap-cache association. | Keep `folio->swap` and PTE identity unchanged. Revalidate any state looked up before sleeping work. Final invalidation erases lookup reachability before reuse. |
| LRU | Frontend-owned intrusive list and lock; node and held objcg identify residency. | C2 tracks membership/coldness but registers no pressure shrinker or eviction worker. Do not cache an unpinned memcg pointer; objcg reparenting changes current owner. |
| Physical association | Existing `xs_table`, reverse map and charge protocol. | Retain physical allocation/fallback helpers and logical-before-physical lock order. A stored compressed version is authoritative over an older physical association. No reserve/commit/abort migration API is added in C2. |

The shared API is already concrete: `page_compress_store()` and `_store_raw()` produce one handle/length; `page_compress_load()` is non-consuming; `free()` consumes the handle; `backing_pages()` reports allocator pages (`include/linux/page_compress.h:12-52`). The frontend decides raw admission. If raw fallback is admitted, charge its full PAGE_SIZE length and count it separately; `length == PAGE_SIZE` is a raw copy, not decoder evidence. A codec failure with permitted raw fallback and an allocation failure are distinct outcomes. The library can sleep even with nonblocking allocation flags.

Large stores may remain base-page loops. On any subpage failure, remove every newly installed or stale compressed entry for the entire rewritten folio before fallback/retry; the original locked folio remains the valid copy. Test first/middle/last subpage failure. A load error preserves its compressed source. The whole-range query prevents higher-order physical reads from bypassing a newer compressed subpage. The order-zero load then has one unambiguous owner.

Index queries used under a cluster lock cannot take a sleepable lock or decode. Define lock ordering for cluster, index and LRU locks; never hold an index/LRU spinlock across compression, memory charge, device waits or pool destruction. Invalidation must detach synchronously before the swap-range release barrier. If any required final free is sleepable, move only that retirement to a preallocated/deferred path that pins its frontend and is drained at teardown; do not defer the index erase, allocate a work item under the cluster lock, or let delayed cleanup erase a reused key. Source inspection should first determine whether existing non-sleeping `page_compress_free()` and generic uncharge suffice.

Do not free frontend state at initial swap-list removal. `try_to_unuse()` needs it to recover live data, and failed swapoff reinserts the device (`swapfile.c:4104-4113`). On successful teardown, require empty index/LRU, zero live handles and balanced charged bytes before the pool is destroyed; a pool backing snapshot and post-destroy completion record must still be observable without dereferencing freed state.

## Accounting implementation and exact limits

`obj_cgroup_charge_zswap()`, `_uncharge_zswap()`, `obj_cgroup_may_zswap()` and `mem_cgroup_zswap_writeback_enabled()` are unsuitable XSwap dependencies. Under `MEMCG && !ZSWAP`, their header variants are no-ops or always true (`include/linux/memcontrol.h:1945-1974`). Their concrete implementations and the `zswap_max` / `zswap_writeback` fields are also ZSwap-guarded. Widening only a prototype or retaining those stubs cannot establish independent accounting.

Implement XSwap's small charge/uncharge wrappers under CONFIG_MEMCG using the already generic declarations at `include/linux/memcontrol.h:1793-1794`. A legitimate `!MEMCG` build can omit accounting; `!ZSWAP` cannot. Avoid adding a second generic compression-accounting subsystem when the existing byte-charge primitive is enough.

1. Hold the objcg acquired from the locked input folio. Retain one ownership reference for every published entry or use an explicitly balanced frontend owner representation.
2. Compress/store while the input remains authoritative. Before index/LRU publication, charge the returned stored length with reclaim-safe flags and check the return value. No frontend success counter precedes successful publication.
3. On charge/publication failure, free the uncommitted handle, undo any successful charge, release references and follow the declared fallback/retry/error path. A later large-folio failure reverses all earlier subpage ownership.
4. Final entry retirement uncharges exactly its recorded length and puts its objcg once. Keep compressed bytes, raw bytes, metadata, codec contexts and allocator backing pages distinct. A byte charge is not an allocator-fragmentation measurement.
5. Keep XSwap events in its private statistics; do not increment MEMCG_ZSWAP_B, MEMCG_ZSWAPPED, ZSWPOUT/ZSWPIN or ZSwap-specific mTHP counters for this independent frontend.

Generic charging has two source-level qualifications that the tests must respect. Byte stock can satisfy a charge or defer observable uncharge (`memcontrol.c:3607-3647`), so sample after workload drain and validate frontend charge/uncharge totals as well as memory-control convergence. The normal memcg core force-charges a real PF_MEMALLOC reclaim caller after limits are hit (`:2741-2748,2832-2840`); preserve that core behavior and never set PF_MEMALLOC or assume forced success in an ordinary worker. This policy supplies real accounting and error handling, not a strict per-frontend compressed-byte quota.

The physical-slot coverage is exact: `folio_alloc_swap():2155-2170` records XSwap's owner but does not charge physical swap at logical allocation; `xswap_backend_alloc():4733-4745` charges when acquiring real backing and rolls the reservation back if the charge fails. `xswap_backend_free():4820-4823` and final slot release reverse it. `memory.swap.max=0` therefore allows the bounded compressed-resident capability while rejecting a new physical fallback for that owner. It is not a compressed-byte limit.

C2 has no independent writeback-disable control. `memory.zswap.writeback=0` remains a ZSwap setting and does not control XSwap fallback. A C3 permission contract must resolve its own selected-target/writeback-disable requirement before demotion is implemented; adding or reinterpreting cgroup controls would require a new explicit scope decision. This is a C3 gate, not a reason to block the chosen C2 frontend/accounting work.

## Minimal observability and negative controls

Use private experiment statistics with a device-creation generation so destruction/recreation cannot be mistaken for one continuous instance. A debugfs read or final teardown record must pin or snapshot valid state; an open file must not later dereference a freed frontend. Do not use the existing `typeN` pathname alone as object identity.

| Evidence | Minimum observable / cross-check |
| --- | --- |
| Real storage | Live compressed object count, raw object count, sum of stored lengths, entry count and `page_compress_backing_pages()`. For compressed proof require nonzero objects with `0 < length < PAGE_SIZE`; raw copies and zeromap are separate. |
| Real decode | Successful compressed decoder loads separately from raw loads, misses and decode failures. Count after successful library completion. Demand-fault data verification and phase-bound counter deltas connect these operations to the tested pages. |
| Independence | Final linked config and kernel identity, frontend kind/codec/pool identity, no legacy ZSwap state for the XSwap type. In mixed mode, XSwap-only traffic leaves legacy counters unchanged; ordinary-device traffic still exercises legacy ZSwap. |
| No-backing topology | Actual active swap devices and physical-allocation/fallback counters show no lower device or physical residency for the independent case. Logical nonzero swap entries, resident-object snapshots and demand decode hits exclude zero-only or swap-cache-only success. |
| Charge/teardown | Charge attempts/failures, successful charged and uncharged bytes, live objcg-owned entries, live/deferred-operation count, empty index/LRU and completed pool destruction for the same generation. After freeing/offlining the workload, obtain a final snapshot/completion record and memory-control readback. |
| Physical fallback | Explicit separate topology, allocated physical association and data roundtrip, including write failure and retry. Existing actual I/O completion semantics remain authoritative; a submit count alone is insufficient. |

The trusted observer/parser must bind these fields to exact source/config/image, operation phases and the counted attempt. Candidate counters are cross-checked against topology, data and page-state observations; a self-reported `independent=true` is insufficient. The capability implementer owns the parser/workload changes, not the kernel candidate worker.

Required negative controls before activating C2's profile:

- Old anchor in the independent config is the expected unsupported/build-configuration control; an unexpected restored ZSWAP=y fails identity validation.
- All-zero data cannot pass compressed residency: zeromap can serve it before either frontend. An all-raw incompressible run cannot pass decoder evidence either.
- Physically backed, swap-cache-only, zero-object, zero-decoder, wrong-generation and missing/partial teardown records fail the independent proof.
- With both frontends compiled, changing legacy `zswap.enabled` leaves XSwap ownership operational. Re-enabling it does not duplicate storage/accounting. `memory.zswap.max=0` remains a legacy-only restriction under the selected C2 contract.
- Memory-charge, entry allocation, index publication and first/middle/last subpage failures leave no orphan handles/charges, no stale readable entry and no permanently locked folio. Exercise no-backing retention and physical fallback separately.
- Decode failure must not read an older physical copy. Slot reuse must return the new pattern, never a previous occupant's data.
- Real concurrent fault/COW/free, memcg offline, XSwap destroy and physical-backing swapoff preserve data and balance; sanitizer-bound evidence covers changed paths. Large-folio allocation/order and the mixed compressed/physical range must be observed, not inferred from THP=y.
- `MEMCG=y,ZSWAP=n` must show nonzero successful byte charges and balanced uncharges. `MEMCG=n` is a distinct configuration, not a substitute for accounting proof.

Timing remains blocked on C1 correctness and the complete C2 correctness/configuration proof. The compressed-resident timing case additionally requires the frozen residency/first-touch validity rule from validation.md; aggregate traffic somewhere in the guest cannot certify its timed samples.

## File allocation and implementation order

The K1 tree changes seven files against the common anchor: `include/linux/cpuhotplug.h`, `include/linux/page_compress.h`, `mm/Kconfig`, `mm/Makefile`, `mm/page_compress.c`, `mm/page_compress_test.c` and `mm/zswap.c`. Carry their reviewed provenance into C2; do not reopen the immutable K2 review or rewrite C1 evidence.

| Allocation | Files / constraint |
| --- | --- |
| New frontend | Add `mm/xswap.c`, `mm/xswap.h`. |
| Required C2 integration | Modify `mm/swapfile.c`, `mm/page_io.c`, `mm/swap.h`, `include/linux/swap.h`, `include/linux/swap_ops.h`, `mm/memcontrol.c`; revise existing C1 `mm/Kconfig`, `mm/Makefile`. |
| Narrow correctness integration | `mm/swap_state.c` only for the whole-range compressed/large-folio eligibility check. `include/linux/memcontrol.h` only for a necessary internal declaration/guard, without widening ZSwap control semantics. `include/linux/zswap.h` is permitted by PLAN but need not change. |
| Focused kernel/selftest support | Reuse `mm/page_compress_test.c` where applicable; the already named `tools/testing/selftests/mm/swap_next_compression.c` and its Makefile entry can host a focused test if selected by the frozen scope. Do not add a new test filename implicitly. |
| Outside candidate scope | Trusted profile/protocol/config/workload/parser files; `mm/vmscan.c`; crypto or zsmalloc internals; new cgroup files, public VM-event IDs, compressed-disk format or migration/promotion code. |

This allocation can fit the PLAN estimate of 20 cumulative files / 6000 changed lines, including optional header and selftest slots. The coordinator must freeze the actual allowlist and limits in C2's own contract; this brief installs no profile and edits no protocol.

Recommended sequence after the dependency gate:

1. Establish C1 correctness on its final exact tree, resolve applicable vetoes, and finish C2's independently reviewed trusted capability/config/negative-control preparation. Preserve anchor comparison and predecessor provenance.
2. Create only the controller-owned C2 candidate worktree allowed by the phase contract. Add independent Kconfig/build selection, private state and activation/unwind/teardown skeleton; leave the frozen `linux/` checkout untouched.
3. Implement object publication, generic charges, partial-folio rollback, non-sleeping invalidation and frontend lifetime together. Give each failure edge an owner and exact inverse before wiring runtime entry points.
4. Wire device-selected store/load, physical fallback and the two admission/margin callers as one coherent change. Add the large-folio range check. Keep legacy dispatch/lifecycle and physical completion separate.
5. Add generation-bound observability and focused deterministic failure controls through the approved capability design. Review the complete cumulative diff, lock order and every callback outcome against the ownership tables.
6. Run only the phase contract's immutable builds and counted correctness/config/debug cases. Failed C1/C2 correctness blocks dependent execution. Performance screening follows only after the trusted capability proof passes; C3 remains separate.

## Limitations and remaining decisions

This P2 artifact contains no implementation, build, guest result, profile activation or performance conclusion. It does not change K2-review.md. Source and interface placement were verified over SSH on the stated K1 tree; runtime feasibility remains unmeasured.

No further public-control decision is required for the coordinator's chosen C2 scope. Three implementation checks can still require a revised brief before execution: a necessary asynchronous read retry, a sleeping invalidation cleanup that cannot fit the drain contract, or source/profile growth outside the enumerated files. The C3 writeback/permission contract remains explicitly unresolved for that later phase.
