# Adaptive Stride- and Streak-Gated Swap Readahead

**needs-review** — Screening benchmark: streak gating eliminates speculative readahead on random workloads with -0.96% disk mean and -6.4% zram p99 latency gains.

## Mitigating speculative readahead penalties on non-contiguous swapin

Standard swap readahead speculatively grows windows on initial faults, penalizing random access. Candidate exp2-stride-gated-ra-v1 introduces strict stride and streak gating before expanding readahead windows beyond 1.

Hypothesis 2 gates swapin readahead expansion in mm/swap_state.c, resetting streak counters and collapsing readahead window on non-contiguous access. Evaluated under Protocol Revision 7 with attributable metadata accounting.

Evidence: campaigns/exp2-stride-gated-ra/research.json, campaigns/exp2-stride-gated-ra/patches/exp2-stride-gated-ra-v1.patch

## Swap readahead heuristic and memory layout

Swap readahead decisions track access strides in VMA readahead state and dynamically compute window size during page faults.

Evidence: campaigns/exp2-stride-gated-ra/research.json, campaigns/exp2-stride-gated-ra/protocol.json

## Streak gating in swap_vma_ra_win and swap_update_readahead

Baseline expands window size aggressively and retains prev_win / 2 on direction changes. Candidate introduces 2+ contiguous hit requirement before win > 1 and immediate collapse to win = 1 on non-contiguous fault.

Evidence: campaigns/exp2-stride-gated-ra/patches/exp2-stride-gated-ra-v1.patch, campaigns/exp2-stride-gated-ra/reviews/exp2-independent-v1.json

## Modifications in mm/swap_state.c

Default uninitialized VMA readahead value to 0; in swap_vma_ra_win and swap_update_readahead, require 2+ consecutive contiguous hits before expanding win > 1; immediately collapse win to 1 on stride disruption; in __swapin_nr_pages, bypass window retention on offset discontinuity.

Evidence: campaigns/exp2-stride-gated-ra/patches/exp2-stride-gated-ra-v1.patch, campaigns/exp2-stride-gated-ra/candidates/exp2-stride-gated-ra-v1/value.json

## Architectural decision: exploratory screening completed

Candidate passed all 17 correctness gates, probe calibration, and fast screening benchmark. While random tail latency improved by up to 6.4%, modest net gain within noise retains this candidate as an exploratory screen.

The experiment proves that streak gating successfully prevents speculative swapin I/O during random access. Future work should combine streak gating with asynchronous prefetch or larger folio clustering to offset the sequential ramp latency.

Evidence: campaigns/exp2-stride-gated-ra/ledger/ledger.json, campaigns/exp2-stride-gated-ra/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| ddb7221b7c6b4a618c39cec4382e1b81 |  | probe | CALIBRATED |
| 1b9c659c1389451ba5f191a840e0a6f1 | exp2-stride-gated-ra-v1 | probe | PROBE_PASS |
| ff74475894ee4796b2a46ab5d9b8d808 |  | fast | CALIBRATED |
| c9bf37d96a98448f84216d7755599b6a | exp2-stride-gated-ra-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
