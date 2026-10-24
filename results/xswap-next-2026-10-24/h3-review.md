# H3: sequential physical readahead review

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`. Candidate: `22d34edafce4c1000dc3424604450f1eadb479ae`.

## Judgment

Suitable for a bounded fast experiment. Confidence: medium. A calibrated tail guard failure falsifies the expected tradeoff.

The prior physical-residency candidate reduced disk sequential mean latency by 84.69% but failed the random p99 guard (+10.50%). This candidate adds access-pattern admission rather than changing the window constant. The existing `swap_readahead_info` records the previous virtual address; an adjacent miss may prefetch physically backed slots, while a discontinuity resets advisory history and uses the baseline synchronous demand path. Compressed-only targets retain demand reads.

## Ownership and locking

| Resource | Owner / reference holder | Published | Released | Protection |
|---|---|---|---|---|
| target swap device | do_swap_page get_swap_device reference | existing device activation | existing put_swap_device | swap device reference |
| cluster descriptor | unpinned lookup local to hint | repaired mapped bound | local unlock; retirement grace period | repaired RCU lookup and cluster lock |
| backend entry | existing xswap slot mapping | existing writer under cluster lock | existing swap/cache release | cluster lock; returned hint copies only a boolean |
| folio | existing swap-cache read path | existing cache publication | existing folio_put and PTE mapping | existing lock and reference rules |
| memcg charge | existing backend/folio allocator | existing charge point | existing rollback/free path | unchanged accounting rules |
| VMA history | VMA under fault-side VMA lifetime | atomic_long_set | VMA teardown | advisory atomic history; concurrent faults may change speculation |

No descriptor, backend entry, or folio pointer crosses a new sleeping allocation. A stale residency result is only a hint; normal allocation/read paths revalidate. Readahead retains device references for cross-device PTEs and skips compressed-only neighbors. Errors and all charge/uncharge paths remain in existing code.

## Checks

Scope (3 files, 97 changed lines), diff whitespace and checkpatch pass. Exact-commit release/debug builds, data/COW/concurrent-fault/backend swapoff/live destroy, KASAN/lockdep, and calibrated AB/BA measurements remain to run.

## Limitations

History is shared within a VMA, so unrelated concurrent streams can alter admission. Cluster-based readahead is left disabled for xswap faults when VMA readahead is unavailable. 4 KiB workloads do not cover large folios, KCSAN, allocation/I/O failure injection, or full promotion. Sparse must be reported separately.

Revert candidate commits to return to the frozen baseline; no merge is authorized.
