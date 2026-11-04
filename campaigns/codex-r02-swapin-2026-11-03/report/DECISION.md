# Allocation-first synchronous swap-in: retained, unmeasured

**Inconclusive. Stop this campaign.** The independent source review supports trying the candidate, but the fresh baseline metadata calibration failed. The candidate was neither built nor booted. Its latency benefit and runtime correctness remain unmeasured.

## Decision and evidence

| Finding | Evidence | Confidence | Observation that would change it |
| --- | --- | --- | --- |
| The cold successful helper path removes a repeated cache lookup | Exact candidate patch and independent review | High | A reachable cold path still executes that lookup or a preserved invariant is lost |
| The baseline correctness route passed | One fresh disk/xswap guest; all 17 gates, serial and provenance replayed | High for the tested route | A reproducible failure on the same source and route |
| The probe cannot support candidate advancement | Three metadata samples; range/median 10.01009846% against a frozen 1% maximum | High | An approved revised measurement contract with stable fresh calibration |
| Candidate performance is unknown | No candidate image, guest or paired comparison exists | High | Valid exact-candidate runtime and calibrated paired evidence |
| No useful effect can be awarded | The predeclared requirement is a resolved gain of at least 5% beyond noise | High | A qualified comparison meeting that requirement and its guards |

## What changed

The application faults on a swapped anonymous or shmem page. Its caller first checks the swap cache. On a synchronous device, a miss enters `swapin_sync()`. The baseline helper checks the cache again before calling the allocator.

The candidate calls the existing allocator first. If the allocator returns `-EEXIST`, the helper obtains a reference to the cached folio and returns it; if that folio disappeared, it retries. Both locked checks inside the allocator remain intact, including the recheck after allocation. LRU insertion, read submission and error handling retain their order.

This removes one repeated RCU-protected lookup on an uncontended cold success. A raced cache hit now pays the allocator's locked precheck before retrieving its reference. The effect on elapsed latency and contention is a hypothesis.

- Baseline and line anchor: `5e84ca928deeacb4eee656806a003f27d1eca82f`.
- Candidate: `3fe7af01da59a8ade95823a13c25a8c796c6321f`.
- Candidate tree: `0c83218561a357c129c5d93ac45a0530e0ad1df6`.
- One independent candidate, one file, seven insertions and three deletions.
- No new helper, persistent metadata, allocation, tunable or cleanup obligation.
- Parent-relative and cumulative complexity are identical because the parent is the baseline. The remaining obligation is understanding the raced-hit lock tradeoff.

The integrated upstream allocation/checking design is the control. Targeted upstream inspection found no distinct compatible unapplied allocation-first alternative; the search was not exhaustive. See [upstream context](upstream-context.json) and [independent review](independent-review.md).

## What actually ran

The approved kbench TCG revision 6 measurement parameters were retained: four vCPUs, 4096 MiB RAM and a preallocated 16 GiB swap image. The latency cases use xswap on disk and zram-64k. The brd metadata guard uses plain mode. That metadata case measures a guest-wide MemAvailable delta per capacity slot, not candidate xswap descriptor allocation directly.

| Work | Count | Outcome |
| --- | ---: | --- |
| Fresh baseline correctness | 1 guest | All required screen gates passed |
| Fresh baseline probe calibration | 9 guests | All valid; metadata stability failed |
| New kernel builds | 0 | Exact existing baseline build reused after verification |
| Candidate builds or guests | 0 | Stopped before spending them |
| Fast A/A or baseline/candidate pairs | 0 | Not reached |
| Slow confirmation or promotion | 0 | Not run |

| Plain brd metadata sample | Bytes per capacity slot | Used-memory delta, KiB | VmallocUsed delta, KiB |
| --- | ---: | ---: | ---: |
| 1 | 0.12088012740343856 | 31688 | 28744 |
| 2 | 0.112457275809561 | 29480 | 28760 |
| 3 | 0.12455749558120033 | 32652 | 28728 |

The samples' range divided by their median is **10.01009846%**; the frozen maximum is **1%**. The run-validity gates and the calibration stability gate answer different questions: every attempt was valid, while their metadata signal was too variable for this protocol.

The prior campaign also recorded a noisy metadata calibration. It is historical context only; no old sample was paired with a new observation. This campaign reused verified build/image artifacts and collected fresh runtime evidence.

## Verification and closure

The replay script validates all ten result and serial hashes, reservation bindings, build/source/config/protocol identities, retained/current harness hashes, parser outputs, validity classification, calibration analysis and budget reconciliation. See [public runtime summary](public-runtime-summary.json), [verification receipt](outcome-verification.json) and [replay script](verify_outcome.py). Raw runtime artifacts remain local and ignored.

Scope, diff whitespace and strict checkpatch passed. An independent exact-tree review found no blocking source-level issue. Framework checks completed: 541 discovered tests, zero failures, with three reported skips across the suites (the kernel fixture suite collected zero tests). These framework checks are separate from candidate kernel validation.

Execution is closed and the machine claim is released. Spending was 10 of 120 guest attempts and zero of ten new builds. The unused budget is not a mandate to retry a failed calibration. No follow-up guest, altered threshold or measurement was launched. The isolated candidate branch and patch are retained; publication is report delivery only.

## Next question

**Diagnose the metadata measurement before another candidate campaign.** A plausible confounder is whole-guest memory accounting around swap activation. VmallocUsed was comparatively stable while the scored MemAvailable-derived delta moved; this is an inference from three observations, not an identified cause.

A useful next investigation would distinguish the target metadata allocation from unrelated guest accounting and repeatability effects. The hypothesis would be weakened if direct allocation accounting varied with the scored proxy. Any change to the runner, parser, observation timing, tier cases or stability threshold needs a separately approved protocol revision and fresh calibration. This campaign's frozen files and failed result remain unchanged.

## Limitations

- Candidate compilation, boot, runtime correctness, latency and contention behavior are untested.
- Dedicated shmem, large-folio/THP, allocation/I/O failure, memcg failure and sanitizer coverage is absent. Baseline correctness covered its declared anonymous, base-page route.
- Formal acceptance gates in the policy remain open: GCC swap-on/off and zswap builds, sparse, candidate boot/data/COW/concurrent-fault/swapoff validation, failure injection, memcg/large-folio checks, lockdep, KASAN and KCSAN. Checkpatch and source review are the completed candidate checks.
- The metadata proxy's root cause is unresolved. Probe timing observations are uncalibrated baseline diagnostics.
- No held-out efficacy, upstream contrast, fast screen, slow confirmation or accepted optimization is claimed.

[Interactive explanation](explainer.html) · [Machine-readable evidence](summary.json)
