# Follow-up hypotheses and diagnostic scope

## Bounded cache-only tail reclamation

Proposed independently on observation baseline 4f83412c1d59eaf6a4d2460cb47fe0177a3be0c4, without low-first allocation. The first-cycle snapshots show that few high cache-only slots can block tail shrink while PTE-referenced slots remain low. Hypothesis: a bounded pass using the existing guarded swap-cache reclamation helper can remove those associations and expose a contiguous free tail.

The proposed pass holds the existing mapping mutex, never holds a cluster or device spinlock across the reclamation helper, preserves its folio ownership/writeback/reference guards, and stops at a blocker. It examines only the last SHRINK_MIN + SHRINK_SLACK clusters per invocation. Existing shrink isolation and unmap remain authoritative. Same-worker rescheduling is suppressed; external frees still trigger work. This is a plan, pending patch review and execution.

Falsifying observations: high cache-only tail remains with no settled metadata reduction; large latency or repeated-pressure regression; any correctness/lifetime/warning failure. Future I/O/compression cost and mutex hold time are material risks. Existing fifteen-field observation ABI and frozen performance protocol remain unchanged. Per-pass work instrumentation is absent, so settled counters alone cannot prove the detailed causal chain.

## Controlled high-anchor diagnostic

Prepared workload d732ae919a599afda4da20990f79a725e31201da retains a high live anchor across three filler/unmap cycles. Its independent parser/runner is being prepared. This is a new diagnostic protocol, not a replacement for the ongoing comparison. The baseline and normalized configuration are pinned to the observation build; no runtime has occurred.

Reserve at most two baseline diagnostic boots (disk and zswap) from the same total 96-guest budget. The diagnostic runner must append to the existing shared attempts ledger under the common runtime lock as well as its local ledger. Deadline and global STOP remain unchanged. Two 40-boot comparisons, eight calibration boots and two initial smoke boots use 90 attempts; the two diagnostic boots leave four. Two of the remaining four may be used for candidate lockdep smoke coverage.

High placement proves high live occupancy, not free interior holes. Compare free-cluster and tail counters descriptively and retain cache-only blockers. SWAPOFF_LIVE_PASS here means backend teardown plus retained-data verification, not proof of live physical-backend swapoff. COW is resident COW. Missing sanitizer, concurrency and failure-injection coverage stays explicit.
