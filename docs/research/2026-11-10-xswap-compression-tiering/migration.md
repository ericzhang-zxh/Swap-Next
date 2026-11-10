# R2: Swap operations, migration, and pressure integration

Status: research complete; proposed design only.
Researcher: tier_migration_research.
Source reference: `5e84ca928deeacb4eee656806a003f27d1eca82f`.
Repository reference at board creation: `5f0d57e3fe365db15878c5ca674cccc8558f36a5`.
No source edits, kernel builds, guests, controller changes, or experiment launches were performed.

## Judgment

Build on XSwap's existing stable logical swap identity and physical reverse map. First give XSwap its own compressed-store frontend and operations; then move RAM-to-SSD demotion out of ZSwap while preserving protected swap-cache staging. A registered memcg/NUMA-aware shrinker is a sufficient initial memory-pressure entry point. A new hook in `mm/vmscan.c` is not inherently required.

The initial RAM-to-SSD implementation is a meaningful demotion mechanism. Full physical-tier replacement and promotion additionally require separate destination reservation, explicit completion, commit/abort, and accounting semantics. They should not be claimed from the current fallback allocator or a writeback counter.

Confidence: high for the source findings below; medium for the proposed decomposition until exact-tree implementation and correctness testing. The decomposition would change if the smallest implementation required duplicated ownership machinery or the new trusted tests exposed a lifetime/accounting dependency that cannot remain in the frontend.

## Existing behavior and exact evidence

All source anchors below refer to the stated kernel reference, accessed with `git show`.

| Finding | Evidence |
| --- | --- |
| `swap_ops` currently covers batching and submission, without migration or lifecycle callbacks. | `include/linux/swap_ops.h:18-39`: context, flags, `can_merge`, `submit_write`, `submit_read`. |
| XSwap's actual compression bypasses its operations. | `mm/page_io.c:238-269`: `zswap_store` first, then physical fallback. `:507-537`: `zswap_load` first, then physical lookup. |
| The XSwap device currently assigns block operations only to obtain flags. | `mm/swapfile.c:5507-5535`: no bdev, synchronous flag, explicit comment that I/O callbacks never run, `zswap_swapon`. |
| Logical entry and physical address are separate already. | `mm/swapfile.c:4517-4525`: `xs_table` physical entry. `:4687-4700`: physical-to-logical reverse map. `mm/page_io.c:355-412`: explicit I/O entry separate from `folio->swap`. |
| The existing allocator chooses a non-XSwap device by swap priority, respecting NOFS restrictions. | `mm/swapfile.c:4650-4684`. This is fallback selection, not a generic directed tier graph. |
| Physical allocation combines reservation, memcg charge, mapping publication, and reverse-map installation. | `mm/swapfile.c:4705-4762`. Replacing an existing physical location needs a separate transaction; this function cannot be called unchanged as a generic SSD A-to-B move. |
| Physical ownership must be checked when releasing a recycled slot. | `mm/swapfile.c:3273-3313`. Logical cluster lock precedes physical cluster lock in release (`:3349-3375`). |
| Current writeback reserves a destination and transfers data authority to a protected full folio before freeing the compressed object. | `mm/zswap.c:1018-1099`. The compressed object is freed at `:1077`, before I/O submission, with the folio lock and then PG_writeback protecting staging. |
| A failed write redirties the authoritative staging folio. | `mm/page_io.c:547-560`. Submission success is not completion success or net RAM reclamation. |
| Existing swapoff brings a physical-backed XSwap entry into swap cache before unlinking the physical location. | `mm/swapfile.c:3478-3597`. It pins the owning device, serializes descriptor lifetime, waits for writeback, validates data, and marks the folio dirty. |
| Compressed lookup and release are still tied directly to ZSwap lifecycle. | `mm/swapfile.c:1644-1650`, `:4143-4152`, `:5533-5535`, `:5802-5803`. |
| A large-folio physical read requires same-device contiguous backing; compressed entries currently fall back to order zero. | `mm/swapfile.c:4528-4555`. |
| ZSwap already receives memcg/NUMA-aware pressure callbacks and constrains reclaim by GFP context. | `mm/zswap.c:1226-1269`, `:1322-1334`. Reclaim estimation uses actual compressed backing relative to stored pages (`:1271-1319`). |
| Current memcg helpers have ZSwap-specific semantics that cannot simply be reused for an independent frontend. | `mm/memcontrol.c:6396-6417` expects PF_MEMALLOC charging; `:6449-6453` allows writeback whenever ZSwap is disabled. `include/linux/memcontrol.h:1945-1973` has no-op/always-true !ZSWAP stubs. |
| Zero-filled roundtrip does not establish compression. | `mm/page_io.c:226-228` uses zeromap before either compression or backend dispatch. |

The original explicit-I/O-entry rationale is retained in the [2026-09-20 RFC](https://marc.info/?l=linux-mm&m=178988870746656&w=3). The [ZSwap documentation](https://docs.kernel.org/admin-guide/mm/zswap.html) describes its compressed cache, object handles and pressure-driven writeback; exact implementation claims above remain pinned to the project reference.

Imported series provenance lives in `campaigns/_unassigned/patches/xswap-reference/manifest.json` and `xswap-phase3/manifest.json`, including [Phase I](https://patchew.org/linux/20261003003136.750633-1-hebaoquan@kylinos.cn/mbox), [Phase II](https://ci.syzbot.org/series/01f881d5-45ec-487a-95ef-89aed31ae30c), and [Phase III](https://patchew.org/linux/20261003011111.1003090-1-hebaoquan@kylinos.cn/mbox). They establish provenance, not new runtime coverage.

## Responsibility boundaries

| Layer | Owns | Does not own |
| --- | --- | --- |
| Shared compression library | Codec contexts, compressed-pool operations, store/load/free of handles, measured pool footprint. | Logical swap identities, physical destinations, LRU victim choice, migration transactions, frontend admission policy. |
| XSwap compressed frontend | Its entry index and pool lifetime, logical entry validity, compressed-object ownership, per-memcg/node residency and coldness. | Another frontend's index or a global mandatory shared pool. |
| Backend operations | Concrete read/write/invalidate/lifecycle behavior and I/O completion result. | Global tier ranking or when memory pressure warrants migration. |
| XSwap migration core | Pinning, destination reservation, staging, revalidation, commit/abort, reverse-map and charge transitions. | Compressor internals or a compulsory new user-space daemon. |
| Tier policy/reclaim adapter | Eligible destination, victim selection, budgets, hysteresis, permissions and pressure response. | Reimplementing data movement for every backend pair. |

Peer agreement with R1: library load is non-consuming; successful store transfers a handle to its frontend; free consumes that handle. The frontend holds a valid pool and entry through existing locks/revalidation or references. The library need not add per-object refcounts or know a `swp_entry_t`. No migration API belongs inside the compression library.

## Minimal operations change

XSwap's device-selected operations must take responsibility before the legacy unconditional ZSwap interception. Otherwise a nominal XSwap ops path still depends on ZSwap, or objects can be compressed twice.

The coordinator should choose the exact operation signatures after implementation review. The minimal responsibilities are:

- Per-folio store/load entry points with unambiguous handled/retry/error outcomes and explicit folio-lock/writeback ownership.
- Slot-range invalidation before reuse, with a non-sleeping caller contract where the cluster lock is held; defer cleanup that can sleep.
- Activation/teardown that creates frontend state, stops pressure work, drains in-flight operations, and waits for references before descriptor unmap.
- Existing physical `can_merge/submit_read/submit_write` support, retaining the explicit physical entry.

A synchronous per-folio operation avoids allocating a bio-style batch merely to compress RAM. Implementing RAM through the existing batched submit interface is the simpler API alternative, but its mempool/batch/completion overhead must be measured. This is a suitable bounded C2 comparison only after one correct independent path exists; it is not a reason to implement two unvalidated paths at once.

Do not add one backend-specific `migrate_to_every_other_backend()` callback. Keep the cross-backend transaction in XSwap and use operations for backend mechanisms. A later generic migration completion hook needs an operation cookie and actual success/failure result; today's void submit callbacks and private completion helper do not expose a commit/abort result.

## Proposed state transitions

### First RAM-to-SSD demotion

1. Select a cold compressed entry under its frontend LRU lock. Copy stable identifying information; do not dereference the original entry after dropping protection.
2. Acquire the owning swap-device reference and allocate/lock a swap-cache staging folio for the logical entry. A concurrent fault can win; stop/retry without manufacturing a second owner.
3. Reload/revalidate the compressed entry identity after the sleeping allocation. Ensure destination eligibility, memcg permission, GFP/NOFS/NOIO constraints and device liveness.
4. Reserve the physical destination and its required charge. Decode the compressed object into the staging folio; on pre-transfer failure, free the reservation and preserve the compressed source.
5. Transfer data authority to the valid locked staging folio. Remove/free the compressed object only after that authority transfer. The existing folio-lock-to-PG_writeback handoff can be retained for this first demotion.
6. Submit using the explicit physical entry. On failure preserve/redirty the staging folio and retain correct ownership for retry; on success release staging through the normal swap-cache/writeback lifetime path.

The final copy on SSD may be an ordinary uncompressed page. Storing variable-length compressed bytes on SSD would require a separate on-disk format and metadata design, outside this first mechanism.

### General physical replacement and promotion

For SSD A-to-B, retain A as the published location while B is reserved and written. A transient migration record owns B, the source pin, staging, charge deltas and completion. On completion, revalidate logical identity and source location, atomically publish B under the logical-entry lock, fix the reverse mappings, then retire A after all readers/I/O have released it. On failure, cancel B and preserve A. Swapped data may become resident or be invalidated during the copy; that outcome must cancel or reconcile the move rather than resurrect an old logical slot.

A physical reservation that exists before normal reverse-map publication must still be visible to destination swapoff, or device liveness must be held in a way swapoff waits for. The current combined allocation/publication routine avoids this split; the new reservation API must make the replacement obligation explicit.

Promotion to compressed RAM uses the same logical identity but must have fallible memory charging, admission and rollback in its normal worker context. It cannot inherit ZSwap's PF_MEMALLOC forced-charge assumption. Promotion policy needs its own hotness signal and hysteresis; a fault that reads data into application memory is ordinary swap-in, not evidence of SSD-to-compressed-tier promotion.

## Ownership and concurrency checklist

| Resource | Owner/protection | Publication and release |
| --- | --- | --- |
| Logical entry | Existing swap references and owning device pin; validate after sleep. | PTE identity remains stable throughout migration; no source pointer survives without its documented protection. |
| Compressed handle | XSwap frontend entry/pool validity under its synchronization contract. | Publish after store and charge succeed; release only after valid data authority is transferred or final invalidation wins. |
| Staging folio | Swap-cache reference + folio lock, then PG_writeback; explicit migration reference if a new completion transaction needs one. | Must outlive async access and remain recoverable after I/O failure. |
| Physical reservation | Migration transaction until committed; destination-device lifetime held. | Unpublished reservations need a swapoff-visible lifecycle and exact rollback. |
| Published physical slot | Logical mapping + reverse map, logical-to-physical lock order. | Release validates the physical slot still names the same logical owner. |
| Charges | The owning memcg/object cgroup, with separate compressed bytes, physical slots and transient bytes. | Charge before publication; rollback each failed stage; free/uncharge once. Preserve cgroup lifetime and reparent/offline behavior. |

The initial implementation can keep a frontend compressed index plus the existing `xs_table` physical mapping. A universal tagged per-slot location object is not necessary merely to get RAM-to-SSD demotion working. It becomes a separate design choice if a full migration transaction requires one, with its metadata cost measured.

## Pressure integration and forward progress

Register an XSwap shrinker with memcg and NUMA awareness after its frontend exists. Reuse established reclaim signaling instead of initially editing `vmscan.c`. Keep victim selection bounded; stop when no eligible target, permission, memory, or I/O progress exists.

Pressure work must account for the actual pool backing footprint and temporary full pages. Releasing N compressed objects does not necessarily release N backing pages because allocator packing/fragmentation matters. An asynchronous enqueue or write submission is not net RAM freed. Record scanned entries, submitted pages, completed writes, pool backing bytes, staging bytes/peak, and eventual net bytes released separately.

A worker may help control latency, but moving work to a queue alone does not solve allocation under pressure. Bound concurrency and staging allocations, obey NOFS/NOIO, and verify progress or a clean bounded failure with injected allocation shortage. A reserve/mempool is a candidate remedy only with a clear ownership, size and exhaustion contract; it is not free memory.

For the first automatic policy, permit a strictly downward destination rule and exclude the source. Add hysteresis before enabling promotion so sustained or oscillating pressure cannot bounce the same data indefinitely. Retain memcg writeback-disable semantics independently of whether the legacy ZSwap frontend is enabled.

## Campaign dependency and falsifiers

| Stage | Substantive question | Required proof | Falsifier/stop |
| --- | --- | --- | --- |
| C1, shared mechanism | Can two clients share compression/object storage while retaining independent ownership and established behavior? | Exact-tree decomposition; identical nonzero compressible/incompressible data behavior; codec lifecycle, failure cleanup, ZSwap baseline guards. | Hidden ZSwap registry/policy dependency, added lifetime ambiguity, leak/accounting mismatch, unguarded regression. |
| C2, independent frontend | Can XSwap serve compression through its own operations with ZSwap compiled out? | `CONFIG_ZSWAP=n` config identity; actual nonzero compressed object creation/readback; regular ZSwap regression arm; invalidate, concurrent faults, teardown and fallback. | Merely disabling a runtime parameter, zeromap-only evidence, any required ZSwap symbol/state, double compression, invalidation/teardown race. |
| C3, bounded demotion | Does XSwap pressure reclaim move cold RAM-resident swap data to a selected SSD and release net RAM while preserving correctness? | Config-bound pressure scenario, source residency and backing-byte reduction, target physical allocation and I/O, staging-drain proof, roundtrip, memcg and failure matrix. | Counters without residency transfer, hidden peak RAM expansion/OOM, no eventual net reduction, lock/I/O error, unauthorized destination, unbounded retry or thrashing. |

Within C3, establish a deterministic explicit-destination demotion before adding automatic pressure selection. Full SSD A-to-B replacement and promotion should be recorded as dependent hypotheses and run only when the transaction/completion and trusted-test capabilities are present; the first demotion does not establish those features.

For performance screening, retain the approved swap-in primary metric. Architecture completion and pressure reclamation require separate correctness/mechanism evidence; a swap-in speedup alone cannot substitute for them. Pure extraction may be scientifically neutral; an equivalence claim still needs the frozen equivalence criterion, not just a non-significant delta.

## Required code scope

The coordinator/R1 chooses final names; the following is a concrete minimal split for approval and implementation review.

| Files | Purpose |
| --- | --- |
| New shared compression implementation/header chosen by R1; `mm/zswap.c`; `mm/Makefile`; `mm/Kconfig` | Common mechanism, legacy frontend adaptation, independent build selection. |
| New `mm/xswap.c` and private `mm/xswap.h` | XSwap compressed frontend, ops, demotion core and pressure adapter. This can initially coexist with cluster/capacity management in swapfile.c. |
| `include/linux/swap_ops.h`; `mm/page_io.c` | Device-selected compressed I/O dispatch and completion ownership; preserve physical batch path. |
| `mm/swapfile.c`; `mm/swap.h`; `include/linux/swap.h` | Invalidation/lifecycle calls, frontend state, logical/physical mapping and transactional allocation helpers. |
| `mm/memcontrol.c`; `include/linux/memcontrol.h` | Frontend-neutral permission/accounting access, !ZSWAP behavior, fallible worker charging if promotion is introduced. |
| `mm/swap_state.c`; `mm/swap_table.h` only if exact implementation requires them | Existing cache/large-folio mapping integration; avoid widening scope preemptively. |
| Trusted config/guest/runner/proof files identified in R3 | Configuration matrix, direct mechanism and failure evidence. Candidate-supplied instrumentation is not automatically trusted proof. |

A new `vmscan.c` hook and a new SSD compressed format are not required for the first three-stage path.

## Test matrix required before runtime claims

- Build/config identity: XSwap with ZSwap off; both frontends enabled; ordinary ZSwap regression; relevant swap-off configuration build where interface guards change.
- Data: zero as a separate zeromap case; nonzero compressible, same-value nonzero, incompressible, mixed-size folios and partial fallback; checksums after demotion and re-fault.
- Concurrency/lifetime: concurrent faults, invalidation/entry reuse, source and destination swapoff, XSwap destroy, compressed pool/codec lifecycle and cgroup offline.
- Error/progress: destination ENOSPC, staging allocation failure, decompression failure if injectable, target I/O failure, NOFS/NOIO, writeback-disabled and limited memcg.
- Sanitizers/review: exact-tree lock order/lifetime review plus available KASAN/lockdep; the broader profile's KCSAN/fault-injection requirements remain real capability work.
- Mechanism/pressure: target-selected transfer, absence of legacy ZSwap dependency, source and destination residency, in-flight memory peak, completed-I/O and final memory accounting; rate-limited oscillating pressure only after deterministic demotion works.

## Peer reconciliation

- R1 agrees that shared-library handles are frontend-owned and non-consuming loads need no migration API or library knowledge of logical entries.
- R1 identified and this audit independently confirmed the ZSwap-disabled writeback helper and PF_MEMALLOC charging constraints.
- R3 confirmed that the present runner unconditionally selects ZSwap and binds one standard config, and that current backend-swapoff checks do not provide migration-race or ENOSPC injection. Therefore exact independence and generic migration claims require scoped trusted runner/proof work.
- R2 sent R3 the zero-page bypass, protected-staging failure semantics, and required net-memory evidence.

## Limitations and execution readiness

This was source research and planning. No runtime performance, new correctness result, or approved executable profile was created. The existing swap-core allowlist cannot contain this complete library/Kconfig/frontend/memcg split, and the existing swap-architecture profile explicitly lacks necessary coverage. A partial source refactor within the old scope can only support its narrower claim. The coordinator must resolve the exact scope/capability plan through the authorized project process before architecture execution; changing a profile flag alone is insufficient.
