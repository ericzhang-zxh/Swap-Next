# C2 validation contract: independent XSwap frontend

Status: preparation only. C2 requires complete C1 correctness for the exact predecessor, an independently reviewed C2 source tree, and the missing native capability below. This document creates no profile, protocol, campaign or execution authority. The coordinator owns architecture, activation and acceptance.

Inspected framework: `04bc239db9bb1ddc20832f712461cec0e10de12b`. Comparison anchor **A**: `5e84ca928deeacb4eee656806a003f27d1eca82f`. Implementation predecessor **K**: `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, tree `8b085adc109e3b5467c3de998f11b04517f052a5`. **C** denotes a future exact reviewed C2 candidate; no C2 commit exists in this contract. Read with [C2-execution-brief.md](C2-execution-brief.md), which owns kernel placement and the resource-ownership design.

## Scientific boundary and native lineage

C2 adds one synchronous, per-device XSwap frontend using the shared K1 library. `XSWAP=y,ZSWAP=n` must produce nonzero compressed objects, completed decoder calls, correct data, real generic objcg charges and balanced teardown without lower backing. `memory.zswap.*`, legacy statistics and their guards remain ZSwap-only. Physical fallback is ordinary demand/store fallback; no pressure worker, selected-target migration, new cgroup ABI or automatic baseline advancement belongs here.

Keep native baseline/parent A and carry K's exact patch/ancestry as predecessor provenance in cumulative candidate C. Current `standard_workflow.py:build_coverage()` requires `controller_check.parent == protocol.baseline_commit`; declaring parent K while retaining baseline A is not currently executable. The coordinator can create a candidate from A, carry the exact K changes, then add C2; review both the full A-to-C diff and the K-to-C mechanism. Prior K review covers only its exact tree. The planned timing comparison is cumulative A versus C, not a separately measured marginal K-versus-C gain.

Use a separately versioned trusted contract, proposed ID `xswap-independent-v1` and protocol revision 9. Revision 9 is currently unapproved. Preserve revision 8, its catalog, images, protocols and failed outcomes. Do not enable a profile by merely clearing its `missing_capabilities` list.

## Callback and caller codebook

The pinned source and current `swapin.c:parse_decode_trace()` agree that legacy success is **0**. The execution brief now states the correct semantics; the earlier success-1 assumption must not enter a new observer or fixture.

| Path | Return and folio ownership | Required caller behavior / runtime evidence |
| --- | --- | --- |
| A/K `zswap_load()` | `0`: valid, uptodate, unlocked. `-EIO`: terminal, not uptodate, unlocked. `-ENOENT`: absent, still locked. | Existing `swap_read_folio()` treats every result except `-ENOENT` as handled. No extra unlock and no physical read after terminal error. |
| Proposed `xswap_load_folio()` | `DONE=0`: complete valid data, marked uptodate/dirty before compressed retirement, still locked. `FALLBACK=1`: no compressed object anywhere in the requested range, still locked. Negative errno: preserve compressed source, not uptodate, still locked. | Page-IO unlocks exactly once after DONE or terminal error and reaches delay-accounting finish. Only FALLBACK can look up physical backing. An absent backing association is a failed read, never fabricated data. No asynchronous read RETRY channel exists in C2. |
| Proposed XSwap store | DONE: all subpage objects initialized, charged and published. FALLBACK: no tentative or stale compressed copy for the rewritten range. RETRY: retain the authoritative input. All return locked. | DONE unlocks once, without fabricated writeback. No-target or charge-denied physical fallback returns dirty/`AOP_WRITEPAGE_ACTIVATE`, still locked. Actual physical submission uses the existing completion owner; submission is not success. |

Source anchors: A `mm/zswap.c:1661-1678`; K `mm/zswap.c:1440-1511`, `mm/page_io.c:478-560`, and the caller table in the execution brief. A synchronous direct callback test is insufficient for caller ownership: demand-fault tests must also observe completed faults or the expected child SIGBUS, no hung locked folio, and no stale physical read. Negative errno fixtures must not be mistaken for a successful return-0 event.

## Immutable configurations and case policy

Retain `c1-common`, `c1-legacy`, `c1-debug-v2`, `c1-kcsan`, `c1-noswap` and `c1-no-frontends` input bytes wherever their requirements remain exact. Propose three new inputs, each with its own hash:

| Input | Derivation and mandatory final values |
| --- | --- |
| `c2-independent` | Common input with `SWAP=y,XSWAP=y,ZSWAP=n,PAGE_COMPRESS=y,MEMCG=y,ZSMALLOC=y,CRYPTO_LZO=y`; keep tracing/debugfs, THP and ordinary guest support. NUMA remains disabled. Codec selection must not depend on a ZSwap-default symbol. |
| `c2-debug-independent` | Debug-v2 input with the independent requirements above; retain KASAN, lockdep, fault injection, real NUMA, CPU hotplug, KUnit and `SLUB_TINY=n`. |
| `c2-race-independent` | KCSAN input with the independent requirements above; retain KCSAN and keep KASAN disabled. |

Freeze requested and final configuration, effective codec/driver, test-hook compilation and all forbidden flags. A new test symbol requires a new immutable input, not an edit to a C1 file; it must fit the same nine candidate build configurations. Do not use `MEMCG=n` to satisfy accounting coverage. Positive tests require final `ZSWAP=n`, not a runtime disable switch. The common-input performance arms remain A/common and C/common; record their effective config differences caused by the implementation.

**Physical cases require independent admission bypass.** Existing `bench.sh:setup_swap()` disables only `zswap.enabled` after creating XSwap for disk/zram cases. C would ignore that switch, so those cases could otherwise measure compressed RAM. Freeze a per-device policy that returns FALLBACK without storing compressed or raw objects for physical guards and regression; a zero admission cap is the minimal proposed encoding. Read back the policy before workload allocation and require zero independent stored/load deltas plus real physical I/O. This is C2 path selection, not a C3 eviction policy.

For compressed timing, freeze LZO, the same effective codec/driver, a recorded finite nonbinding admission cap, and zero cap-rejection/raw-store/fallback deltas in both arms. Record cap units and actual allocator backing pages separately from stored-byte charges. A cap in stored bytes cannot silently stand in for an allocator-page cap. Raw-object admission for incompressible correctness data remains a pre-freeze coordinator choice; raw copies never count as decoder evidence.

Single topology remains 4 vCPU / 4096 MiB. The C2 NUMA row must inherit the final valid C1 auxiliary environment under a separately named C2 catalog entry. H15's two-socket layout removed the LLC warning, but R4's default AMD max CPU triggered clocksource fallback; it is not a valid final template. H18 recommends Nehalem-v1,vme=off,enforce=on with one -smp 4,sockets=2,cores=2,threads=1, two 2048-MiB objects and CPUs 0-1/2-3 on nodes 0/1. H19 implementation and fresh C1 runtime are pending. Bind every CPU/SMP/memory/node option and actual boot identity, reject aliases/conflicts and require both actual nodes. Keep existing C1 topology IDs and their historical behavior unchanged; do not widen their resolver for C2.

## Twelve counted correctness boots

Each boot runs ordered subcases with complete reset between them; it is not permission to retry an ambiguous attempt. Existing workload/backend names can remain where their meaning is exact, but the revision-9 group must freeze frontend policy and each phase's topology. Every proposed new subcase below is missing capability until implemented and reviewed.

| # / case | Arm / input | Required exercised path and rejection |
| --- | --- | --- |
| 1 `b-regression` | A / common | Existing disk-backed data, fork/COW, concurrent faults and live swapoff/destroy. Require actual physical targets and completion; reject wrong type, corruption or warnings. |
| 2 `b-legacy` | A / legacy | Nonzero ordinary ZSwap roundtrip, residency outside swap cache, successful decode and drained charges. Reject raw-only/cache-only success. |
| 3 `c-regression` | C / common | Same physical regression with independent admission bypass observed. Require no legacy interception of XSwap and no independent object/decode traffic. |
| 4 `c-legacy` | C / legacy | Legacy roundtrip, old/new codec pools, rejected codec, memcg/offline, zero-quota admission and teardown. Preserve ordinary ZSwap controls and counters. |
| 5 `c-independent` | C / independent | Exclusive no-backing XSwap, actual short compressed objects, nonzero data, per-target residency, successful decoder calls, generic charges and empty teardown. Include all-zero/raw-only negative controls; neither can pass the compressed gate. |
| 6 `c-coexistence` | C / common | Isolated XSwap traffic survives legacy enable/max changes; isolated ordinary traffic obeys them. Then keep objects in both frontends live and decode each intended type without cross-accounting or duplicate ownership. |
| 7 `c-fallback` | C / independent | Bounded admission, incompressible policy, no-target retention, `memory.swap.max=0` denial and successful physical fallback in separate resettable phases. Require authoritative data, real associations/charges and completed I/O. |
| 8 `c-debug-common` | C / debug-v2 | Existing real shared-library KUnit cases plus legacy lifecycle and actual large-folio XSwap input under KASAN/lockdep. Observe input order and C's own subpage publication; legacy mTHP counters cannot certify independent traffic. |
| 9 `c-debug-independent` | C / debug-independent | Targeted pool/entry/charge/publication failures; first/middle/last subpage rollback; decode error over an older physical copy; physical completion error; reused slot and destroy. Require exact failing operation, preserved authority and balanced cleanup. |
| 10 `c-numa-independent` | C / debug-independent | New socket-aligned C2 topology; actual object allocation on both nodes, owner charges, live-object CPU offline/online and balanced teardown. Reject one-node fallback and unobserved hotplug. |
| 11 `c-race-common` | C / KCSAN | Witnessed load/free/coexistence and legacy pool/offline/destroy overlap with both frontends active. User-space simultaneous starts alone are not an observed kernel overlap. |
| 12 `c-race-independent` | C / race-independent | Witnessed fault/COW/invalidate/reused-slot/destroy overlaps plus physical-backing swapoff with real live associations. Bind operations to key/generation and completion; reject old-pattern reads, duplicate retirement or incomplete drain. |

The coexistence workload must prove routing, not infer it from enabled features. One available existing mechanism is to store XSwap targets at priority 100, then add an ordinary swap device at priority 200 and store separate ordinary targets while the old XSwap objects remain live. K `xswap_create():5466-5474,5539-5542` accepts and installs explicit priorities. Freeze the sequence and verify each mapping's PTE type. Test legacy control toggles in separate isolated phases; priority assumptions cannot replace page-state observations.

## Minimal proof and genuine error coverage

Keep the native result/sidecar, counted reservation, source/tree, input/final config, image, current harness, case/topology and raw-log hashes. Add a versioned C2 compression record schema; preserve C1's parser. The existing `correctness_subcases` PASS/reset envelope may carry it, but a summary boolean cannot replace raw evidence.

Every C2 block binds `contract_id`, source role, frontend kind, immutable device generation, logical type/key range, pool/codec identity, case and phase. Require ordered begin/observed-effect/data/reset/end records with unique keys and complete subcases. Candidate fields must be read safely from a pinned snapshot or a retained completion record; reading `typeN` after freeing its frontend is invalid.

Minimum observations are:

- Compressed/raw entry counts and lengths, live handles, allocator backing pages, successful compressed/raw loads, misses/errors and physical associations. A real compressed object has `0 < length < PAGE_SIZE`; lengths equal to PAGE_SIZE and zeromap are separate.
- Target nonzero pattern/generation, swapped PTE type, absent swap cache (`mincore` plus pagemap), successful word checks, and phase-bound decoder deltas. No lower device, association or physical traffic may appear in the independent no-backing case.
- Actual generic charge calls/return values, successful charged/uncharged bytes and held owner references. With `ZSWAP=n`, successful generic charges must be nonzero; ZSwap stub calls cannot satisfy this field. Private counters advance only after the named operation succeeds.
- Exact injection site/target, hit count, operation outcome, folio input order, publication/rollback counts, observed overlap endpoints, and completion outcome where required. A requested failpoint, enabled sanitizer or test name is not an observed failure path.
- Reset drains handles/index/LRU, charged bytes, owner references and pending operations; restores CPU, injection, codec/admission and swap topology; removes temporary cgroups; and records pool destruction without later dereferencing it. Missing reset stops the boot's remaining subcases.

For accounting, K `include/linux/memcontrol.h:1793-1794` exposes generic objcg byte charging, while its ZSwap-specific `!ZSWAP` helpers at `:1945-1974` are no-ops. Byte stock (`mm/memcontrol.c:3607-3647`) delays external convergence, and PF_MEMALLOC can force-charge. Verify exact frontend ownership totals and real calls, plus bounded post-drain memory-control convergence; do not assert a new strict compressed-byte quota or immediate byte-for-byte `memory.current` equality. Physical charges occur in `xswap_backend_alloc():4733-4745`; `memory.swap.max=0` must block new physical backing while allowing bounded compressed residence under this C2 policy.

The missing error adapters must meet these concrete path tests:

| Error | Required real transition |
| --- | --- |
| Allocation/init/publication refusal | Allocate preceding real objects, hit the named failure in the frontend path, observe callback/caller result, and prove every earlier handle/charge is unwound. For large folios, observe a real higher-order input and separately hit first/middle/last subpage. |
| Charge refusal | Distinguish an injected frontend charge-boundary refusal from an actual nonzero `obj_cgroup_charge()` return. Both can test rollback; only the latter proves a natural core failure. Never label an injected refusal as a failed core call. Positive `ZSWAP=n` charging remains mandatory. |
| Decode error | First create an older completed physical version, then a newer compressed version of the same logical key. Inject decode failure, require terminal handling/expected child SIGBUS and no physical read or stale-pattern success. Preserve the compressed source until normal cleanup; unrelated data stays correct. |
| Physical write/read error | Reach the actual existing I/O completion/error owner for a bound request and observe redirty/not-uptodate, writeback end/unlock and data preservation. A rejected submission or a counter-only mock cannot certify completion-error handling. |
| Race/lifetime | Record the specific lookup/publication/detach/reuse overlap with generation/key identities. Require the expected data and one retirement. KCSAN stress without the required overlap remains incomplete for that subcase. |

A minimal implementation may use reviewed, narrow debug-only failpoints in already permitted files, guarded by the immutable debug/race inputs. Their location, lock safety, once-only activation, reset and observer lifetime need exact-tree review. Existing `compression.c` allocation/partial/init/NUMA stubs deliberately return INCOMPLETE; renaming or scheduling them cannot supply C2 coverage. No targeted injector currently proves the new frontend/completion transitions. Preserve the no-new-warning/sanitizer gates; an intentional errno is a separate typed event, not an excuse to ignore diagnostics.

## Ten-build and 120-guest allocation

Nine candidate builds cover common, legacy, independent, debug-common, debug-independent, race-common, race-independent, noswap and no-frontends. Rows 3/6 share common and rows 9/10 share debug-independent; the last two builds have no guest. Final disabled symbols must be inspected.

Admit this allocation only after native exact reuse of both A/common and A/legacy, with unchanged input hashes, source, builder and toolchain. Reuse the builds, then run fresh C2 correctness guests. No historical timing or correctness observation becomes a new sample. Keep builder files unchanged: changing them invalidates these cache identities. If either control build cannot be reused, this complete plan exceeds ten and must stop before execution.

The tenth counted build is an expected-negative A/independent control through the existing isolated full builder. A `mm/Kconfig:125-127` requires ZSWAP for XSWAP, so the requested `ZSWAP=n,XSWAP=y` must finish with ZSWAP disabled and XSWAP absent/disabled. Retain input/final configs, build/image/log hashes and exact source. Successful compilation of this unsupported configuration yields a proposed typed `EXPECTED_UNSUPPORTED_CONFIG` result, never a guest-eligible positive build, candidate failure or positive cache entry. Unexpected ZSWAP restoration, missing final config or unrelated compiler failure is not the expected result.

Current native build coverage has only successful positive admission. Its new negative-control branch must reserve once before execution, preserve interruption/failure spending, verify this exact expectation, and keep positive build reuse/cache and planning states separate. Existing `build.py --probe` checks namespaces only; it is not a Kconfig run and cannot replace the counted negative control. This allocation has no kernel-build retry slot.

| Pool | Planned attempts |
| --- | ---: |
| Probe A/A: four cases times three | 12 |
| Candidate probe: four cases times one | 4 |
| Fast A/A: three cases times ten pairs times two | 60 |
| Fast AB/BA: three cases times four pairs times two | 24 |
| Correctness boots above | 12 |
| Total planned / spare | 112 / 8 |

Proposed caps remain probe=32, fast=88, total=120, builds=10 and wall=64800 seconds, with the unchanged 900-second per-guest timeout. Four spare attempts exist in each guest pool. Grouping many subcases into one boot does not establish that they fit 900 seconds; a timeout stays counted and incomplete. Extra diagnostics consume the same caps. Preserve the original family anchor, predecessor costs and the family's 360-guest/30-build ceiling.

## Paired timing observer

Freeze one observer contract, proposed `pid_kretprobe_frontend_v2`, with trusted arm mapping: **A: zswap_load, success 0; C: xswap_load_folio, DONE 0**. The candidate symbol must be present/probeable in the exact image. Resolve the arm from the reviewed source role, not a free-form environment variable, and record both requested symbol/return predicate and observed registration. No silent fallback to the other symbol is allowed.

Keep the existing measured interval exactly: verify target PTE/type and nonresident mincore and clear trace; take `t0`; perform the volatile first touch; take `t1`; read/validate trace afterward. Keep one PID-filtered return probe, maxactive=64, 16-KiB trace buffer, CLOCK_MONOTONIC_RAW, the same data/order-zero workload, 128-MiB total target, fixed sequential/random ordering and at least 90 percent eligible targets in each half. Each timed target requires exactly one successful return, no missing/lost/duplicate event or missed probe, and correct data. A return 0 can represent a raw load, so also require real compressed-object evidence and zero raw-store/load/fallback deltas.

A and C use the same common input and per-case policy. Keep disk/zram target sizes and sampling unchanged, with explicit independent admission bypass for C. Preserve the four probe cases, three fast cases, primary sequential mean, random-mean and physical guardrails, advisory p99, fresh A/A calibration and existing noise limits. Never pair an old A observation with a new C observation.

This measures instrumented end-to-end first-touch latency. The return probe is inside the fault, while residency checks/trace handling outside the interval can perturb subsequent samples. The two callbacks have different unlock boundaries; A/A variation does not quantify cross-symbol instrumentation bias. Report that unmeasured limitation once and make no inferred uninstrumented or marginal-over-K speedup claim. No alternative observer or post-hoc overhead subtraction is part of this contract.

## Native feasibility, work ownership and activation

Read-only calls against framework `04bc239` accepted the retained revision-8 contract and returned these exact preparation blockers, without writing a protocol or running a workload:

| Proposed change | Current native rejection / required adapter work |
| --- | --- |
| Twelve correctness rows | `C1 requires the complete eight-case correctness matrix`; add an exact C2 catalog with all twelve rows, both disabled builds and the typed negative control. |
| `c2-independent` | `unknown trusted configuration ID`; add the three immutable inputs, final-config rules and C2 topology mapping. |
| Revision 9 | `unapproved protocol revision`; add an explicitly reviewed revision and profile capability branch, preserving revision 8. |
| Arm-specific observer | `revision 8 requires exact per-target compression observer identity`; add the C2 symbol/predicate contract and source-bound proof/cache identity. |

Other necessary source boundaries are concrete: `guest_budget.reservation_identity()` admits named configs/cases only for revision 8; `run.py`/`bench.sh` assume the C1 ZSwap route; `compression.c` reads ZSwap state/charges; `evidence.py` and `swapin.c` bind legacy counters/symbols; `correctness_proof.py` dispatches a matrix only for revision 8; `standard_workflow.py:build_coverage()` only admits positive revision-8 builds; `reference_cache.py` has revision-8/common-input branches. Updating only `validity.py` or a profile would leave an incomplete native path.

The minimal trusted change must carry one exact C2 identity through reservation, runner, raw result, parser replay, full matrix, negative build, current-source hashes, cache admission and durable next-action planning. Extend existing schema-1 attestation envelopes where possible; give new compression records their own version and reject unknown/missing identities. Keep historical parser replay bound to its archived harness. Required adversarial tests include missing/duplicate/wrong source/config/generation, old observer with new source, negative build admitted as positive, skipped injection, fake overlap, one-node fallback, raw/zero/cache-only traffic, physically backed independent traffic, wrong admission policy, failed reset, and warning/sanitizer findings.

Trusted harness ownership covers immutable inputs, catalog, per-case setup/policy, workload/failpoint observation, observer registration and image provenance. Trusted proof/workflow ownership covers protocol validation, reservation, raw replay, matrix completeness, typed negative build, cache and planner states. The kernel candidate owns only the execution brief's approved allowlist; it cannot edit acceptance fixtures or budgets. New guest sources require preparation/provenance and guest-free checks before any counted runtime.

Activation requires complete C1 correctness, an exact reviewed cumulative C2 tree and callback/caller ownership, positive/adversarial native checks, both control-build cache hits, the complete typed negative-control adapter, and frozen configs/codec/admission/observer/resources. All twelve fresh correctness boots and both disabled-build proofs gate timing. A failed required operation blocks dependent C3 work; no profile is activated by this document.

## Remaining acceptance decisions and limits

The coordinator must freeze three concrete choices before implementation is declared ready: (1) the finite cap units/value, physical-case bypass encoding and incompressible raw policy; (2) the exact debug/race failure mechanisms, including whether injected charge refusal plus real positive charging is sufficient or a natural core-charge failure is additionally required, and how actual I/O completion errors are reached; (3) the C2 profile/revision and native lineage mapping, with practical-value thresholds for the cumulative instrumented comparison. No scientific gate may be weakened to make the grouping or ten-build ceiling fit.

C3 separately needs selected-target permissions, writeback-disable semantics, reserve/commit/abort migration, pressure triggering, in-flight demotion/cancellation and reclaim/eviction evidence. C2's ordinary physical fallback, LRU bookkeeping and accounting do not satisfy those C3 gates. The unresolved C3 control policy does not block source preparation of this C2 frontend.

Confidence is high for the pinned API/config constraints, native rejection results and budget arithmetic. Feasibility of the new fault hooks, grouped runtime duration and paired observer remains unmeasured. Only this contract was edited; no code, profile, frozen protocol, campaign state, build or guest was changed or launched.

Coordinator follow-up: [C2 coordinator decisions](C2-coordinator-decisions.md) selects cap/bypass/raw policy, labels injected charge/completion failures, and fixes the cumulative comparison boundary. The H18 auxiliary CPU proposal above remains runtime-unverified.
