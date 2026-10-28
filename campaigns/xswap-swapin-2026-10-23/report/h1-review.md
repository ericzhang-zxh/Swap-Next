# H1 residency-aware physical readahead review

Base: `5e84ca928deeacb4eee656806a003f27d1eca82f`.
Head / revert commit: `e401f1314d81d3990de62af0ba37fc5df79193f6`.
Disposition: statically ready for the controller's build and correctness gates; no promotion decision.

## Mechanism and evidence

The baseline do_swap_page selects swapin_sync for SWP_SYNCHRONOUS_IO,
including xswap physical writeback. H1 tests backing under the xswap cluster
lock and selects existing readahead for backed faults. Both VMA and cluster
walks skip speculative xswap neighbors whose backing test is false. The
cluster entry point retains a compressed-target bypass because shmem calls
it directly. Existing plain swap paths retain their selection behavior.
Confidence: high from source tracing; a changed caller or backend invariant
would require re-review.

## Ownership and concurrency

| Resource | Owner / reference holder | Published when | Released when | Protected by |
|---|---|---|---|---|
| Swap device | do_swap_page get_swap_device; direct cluster caller; VMA walk takes additional refs for other types | Existing swapon | Existing swapoff after users drain | Device reference, unchanged |
| Cluster descriptor | Device mapped prefix; helper returns temporary locked pointer | Existing map release publication | Existing shrink grace period then cluster lock and unmap | Baseline swap_cluster_lock_unpinned RCU lookup and ci lock |
| xs_table and backend hint | Cluster; helper copies boolean only | Existing backend allocation under ci lock | Backend clearing/table freeing under ci lock | ci lock; no pointer or physical entry escapes |
| Folio | Allocation caller, then swap cache and I/O | __swap_cache_do_add_folio after second slot check | Existing cache removal, caller put and I/O completion | Folio lock/refcount and ci lock |
| Virtual slot | PTE/cache users; hint adds no user | Existing swap allocation | Existing last-user release | ci lock and existing swap counts |
| Physical slot | Virtual-slot backend and reverse map | Existing backend allocation/install | Existing release/unuse after folio coordination | Existing virtual-to-physical lock order; H1 never takes physical lock |
| Compressed object | Existing zswap entry | Existing zswap store | Existing load/invalidation/writeback | Unchanged zswap/folio synchronization |
| Memcg charge | Existing swap/cache ownership | Existing backend charge and swapin charge | Existing uncharge/failed charge rollback | Unchanged accounting paths |

All new helper callers protect the device. do_swap_page acquires it before
lookup; cluster readahead inherits its established device contract; VMA
neighbors on another device acquire and release their own reference even
when skipped. The helper obtains ci through the descriptor repair, reads
xs_table only under ci lock, then unlocks. It allocates nothing and holds no
pointer across a dropped lock.

The hint can become stale after unlock. __swap_cache_alloc performs its
existing two locked validity checks around allocation; the folio pins the
entry after publication. swap_read_folio resolves zswap/physical residency
again under existing folio and cluster protection. Concurrent free/reuse can
therefore change the residency eventually read; filtering is advisory, not
an atomic guarantee that every speculative read reaches disk. Concurrent
fault/cache insertion uses the existing EEXIST retry. This is a correctness-
preserving selection hint, not an ownership transfer. Confidence: medium
from source tracing; runtime race diagnostics would supersede it.

## Failure paths and configuration

No new allocation, charge, I/O completion or cleanup path was added.
Failed speculative allocation returns NULL and the walk continues; the target
retains its final synchronous cache read and existing error propagation.
Memcg failure rollback remains in __swap_cache_alloc. Physical swapoff uses
existing folio/slot coordination; H1 never retains a borrowed physical entry.
Baseline descriptor lookup/allocator repair code is unchanged.

CONFIG_SWAP=n gets a false helper stub. CONFIG_SWAP=y with CONFIG_XSWAP=n
uses the existing xswap_slot_backend stub; ordinary devices immediately
return false. No zswap-specific types or calls were added. Runtime behavior
with CONFIG_ZSWAP=n still depends on the baseline's xswap configuration.
These combinations were inspected, not compiled.

## Performance hypotheses and tradeoffs

Physically backed sequential faults may benefit from plugged neighboring
reads. Virtual adjacency does not ensure physical contiguity or merging.
Random access and fragmented layouts may pay more allocations, cache usage,
I/O and cluster-lock traffic. Compressed-only faults keep swapin_sync; a
physical hint check adds a cluster-lock acquisition. Backed faults now take
the order-0 readahead allocator, foregoing the previous large-folio
synchronous opportunity. Large-folio and mixed-residency workloads require
explicit regression inspection. Confidence: low until measured.

## Checks and limitations

- git diff --check: passed before commit.
- scripts/checkpatch.pl --no-tree --strict --no-signoff: 0 errors,
  0 warnings, 0 checks; evidence `h1-checkpatch.txt` and `h1-resume.patch`
  beside this review. Signoff checking was omitted because agents cannot
  certify DCO.
- Read repository contract, code patterns, campaign policy, kernel review
  skill and required process guidance. Changes limited to mm/memory.c,
  mm/swap_state.c and mm/swap.h.
- No builds, guests, sparse, fault injection, lockdep/KASAN/KCSAN, runtime
  data integrity, live swapoff or performance checks were run by this worker.
  These remain controller gates. No reproducer was executed and no security
  vulnerability is asserted. No policy, benchmark, evaluator or baseline
  changes were made. Nothing was pushed or published.

No blocking source-level ownership defect was identified in the added code.
The outstanding items are the build/runtime gates and measured tradeoffs
above, plus independent review of the experimental baseline itself.
