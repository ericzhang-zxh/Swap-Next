# Residency-aware swap-in experiments

Both candidates were screened out. H1 reduced disk sequential mean latency by 84.69% but increased random p99 by 10.50%. H2 changed zswap sequential mean by -0.41% and increased sequential p99 by 280.79%. These two-pair screening results block slow confirmation.

- [Published interactive report](https://ericzhang-zxh.github.io/Swap-Next/xswap-swapin-2026-10-23/)
- [Full report](REPORT.md) and [public data summary](summary.json)
- [Pinned experiment evidence and provenance](https://github.com/ericzhang-zxh/Swap-Next/tree/23f13a766e4df884ffee2ef5e1379c45e80e54c8/results/xswap-swapin-2026-10-23)
- [Pinned candidate patches](https://github.com/ericzhang-zxh/Swap-Next/tree/23f13a766e4df884ffee2ef5e1379c45e80e54c8/patches/xswap-swapin)

This commit publishes the completed report only. Candidate code, benchmark changes and live runtime state remain on the experiment branch. All 12 final correctness cases and three KASAN lifetime stress runs passed; 46 total guest attempts include four retained pre-calibration harness failures. Coverage gaps and uncertainty are retained in the report.
