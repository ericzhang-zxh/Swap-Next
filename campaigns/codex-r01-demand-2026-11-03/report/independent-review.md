**Disposition: PASS_FOR_BOUNDED_RUNTIME.** No blocking correctness finding is supported by this exact-tree source review. Proceed through the campaign’s candidate build and required correctness gates before probe and fast screening. Error-path equivalence is unproved; the allocation-failure race described below is a material tradeoff.

| Identity | Value |
|---|---|
| Campaign / candidate | `codex-r01-demand-2026-11-03` / `codex-r01-precheck-v1` |
| Contributor | `codex-research-01` |
| Head | `4068681982a044debd290884719e9bdbd4ac5ba9` |
| Source tree | `912225c401b2df2c160479533f0d9c961b06771c` |
| Parent and baseline | `5e84ca928deeacb4eee656806a003f27d1eca82f` |
| Change | `mm/swap_state.c`: 14 insertions, 13 deletions |
| Commit to revert | `4068681982a044debd290884719e9bdbd4ac5ba9` |

All source locations below identify files in the head Git tree unless explicitly marked as baseline.

The structural mechanism is established with **high confidence**. An eligible successful order-0 allocation with non-NULL `vmf` omits one `swap_cluster_lock_unpinned()` call, its RCU read-side section and cluster lock acquisition/release, and one `__swap_cache_add_check()`. The post-allocation lookup, locked validation, publication, charge and rollback remain mandatory at `mm/swap_state.c:491–527`. This establishes reduced source-level work per eligible allocation attempt. No measured latency improvement is claimed.

Non-NULL `vmf` identifies demand callers in the inspected tree, with these boundaries:

| Caller | Effect |
|---|---|
| Anonymous synchronous faults | `do_swap_page()` passes `vmf` through `swapin_sync()`; order-0 attempts take the new branch (`mm/memory.c:4994–5004`). |
| Shmem synchronous faults | `shmem_fault()` supplies `vmf`; `shmem_swap_alloc_folio()` forwards it through `swapin_sync()` (`mm/shmem.c:2251–2277, 2634, 2911–2933`). |
| Large-folio attempts | Every `order > 0` attempt retains the precheck. A later order-0 fallback with `vmf` takes the new branch. |
| Readahead, including swapoff’s readahead call | `swap_cache_read_folio()` supplies NULL `vmf`, preserving the precheck (`mm/swap_state.c:731–754`). |
| Zswap writeback / physical-backend removal | Direct allocation calls supply NULL `vmf` (`mm/zswap.c:1026`, `mm/swapfile.c:3542`). |
| Non-fault shmem access | Supplies NULL `vmf`; precheck retained. |

Xswap explicitly sets `SWP_SYNCHRONOUS_IO` at `mm/swapfile.c:5512`, so its anonymous demand faults reach the changed path even when data ultimately comes from a physical backend. The latency workload requests `MADV_NOHUGEPAGE`, verifies swapped pages, and times accesses to them (`benchmark/swap-standard/swapin.c:157–210`). Actual eligible-path frequency remains unmeasured. The optimization also applies to other synchronous swap devices and shmem faults; it is not xswap-exclusive.

**Ownership and protection review**

| Resource | Owner / reference holder | Published when | Released when | Protection |
|---|---|---|---|---|
| Newly allocated folio | Allocator’s reference; cache acquires `nr_pages` references | After folio lock/swapbacked initialization and locked slot validation | Pre-publication rejection puts the allocation reference; charge rollback removes cache entries and puts `nr_pages + 1`; normal consumers release their references | Cluster lock serializes cache publication; folio lock protects subsequent use |
| Swap slot | Existing swap count, then swap-cache occupancy as well | Allocation publishes the folio in the slot | Slot is freed only after its swap references and cache occupancy permit release | `ci->lock`; cached slots remain allocated even when swap count reaches zero |
| Xswap cluster descriptor | Device owns mapping; readers obtain temporary protected access | Mapping and lock initialization precede mapped-bound publication | Free tail is removed from allocation lists, bound lowered, readers drained, then pages unmapped | RCU lookup plus cluster lock before publication; locked cached folio pins its slot afterward |
| Swap device | Caller’s `si->users` reference or existing teardown protection | Existing device activation | Swapoff kills references and waits before freeing device resources | `get_swap_device()` / `put_swap_device()` and swapoff synchronization |
| Memcg charge | Folio charge and slot’s existing accounting ownership | Existing post-publication charge succeeds | Failed charge releases temporary accounting references; cache rollback remains symmetric; final folio release uncharges a committed charge | Existing memcg reference/accounting rules; folio remains locked during setup |
| Compressed object / physical backing | Existing zswap entry or xswap backend mapping | Existing store/backend paths | Successful load or slot teardown follows existing release paths | Locked swap-cache folio stabilizes the entry during read; existing cluster/backend synchronization |

The omitted precheck does not acquire a lasting slot reference or pin a descriptor across allocation. The baseline already drops its cluster lock before allocation and must relookup afterward. The candidate likewise retains no descriptor pointer across the sleeping allocation on the changed branch.

The retained lookup enters RCU before reading `nr_clusters_mapped`, acquires the cluster lock before leaving RCU, and rechecks table presence, entry type, cache occupancy and swap count. Xswap shrink lowers the mapped bound before its grace period and subsequently drains cluster locks before unmapping (`mm/swap.h:176–235`; `mm/swapfile.c:5035–5077`). After successful cache publication, cached slots cannot be freed merely because their swap count drops to zero (`mm/swapfile.c:1957–1977`). This supports the retained `ci` use during charge rollback.

Concurrent successful allocations remain serialized: one publishes; the loser observes `-EEXIST`, drops its temporary folio, and `swapin_sync()` retries cache lookup. Consumers still lock and verify the returned folio against their entry and PTE or shmem mapping. Charge failures remove the cache publication before unlocking and releasing references. I/O begins only after successful allocation/charge setup; existing I/O failure handling remains intact.

These lifecycle conclusions have **high source-review confidence**. A counterexample involving a publisher/free path outside these protections, or an exact-tree runtime integrity, lifetime or locking failure, would invalidate the pass.

**Material nonblocking tradeoff: `TRADEOFF-ENOMEM-RACE`**

The candidate widens an existing race in which a usable cached folio exists but the current fault returns an allocation error.

A concrete changed interleaving is:

1. Fault A’s cache lookup misses.
2. Fault B inserts a folio for the same swap entry.
3. In the baseline, A’s preliminary check observes it and returns `-EEXIST`; `swapin_sync()` retries lookup.
4. In the candidate, A attempts allocation. If allocation fails, `mm/swap_state.c:484–485` returns `-ENOMEM` without another cache lookup.
5. Anonymous fault handling can return `VM_FAULT_OOM` if A’s original PTE is unchanged (`mm/memory.c:5006–5017`). Shmem can similarly return `-ENOMEM` while its swap mapping remains unchanged (`mm/shmem.c:2516–2522, 2611–2624`).

The baseline already permits that OOM outcome when B inserts **after** A’s preliminary check but before A’s allocation fails. Consequently, this is not evidence that a required lifetime or publication guarantee was removed. It is a genuine expansion of the window for unnecessary allocation, reclaim and an OOM result despite a concurrently usable cache entry.

Confidence is **high** that this behavioral difference exists; its frequency and practical impact are **unknown**. It is nonblocking for the requested bounded experiment. Error behavior must not be described as identical. A reproducible increase in user-visible OOM or severe reclaim under contention would require rejection or revision. The existing correctness workload does not force this failure window.

**Checks and limits**

Independently performed:

- Read the repository contract, review skill, coding principles, campaign policy/protocol/research contract, and required kernel process documents.
- Verified head, tree, parent, changed paths and a clean candidate worktree.
- Inspected the complete patch, baseline implementation, callers, publication/removal, descriptor shrink, swapoff, charge rollback and read completion paths.
- Ran `git diff --check`: passed.
- Ran trusted `checkpatch.pl --no-tree --no-signoff` against the exact diff: **0 errors, 0 warnings**.
- Inspected the recorded static evidence and verified its log hashes and the frozen policy/protocol hashes.

Not performed by this reviewer: builds, sparse, guests, runtime reproduction, allocation or I/O fault injection, KASAN, KCSAN, lockdep, or performance measurement. The protocol’s correctness workload exercises anonymous order-0 data roundtrip, shared-entry concurrent faults, COW and live teardown; it does not establish shmem, THP, memcg-limit or allocation-failure coverage. The cited upstream rationale commit was unavailable in the local object store; this disposition rests on the verified baseline and candidate sources.

For both scored xswap latency cases, the source mechanism is reachable, while the amount of benefit and contention cost remain open. No persistent metadata or new lock-order obligation is introduced. The declared useful-effect threshold, metadata checks, random-latency guards and fresh calibration remain necessary.

This pass is limited to bounded runtime evaluation of the exact tree above. No promotion endorsement is given. The reviewer made no edits, launched no builds or guests, and left no work running.
