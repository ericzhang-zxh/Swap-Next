# Research decision: stop after noisy baseline calibration

**Inconclusive. Keep the baseline and retain the unmerged candidate.** The source-level optimization is established, but no paired candidate performance measurement was reached. No supported complete latency result exists for the session value command; this engineering decision records the missing evidence instead of fabricating a value record.

## What was learned

| Claim | Evidence | Confidence | What would change it |
| --- | --- | --- | --- |
| Eligible demand allocation removes one preliminary locked check | Exact-tree independent review and retained patch | High | A reachable caller or lifetime counterexample in the exact tree |
| Baseline and candidate passed the required bounded correctness route | Two counted xswap/disk correctness guests; every run gate passed | High for this route | A reproducible data, concurrency, COW or teardown failure |
| Baseline metadata calibration failed its frozen stability gate | All nine calibration guests valid; three metadata samples below | High | A separately authorized, valid new calibration under a capable measurement design |
| Candidate latency benefit and regression risk remain unmeasured | No candidate probe, no fast calibration and no B/C pairs | High | Complete future paired evidence with passing calibration and guards |

The metadata measurement is the guest-wide MemAvailable loss across swapon, divided by capacity slots. It is a proxy, not allocator-specific accounting. Its spread cannot be attributed to this candidate: all samples use the baseline, and the plain brd metadata case does not exercise the demand allocation change.

| Sample | Bytes per capacity slot |
| --- | ---: |
| Baseline metadata run 1 | 0.123199463350 |
| Baseline metadata run 2 | 0.115219116640 |
| Baseline metadata run 3 | 0.115219116640 |

Relative range / median: **6.9262%**; frozen limit: **1%**. All failed and successful evidence is retained. No threshold changed and no calibration was repeated.

## Value and upstream context

The frozen useful-effect threshold was 5% beyond calibrated noise, with passing scored guards. The primary metric was sequential swap-in mean latency; random mean latency was a guard and p99 advisory. This campaign cannot evaluate that threshold.

The upstream universal-precheck algorithm is already present in the experimental xswap baseline. Its author explicitly valued avoiding wasted large allocations and stale readahead work. The candidate narrows the exception to demand order-0 allocation. No separate pristine-upstream or B/P arm was measured; original upstream object ancestry remains unavailable locally. See [upstream-context.json](upstream-context.json).

The candidate adds no persistent state, interface or tunable and retains the authoritative lock and rollback. It introduces a branch, permits transient unnecessary allocation, and widens an existing ENOMEM/cache-fill race. The required future allocation-failure test increases the maintenance burden relative to the initial proposal. With no demonstrated latency gain, those obligations are not justified for adoption. The simpler current choice is to keep the baseline.

## Coverage and limits

Fresh evidence: two kernel builds, one trusted guest-image preparation, two correctness guests and nine baseline calibration guests. Reused measurements: none. Existing cache/build/calibration inputs were absent, stale or scientifically mismatched. Exact correctness and static proof identities are linked from [PREPARATION.md](PREPARATION.md).

The protocol is revision 6 TCG with 4 vCPUs, 4096 MiB RAM and 16 GiB scratch swap. It supplies no KVM inference. Runtime correctness covers anonymous base-page roundtrip, shared-entry concurrent faults, COW and live teardown. Shmem, THP, memcg limits, forced allocation/I/O failure, KASAN, KCSAN and lockdep are uncovered. No sparse result is claimed. The exact cause of the guest-wide metadata variation remains unknown.

## Resource and continuation decision

Consumed **11 / 120 guest attempts** and **3 / 10 build reservations**, including invalid or auxiliary work (there were no invalid guests). Execution budget elapsed to closure: **24.30 minutes / 18 hours**. Preparation and report delivery time are separate from that controller clock. The machine claim is released; execution is closed. No slow tier or promotion occurred.

A future run should first establish a repeatable metadata measurement under a newly approved design, then evaluate the retained candidate and its allocation-failure tradeoff. The more invasive synchronous-I/O idea remains untested. Starting another optimization with this failed calibration would provide no useful comparison.

## Framework completion

The real run exposed an over-specific baseline artifact label and a report path issue. Targeted repairs preserve exact source/configuration pins and all numerical gates. Report rendering now exposes calibration-only metadata samples and pins source links to committed bytes. The mutable PID-bound session stays local; scientific ledgers, reservations and immutable closeout remain public records. All required framework suites passed; skipped parser fixtures and the empty kernel unit-test collection remain explicit in [final-framework-tests.json](final-framework-tests.json). These software checks are separate from the real guest evidence.

[Public runtime summary](public-runtime-summary.json) · [Independent source review](independent-review.md) · [Explainer](explainer.html)
