# C1 runtime incident 006: unproven compressed timing sample

Status: R5 closed by the durable session after the first probe-calibration guest failed. No retry was launched.

## Verified result

The unchanged shared-library candidate 7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad completed all eight required correctness guests and both disabled-configuration builds in R5. The native correctness manifest is pinned at campaigns/codex-compress-lib-r5-2026-11-10/candidates/c1-shared-store-r5/correctness.json. This is the C1 functional dependency result.

The first baseline compressed timing guest printed SWAPIN_FAIL compressed_decode_unproven and BENCH_FAIL workload before any complete latency sample summary. The stored result has integration_pass=false, parse_complete=false, qemu_exit=true and run_valid=true. QEMU exit and environmental validity are separate from workload success.

The raw log records 32,713 swapped target pages out of 32,768 and 32,756 total stored pages, with no physical backing. It contains no failed-sample trace dump. These observations locate the failure at the observer acceptance check; they do not establish the exact missing, duplicate or malformed trace cause. The independent H25 source diagnosis is a separate artifact.

## Evidence and costs

| Artifact | SHA-256 |
| --- | --- |
| Failed result | 062011b64633567f5d4546129c385c14536e2c2121bb5b9f03eedd0bffbb51fb |
| Failed serial | 5018cc8eddbe54aa8aee59baf90272b23f08bab15259004ce10fa91f454502ed |
| Runtime archive | 5a385e3b3ebae82697d0917b4be8607aa736fd812c243be4e8c009ac1f33e041 |
| Complete correctness manifest | f53bf3552546426a382657f4580d5b25bd25287e74fb032873da8ba8246d45cd |

R5 spent nine probe guest attempts, no fast guests and five new builds. Original C1 plus R2 through R5 spent nineteen guests and nine builds within the single logical phase's 120-guest/10-build ceiling. The four earlier frozen ledgers and all failed attempts remain intact. No measured speed, equivalence, fast pass, baseline advancement or promotion follows from this closeout.

## Decision

Retain the completed functional proof and the failed calibration as distinct outcomes. Continue preparing the separately authorized C2 capability against the original anchor, with K1 as exact predecessor provenance. C2 must use its own reviewed observer contract, fresh calibration and complete independent correctness coverage. A bounded first-failure trace diagnostic is required before attributing this timing failure to a specific observer cause.
