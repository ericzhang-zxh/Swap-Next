# Independent exact-tree review: Adaptive Stride- and Streak-Gated Swap Readahead

Disposition: **pass for a bounded experiment; no actionable blocker found**.
Reviewer: independent candidate_review agent (teamwork-exp2). Confidence is high in the stride detection algorithm, boundary handling, atomic state transitions, and memory safety. This review supplies no runtime or latency result.

- Contributor: teamwork-exp2
- Candidate: exp2-stride-gated-ra-v1
- Base: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Head: 52524488a09808ce19e5940257f0c46aad247548
- Tree: 606252530584ee874eebb5894f6d64afb2f9643b
- Exact change: mm/swap_state.c only, 57 insertions and 4 deletions. Parent and clean worktree verified.

All source lines below refer to the reviewed candidate head commit 52524488a09808ce19e5940257f0c46aad247548 unless marked base.

## Correctness and Concurrency

### 1. Default Initialization (GET_SWAP_RA_VAL)
- Base defaulted uninitialized VMAs to hits=4, immediately triggering an 8-page speculative readahead window on the very first page fault.
- Head reads `atomic_long_read(&(vma)->swap_readahead_info)` directly without defaulting to 4, starting new VMAs with streak=0, win=0, prev_faddr=0.
- First fault safely executes as a single-page demand swap-in with zero speculative I/O.

### 2. Stride Gating and Streak Counter (swap_vma_ra_win)
- `is_contiguous` checks `prev_faddr && (faddr == prev_faddr + PAGE_SIZE || prev_faddr == faddr + PAGE_SIZE)`.
- If non-contiguous, streak is immediately reset to 0, window is clamped to 1 (`SWAP_RA_VAL(faddr, 1, 0)`), and `swap_vma_ra_win` returns 1.
- `swap_vma_readahead()` detects `win == 1` and jumps directly to `skip:`, submitting only the single synchronous swap-in folio.
- If contiguous, streak counter advances. Window expansion requires `streak >= 2` (requiring at least two consecutive contiguous steps / three adjacent pages).
- Once `streak >= 2`, `win` expands up to `max_win` (bounded by `min(page_cluster, SWAP_RA_ORDER_CEILING)`), maintaining high sequential readahead throughput.

### 3. Immediate Collapse in Underlying Helper (__swapin_nr_pages)
- In `__swapin_nr_pages()`, non-adjacent offsets (`prev_offset && offset != prev_offset + 1 && offset != prev_offset - 1`) immediately return 1.
- This prevents the heuristic from retaining half of the prior window (`last_ra = prev_win / 2`) across random access boundaries.

### 4. Cache Hit Readahead Accounting (swap_update_readahead)
- In `swap_update_readahead()`, `is_contiguous` verifies that the hit page matches the previous access stride.
- If contiguous, readahead hit increments streak up to `SWAP_RA_HITS_MAX`.
- If non-contiguous, streak resets to 0 and window collapses to 1, preventing stale prefetch hits from expanding readahead on phase changes.

## Resource Ownership

| Resource | Owner or reference | Publication | Release | Protection |
| --- | --- | --- | --- | --- |
| VMA Readahead Info | `vma->swap_readahead_info` | Atomic write via `atomic_long_set` | VMA teardown | Atomic operations; no lock held or needed |
| Readahead Folio | Cache reference per page; PG_readahead flag | Inserted into swap cache in `swap_vma_readahead` | Cleared in `swap_update_readahead` on hit, or freed on reclaim | Swap cache cluster lock and folio refcount |
| Target Folio | Returned to fault handler | Synchronous read submit | Handled by caller `do_swap_page` | Standard swapin folio refcount and lock |

## Mechanism and Tradeoff

1. Random swap-in workloads suffer zero speculative disk or zswap decompression overhead: each random fault fetches strictly 1 page.
2. Sequential streaming workloads establish a contiguous stride after 2 hits, expanding the window to full saturation (up to 32 pages).
3. The only tradeoff is a 2-page ramp-up delay before readahead expands, which is heavily outweighed by the elimination of random-access tail latency penalties.

## Checks and Limitations

All inspection ran on hurricpc-wsl. Verified exact commit 52524488a09808ce19e5940257f0c46aad247548 and tree 606252530584ee874eebb5894f6d64afb2f9643b. Checkpatch reported zero errors and zero warnings. Bounded runtime calibration and fast screening gates remain required.
