# Evolution review and implementation corrections

Status: reviewed 2026-10-27. The owner selected: neutral candidates may remain
exploratory parents; cross-campaign baseline advancement needs improvement
beyond calibration noise, and each line preserves its original anchor.
This amends the [approved framework design](2026-10-27-campaigns-cascade-evolution-design.md).
Framework implementation and guest-free checks are authorized. No experiment,
calibration, guest boot, kernel build or image rebuild is part of this work.

## Findings and resolutions

| Finding | Evidence | Confidence | Resolution |
|---|---|---|---|
| A fast pass admits neutral or slower candidates inside the noise envelope. | The pure analysis function admits 100 ns to 120 ns with a calibrated 25% envelope, score 0.8333. | High | Keep exploratory admission separate from advancement. Require all scored guards and normalized improvement above the largest primary noise envelope to advance; retain the line anchor. |
| A child can inherit a parent's mechanism signal without adding a contribution. | Baseline-only probes compare both parent and child to the same band. | High | Keep cumulative comparisons and separately report descriptive parent-to-child deltas. Neutral exploration remains valid; label its evidence accurately. |
| Commit-only attempt identity permits identical code to receive another screen. | An empty child commit has a new SHA but the parent's tree and cumulative patch. | High | Require a changed child tree; deduplicate source trees within the measurement identity, preserving prior failures. |
| The proposed default population exceeds the cap. | 39 probe guests plus 88 latency guests is 127 before correctness or reruns; reserved pools total 133. | High | The revision 4 template uses at most eight probe and two screened candidates, pools 36 + 84 = 120. Minimum performance guests are 33 + 72 = 105; the remaining 15 cover auxiliary correctness and validity attempts. Ceilings do not promise all candidates can finish. Pair counts and measurements stay approved. |
| Plain-mode full correctness is unsupported by the existing guest. | `bench.sh` rejects plain correctness; `correctness.c` uses xswap interfaces. | High | Keep revision 4 as a non-executable template and make the runtime capability gap explicit. No wrong-mode proof or fabricated gates. A future plain correctness adapter is separate work. |
| A shared layout marker cannot prove every machine's local evidence was imported. | Grok pulls `MOVED.json` before importing its ignored ledger. | High | Keep idempotent layout migration and add explicit per-machine `import-state`, private receipts, preflight conflict checks and resumable journals. |
| Closed reads and ownership recovery need explicit semantics. | Review reproduced ledger mutation by status initialization and no supported reclaim after release. | High | Closed reads perform no stored recovery or lock/task writes; add resume preserving budgets, deadline and STOP. Serialize claims and check ownership at each execution entry. |
| Direct guests can bypass adapter accounting. | Standalone runner formerly checked ownership without reserving a guest. | High | Reserve under the shared budget lock before launch; the runner consumes one exact, single-use reservation. Auxiliary correctness uses the same service. Failed attempts stay spent. |
| Archive membership outlives weaker or stale evidence without an eligibility rule. | The initial design updates slow results but does not invalidate parent eligibility. | High | Retain immutable evidence history; correctness failure, slow regression and stale fingerprints remove active parent eligibility. |
| A resumable evolution loop needs durable proposal identity. | Reconstructing a seeded sampler can repeat choices and an unrecorded brief cannot constrain the actual parent. | High | Track sampling sequence, brief ID, exact permitted parent and actual choice. Include relevant older failures as well as recent outcomes. |

The observation that would change each high-confidence finding is a concrete
counterexample in the affected pure function, fixture or guest-free lifecycle
check. Real performance effects require separately authorized measurements.

## Selection contract

1. Probe confirms a declared cumulative mechanism and metadata guards.
2. The agent records why a probe pass enters the latency screen.
3. `FAST_PASS` enters the exploratory population. It remains screen-only.
4. A neutral exploratory parent is allowed. A child changes that parent's
   source tree and is scoped against the fixed campaign baseline.
5. Advancement additionally requires normalized aggregate improvement greater
   than one plus the largest calibrated primary noise envelope and all scored
   guards passing, under the exact current measurement identity. The source
   evidence, baseline and line anchor remain recorded. Root-to-descendant
   performance is not fabricated from incompatible runs.
6. New failures invalidate eligibility, while historical successes, patches
   and failure explanations remain available for inspection and inspiration.

## Delivery checks

Use the project's prescribed guest-free tests and a complete fixture lifecycle:
probe to fast result, population admission, durable brief, changed child,
cumulative scope, child outcome, invalidation and restart. Verify copied/moved
bytes and frozen protocol hashes separately from report-link rewrites. Build
Pages and verify unchanged published URLs after migration. No successful unit
test is described as a real optimization result.

## Coverage boundary

Current probe counters expose swap traffic, readahead and metadata. They can
miss improvements that keep those counts constant, such as reduced locking or
CPU cost. Treat that as a measurement coverage gap when proposing candidates;
new trusted instrumentation requires a separate measurement revision. The first
loop does not claim to cover every architecture or workload.
