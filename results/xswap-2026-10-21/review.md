# xswap candidate review

Reference `37de636c` (Phase I v4 + Phase II v1). Each candidate is an
independent patch on that reference and changes only `mm/swapfile.c`.
The measured outcome is in [README.md](README.md). This file records why
each change was safe to test and what it was expected to do.

## Shared safety argument

All three candidates change constants only. Every lock, publication order,
lifetime rule and failure path stays the same; only how often existing paths
run changes. The paths involved are:

- **Grow** (`cluster_alloc_swap_entry` → `xswap_map_clusters`) runs under
  `xswap_lock`. It rejects stale ranges with `-EAGAIN`, allocates without
  reclaim, rolls back partial mappings, and publishes the new bound with
  release ordering. It drops and retakes the per-CPU cluster lock around
  the mapping.
- **Shrink** is deferred to `xswap_shrink_work` from `__free_cluster`. It runs
  under `xswap_lock` and checks occupancy. It then takes the contiguous free
  tail, keeps one chunk of slack, and revalidates flags and cluster locks
  under `si->lock` before detaching. Unmapping releases backing records,
  flushes per-CPU references, waits for RCU, and frees the pages.
  Destroy and swapoff cancel the work first.

Correctness risk: **low**. Performance risk: more frequent unmap/RCU
waits (shrink) or larger allocation bursts (grow).

## 1. `XSWAP_SHRINK_MIN` 8 → 4 chunks

The smoke boots kept 429 (disk) and 471 (zswap) free tail clusters with zero
shrinks. The minimum batch looked like the gate. The `06.patch` commit
message also says four chunks, while the code uses eight.

**Expected:** more shrinks, fewer retained clusters.
**Observed:** shrinks rose slightly. Two zswap candidate boots shrank yet
kept 2409/2482 clusters with only 82/121 free at the tail. The gate was the
position of the highest in-use slot, not the batch size.

## 2. `XSWAP_GROW_CHUNKS` 4 → 8

Growth was capped at four chunks per episode, and there were 12–16 episodes
per boot.

**Expected:** fewer, larger grows.
**Observed:** zswap grows fell from 15–16 to 13, so the mechanism works.
Retained clusters and latency stayed within A/A spread.

## 3. Cap 8 and grow target 65% → 75%

This keeps the batching from (2) and requests less headroom. The target
stays inside the 50%/85% trigger band.

**Expected:** fewer retained clusters at the cost of more grows.
**Observed:** grows rose to 18–23. Retained clusters did not fall.

## Review conclusion

Rounds 2 and 3 tuned growth while the round-1 evidence already pointed at
free-tail-only shrink. They were the wrong next step, and that is the main
process lesson. See [DESIGN.md](../../DESIGN.md#hypotheses-ranked).

Codex proposed and implemented these candidates. A later review (this
revision) re-read the snapshots and replaced the original conclusions.
