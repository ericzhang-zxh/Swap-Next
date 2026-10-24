# xswap-swapin-2026-10-23

Status: 2 candidates screened out; none eligible for slow confirmation. No candidate promotion or code merge. Report publication is separate.

4 retained failed harness attempts preceded calibration; they are not candidate-bug findings.

Observed guest attempts: 46; integration passes: 42; completed failed: 4; running: 0; incomplete: 0; stopped: 0; effective KASAN passes: 9.

## Evaluations
| Action | Tier | Candidate | Status | Reason |
|---|---|---|---|---|
| calibrate | fast | None | CALIBRATED |  |
| evaluate | fast | xs-ra-phys-v1 | REGRESSION |  |
| evaluate | fast | xs-ra-zswap-v1 | REGRESSION |  |

## Metric ratios and failed guards
Fast is a screening result; slow is confirmation evidence. Few fast pairs do not establish a persistent causal regression. H1 has no compressed readahead path; observed zswap differences, including baseline random-tail outliers, are not credited as H1 mechanism improvements.
| Candidate | Tier | Pairs | Metric | Baseline/candidate | Latency change % | Noise % | Guard |
|---|---|---|---|---|---|---|---|
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_seq.mean_ns | 6.533107 | -84.69 | 4.48 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_seq.p99_ns | 1.113266 | -10.17 | 3.06 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_rand.mean_ns | 0.987356 | 1.28 | 3.0 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_rand.p99_ns | 0.904953 | 10.5 | 3.0 | FAIL |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_seq.mean_ns | 1.006231 | -0.62 | 3.0 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_seq.p99_ns | 1.05638 | -5.34 | 7.73 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_rand.mean_ns | 1.162207 | -13.96 | 3.0 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_rand.p99_ns | 2.665868 | -62.49 | 10.88 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_seq.mean_ns | 1.015766 | -1.55 | 4.48 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_seq.p99_ns | 1.048207 | -4.6 | 3.06 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_rand.mean_ns | 1.091175 | -8.36 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_rand.p99_ns | 1.053169 | -5.05 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_seq.mean_ns | 1.004084 | -0.41 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_seq.p99_ns | 0.262609 | 280.79 | 7.73 | FAIL |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_rand.mean_ns | 1.005972 | -0.59 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_rand.p99_ns | 1.006824 | -0.68 | 10.88 | PASS |

## Failed guards
- xs-ra-phys-v1 fast REGRESSION: swapin-disk.swapin_rand.p99_ns
- xs-ra-zswap-v1 fast REGRESSION: swapin-zswap.swapin_seq.p99_ns

## H2 compressed latency distribution
Inference: synchronous compressed prefetch concentrates decompression cost into fewer fault bursts. Source paths, readahead counters and the p50/p90 distribution support this interpretation; independent profiling has not established causality.
| Candidate | Pair | Arm | p50 us | p90 us | Mean us | p99 us |
|---|---|---|---|---|---|---|
| xs-ra-zswap-v1 | 0 | a | 13.509 | 13.932 | 11.683 | 25.374 |
| xs-ra-zswap-v1 | 0 | b | 0.528 | 82.369 | 11.633 | 97.538 |
| xs-ra-zswap-v1 | 1 | b | 0.528 | 82.68 | 11.629 | 98.27 |
| xs-ra-zswap-v1 | 1 | a | 13.535 | 13.941 | 11.674 | 26.051 |

## Mechanism counters
| Candidate/action | Tier | Pair | Case | Arm | swap_ra | swap_ra_hit | pswpin | zswpin |
|---|---|---|---|---|---|---|---|---|
| calibrate | fast | 0 | swapin-disk | a | 0 | 0 | 262140 | 0 |
| calibrate | fast | 0 | swapin-disk | b | 0 | 1 | 262167 | 0 |
| calibrate | fast | 0 | swapin-zswap | a | 0 | 0 | 0 | 262166 |
| calibrate | fast | 0 | swapin-zswap | b | 0 | 0 | 0 | 262160 |
| calibrate | fast | 1 | swapin-disk | b | 0 | 0 | 262155 | 0 |
| calibrate | fast | 1 | swapin-disk | a | 0 | 0 | 262152 | 0 |
| calibrate | fast | 1 | swapin-zswap | b | 0 | 0 | 0 | 262160 |
| calibrate | fast | 1 | swapin-zswap | a | 0 | 0 | 0 | 262167 |
| xs-ra-phys-v1 | fast | 0 | swapin-disk | a | 0 | 0 | 262170 | 0 |
| xs-ra-phys-v1 | fast | 0 | swapin-disk | b | 114943 | 114936 | 262176 | 0 |
| xs-ra-phys-v1 | fast | 0 | swapin-zswap | a | 0 | 0 | 0 | 262160 |
| xs-ra-phys-v1 | fast | 0 | swapin-zswap | b | 0 | 0 | 0 | 262160 |
| xs-ra-phys-v1 | fast | 1 | swapin-disk | b | 114832 | 114827 | 262152 | 0 |
| xs-ra-phys-v1 | fast | 1 | swapin-disk | a | 0 | 0 | 262163 | 0 |
| xs-ra-phys-v1 | fast | 1 | swapin-zswap | b | 0 | 0 | 0 | 262166 |
| xs-ra-phys-v1 | fast | 1 | swapin-zswap | a | 0 | 0 | 0 | 262160 |
| xs-ra-zswap-v1 | fast | 0 | swapin-disk | a | 0 | 0 | 262132 | 0 |
| xs-ra-zswap-v1 | fast | 0 | swapin-disk | b | 0 | 2 | 262146 | 0 |
| xs-ra-zswap-v1 | fast | 0 | swapin-zswap | a | 0 | 0 | 0 | 262166 |
| xs-ra-zswap-v1 | fast | 0 | swapin-zswap | b | 114780 | 114773 | 0 | 262170 |
| xs-ra-zswap-v1 | fast | 1 | swapin-disk | b | 0 | 2 | 262145 | 0 |
| xs-ra-zswap-v1 | fast | 1 | swapin-disk | a | 0 | 2 | 262146 | 0 |
| xs-ra-zswap-v1 | fast | 1 | swapin-zswap | b | 114736 | 114729 | 0 | 262166 |
| xs-ra-zswap-v1 | fast | 1 | swapin-zswap | a | 0 | 0 | 0 | 262163 |

## Xswap occupancy snapshots
| Candidate/action | Pair | Case | Arm | Phase | Mapped | Usage | Grows | Shrinks |
|---|---|---|---|---|---|---|---|---|
| calibrate | 0 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 0 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 0 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-zswap | a | swapin_end | 657 | 1 | 10 | 1 |
| calibrate | 0 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-zswap | b | swapin_end | 657 | 1 | 10 | 1 |
| calibrate | 1 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-disk | b | swapin_end | 146 | 0 | 10 | 1 |
| calibrate | 1 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 1 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 1 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-disk | a | swapin_end | 146 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-disk | a | swapin_end | 657 | 1 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |

## Correctness and build evidence
Exact run gates, output-config sanitizer settings, result and serial hashes are preserved in summary.json. Debug names alone do not establish KASAN coverage.

## Sparse coverage
- results/xswap-swapin-2026-10-23/h1-sparse.json: no_new_diagnostics=True, full_tool_success=False. Baseline diagnostics remain a tool-coverage gap.
- results/xswap-swapin-2026-10-23/h2-sparse.json: no_new_diagnostics=True, full_tool_success=False. Baseline diagnostics remain a tool-coverage gap.

## Missing policy gates
- baseline: gcc_swap_off
- baseline: checkpatch
- baseline: allocation_failure
- baseline: io_failure
- baseline: memcg_limits
- baseline: large_folio
- baseline: kcsan
- xs-ra-phys-v1: gcc_swap_off
- xs-ra-phys-v1: allocation_failure
- xs-ra-phys-v1: io_failure
- xs-ra-phys-v1: memcg_limits
- xs-ra-phys-v1: large_folio
- xs-ra-phys-v1: kcsan
- xs-ra-zswap-v1: gcc_swap_off
- xs-ra-zswap-v1: allocation_failure
- xs-ra-zswap-v1: io_failure
- xs-ra-zswap-v1: memcg_limits
- xs-ra-zswap-v1: large_folio
- xs-ra-zswap-v1: kcsan

## Exact patches

The interactive report retains expandable exact diffs. Download the original patches from the [pinned experiment commit](https://github.com/ericzhang-zxh/Swap-Next/tree/23f13a766e4df884ffee2ef5e1379c45e80e54c8/patches/xswap-swapin).

## Next hypotheses
- H1 adaptive readahead window with a tail guard: Reject a new candidate if random p99 exceeds its calibrated envelope.
- H2 bound synchronous decompression work: Reject unbounded prefetch or added demand-fault latency.
- Further validation only for a new candidate: Require fresh correctness evidence and a fast pass before slow confirmation.

## Limitations
- No processes remain active in the extracted campaign ledger.
- Retained failed harness attempts are not classified as candidate kernel defects.
- Gate inventory is conservative and may require manual matching of static reports.
- No candidate promotion or code merge. Report publication is separate.
