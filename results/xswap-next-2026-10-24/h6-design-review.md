# H6: adjacency admission for both readahead modes

Judgment: suitable for bounded fast discovery (confidence: medium). A missing prefetch counter or a failed latency guard changes that judgment.

The H3 pilot produced zero disk swap_ra because its VMA-only predicate rejected the rotational physical backend. Keep the same baseline and physical-residency checks, but allow adjacent faults in both readahead modes. In cluster mode, store each demand-miss address in the existing advisory VMA history. In VMA mode, leave adjacent history for the normal VMA estimator. A discontinuity resets history and retains synchronous single-folio reads.

## Ownership

| Resource | Owner and protection | Change |
|---|---|---|
| VMA history | fault-side VMA lifetime; atomic advisory updates | cluster-mode misses record the current address |
| device | do_swap_page get_swap_device reference | unchanged |
| descriptor/backend | repaired unpinned RCU/cluster lock lookup | boolean hint only; no pointer survives |
| folio | existing swap cache, lock and reference rules | unchanged |
| compressed object/memcg | existing store/load/free and charge rollback | unchanged |

No new lock order, allocation or object lifetime is introduced. Mode switches may lose advisory hit history or alter speculation; correctness remains in the existing cache and I/O paths. Cluster-mode cache hits update global counters rather than VMA history, so the next miss after a prefetched block may stay synchronous before another adjacent miss admits readahead.

## Verification

Require nonzero disk swap_ra and useful swap_ra_hit, byte-exact correctness and passing calibrated latency guards. The global window can survive a discontinuity, so rare random adjacency remains a tail risk. Four-KiB performance evidence leaves large folios, KCSAN and failure injection for later review.

Exact candidate: `25e1feb2b74f8ab30db0816e194294b7a6085a7f`. Scope/whitespace/checkpatch pass.

## Independent review of exact patch

No blocking correctness finding was supported for `25e1feb2b74f8ab30db0816e194294b7a6085a7f`. The H3 delta changes advisory admission/history only. Independent review notes conservative sequential false negatives after prefetched hits, extra random-miss atomic history traffic, occasional random adjacency and fragmented physical neighbors as measured performance risks. Admission and dispatch may sample different readahead modes; existing references, slot validation and I/O continue to own correctness. The reviewer ran no builds or guests and gave no promotion recommendation or signoff.
