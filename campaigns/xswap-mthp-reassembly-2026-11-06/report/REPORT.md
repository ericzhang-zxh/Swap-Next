# Contiguous mTHP Swapin Reassembly (xswap-mthp-reassembly-v1)

**inconclusive** — Milestone 2 evaluation: lifting the zswap mTHP blackout with two-phase commit decompression passes all 17 integration gates while base-page latency remains equivalent to control.

## Lifting the zswap mTHP swapin blackout

Upstream mm/memory.c unconditionally returns 0 in thp_swapin_suitable_orders() when zswap is active, forcing 16 individual order-0 page faults. Milestone 2 lifts this blackout via contiguous zswap reassembly.

Milestone 2 builds on Milestone 1 allocator-first sync swapin by reassembling contiguous swap entries into orders 2 and 4 folios directly from zswap under a single page table lock hold.

Evidence: campaigns/xswap-mthp-reassembly-2026-11-06/research.json, campaigns/xswap-mthp-reassembly-2026-11-06/patches/xswap-mthp-reassembly-v1.patch

## Contiguous swap slot checking and high-order folio allocation

thp_swapin_suitable_orders() queries zswap_all_present() across orders 2 and 4. If all swap slots in the cluster reside in zswap, high-order folios enter swapin_sync() under a single PTL hold.

Evidence: campaigns/xswap-mthp-reassembly-2026-11-06/research.json, campaigns/xswap-mthp-reassembly-2026-11-06/protocol.json

## Two-phase commit subpage decompression in mm/zswap.c

Two-phase commit decompression in mm/zswap.c loads each subpage into kmap_local_folio offsets. If any slot fails, all are cleanly aborted without state corruption; otherwise all slots commit atomically.

Evidence: campaigns/xswap-mthp-reassembly-2026-11-06/patches/xswap-mthp-reassembly-v1.patch, campaigns/xswap-mthp-reassembly-2026-11-06/reviews/xswap-mthp-reassembly-independent-v1.json

## Kernel changes across memory management and zswap

Modified include/linux/zswap.h, mm/zswap.c, mm/memory.c, and mm/swap_state.c. Passed controller check with 0 checkpatch errors, 17/17 QEMU TCG integration gates, and probe evaluation under Revision 7.

Evidence: campaigns/xswap-mthp-reassembly-2026-11-06/patches/xswap-mthp-reassembly-v1.patch, campaigns/xswap-mthp-reassembly-2026-11-06/candidates/xswap-mthp-reassembly-v1/value.json

## Architectural verdict: Milestone 2 contiguous mTHP reassembly verified

Candidate xswap-mthp-reassembly-v1 verified the feasibility of contiguous mTHP zswap decompression with 17/17 correctness gates passing, establishing the foundational reassembly engine for Milestone 3 stride-aware batching.

Milestone 2 delivers verified contiguous mTHP reassembly from zswap with two-phase commit decompression and batch PTE mapping, providing the structural foundation for Milestone 3 stride-aware batching.

Evidence: campaigns/xswap-mthp-reassembly-2026-11-06/ledger/ledger.json, campaigns/xswap-mthp-reassembly-2026-11-06/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| edc1ee76e7d94a64a01ec371b5a8944f |  | probe | CALIBRATED |
| 0af203f743bf4038a97bf4ffa9e11f2c | xswap-mthp-reassembly-v1 | probe | PROBE_PASS |
| 4d9b2ef33400429c9d774adc8c5f86a2 |  | fast | CALIBRATED |
| 8f4c32b846084f769aae5dd2e5cd83f1 | xswap-mthp-reassembly-v1 | fast | REGRESSION |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
