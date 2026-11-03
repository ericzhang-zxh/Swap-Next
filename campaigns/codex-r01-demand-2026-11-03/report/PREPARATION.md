# Independent demand-cost pilot preparation

Contributor: codex-research-01. Source checkout: 5b29a4a56918d27df64af9700043a1fd8b9ce52f.

## Hypothesis and alternatives

The baseline performs preliminary and authoritative locked swap-cache validation around folio allocation. Test only order-0 calls with a fault context. Preserve large-folio/speculative prechecks, authoritative lifetime lookup, count/type checks, publication, memcg charging and rollback.

The upstream author argues the precheck avoids wasted large allocations and stale readahead. That is the counterargument, not support for a guaranteed win. Its algorithm is already the baseline. See the line agenda for pinned provenance and frozen value criteria. Previous readahead candidates were rejected; this experiment does not continue them.

## Measurement and reuse

Use the approved revision 6 TCG numeric parameters unchanged on hurricpc, with new calibration. Plain KVM revision 4 cannot provide full correctness; no new KVM protocol is invented. The reference cache is absent. Existing baseline builds have stale input-config hashes; none supplies the required current build. Historical A/A is expired and on a different machine; the retained revision 6 probe calibration also failed its metadata spread gate. No prior samples are new observations.

Build-label validation incorrectly fixed the artifact location to kb-xs-desc-v1. The targeted repair permits a safe independent build label while keeping the exact baseline commit and configuration checks. Regression tests cover an independent label, unsafe names and a changed source commit. Old build artifacts remain untouched.

## Coverage and stopping

The protocol observes first-access latency and metadata, not per-operation lock cost or failed allocation count. Structural review must establish the reduced work; real correctness and paired latency remain mandatory. Stop on failed gates, unresolved provenance, STOP or budget. A calibration failure ends this attempt without threshold changes or blind reruns. No slow tier or promotion is authorized.

## Implementation and review update

Candidate `codex-r01-precheck-v1` is commit `4068681982a044debd290884719e9bdbd4ac5ba9`, tree `912225c401b2df2c160479533f0d9c961b06771c`. Its single-file change adds 14 lines and removes 13. The independent review is retained in [independent-review.md](independent-review.md), with an immutable exact-tree pass and structural proof. It supports bounded execution.

The frozen proposal described the test burden as unchanged. Review identified an additional validation obligation: allocation-failure injection under cache contention. A competing publisher can fill the cache before this fault allocates; skipping the precheck widens the existing window in which allocation failure returns ENOMEM despite a usable cached folio. This is a real tradeoff with unknown frequency. Existing correctness covers anonymous order-0 roundtrip, concurrent faults, COW and live teardown; shmem, THP, memcg-limit and forced allocation/I/O failure remain uncovered. A later value judgment must account for this obligation rather than inheriting the initial complexity estimate unchanged.

Both baseline and candidate were freshly built with the current pinned configuration. Each passed one counted real xswap/disk correctness guest. The candidate passed every runtime gate. No KASAN, KCSAN, lockdep, sparse or failure-injection result is claimed.

Framework regression checks also found that two patch-path string literals were rejected by the repository path guard. Explicit campaign-directory path composition repairs those references without changing report contents or scientific measurements. The targeted build-label and path repairs are commit `d135174`; full checks and the repaired-suite reruns are retained in [framework-tests.json](framework-tests.json).
