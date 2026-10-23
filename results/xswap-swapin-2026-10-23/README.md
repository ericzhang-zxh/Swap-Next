# xswap swap-in experiments: completed, both screened out

The authorized H1 physical-residency and H2 compressed-residency readahead candidates were implemented independently on descriptor-lifetime baseline `5e84ca928deeacb4eee656806a003f27d1eca82f`. Both fail calibrated fast-tier guards, so neither is eligible for slow confirmation or promotion.

| Candidate | Intended result | Decisive screening result |
|---|---|---|
| H1 `e401f1314d81` | Physical readahead | Disk sequential mean latency fell 84.69%, but random p99 rose 10.50%, exceeding its 3% envelope. |
| H2 `f7093a0732ae` | Compressed-resident prefetch | Zswap sequential mean changed -0.41% within 3% noise; sequential p99 rose 280.79%, exceeding its 7.73% envelope. |

These are two-pair screening observations, not independently confirmed causal effects. H2 uses synchronous ordinary swap-cache prefetch, not a batched decompressor. Its measured distribution is consistent with concentrating decompression into fewer, longer faults.

## Evidence

- [Interactive result page](explainer.html), [full report](REPORT.md), [machine-readable summary](summary.json).
- 46 guest attempts: 42 integration passes and 4 retained pre-calibration harness failures. No candidate kernel defect was established by those four failures.
- All 12 final standard/KASAN × disk/zswap correctness runs passed. Baseline/H1/H2 KASAN lifetime stress passed 8/12/8 rounds with actual writeback, growth/shrink, data verification and no detected kernel warnings.
- Eight new kernel builds completed; one existing baseline build was reused. Output configurations, kernel hashes and serial hashes are retained.
- 59 harness/workflow regression tests passed after the final console-drain change. Controller checks and strict checkpatch passed for both candidates.
- Sparse found no new diagnostics, but a baseline `mm/memory.c:282` type error prevents claiming a fully clean sparse run.
- No slow-tier performance run, formal acceptance, merge, push or publication occurred. Both candidates are closed; no campaign process remains running.

## Scope gaps

No CONFIG_SWAP=n full build, KCSAN, allocation/I/O fault injection, large-folio acceptance, holdout confirmation or full formal policy coverage. The campaign's formal runtime/promotion gates remain disabled. This is the bounded discovery run authorized by [resume-contract.json](resume-contract.json).

The exact candidate patches are in `patches/xswap-swapin/`. The report generator is retained as [generate-report.py](generate-report.py); it reads trusted evidence and writes to an external output directory. The final HTML expands exact diffs on demand and has been rendered in light and dark themes.
