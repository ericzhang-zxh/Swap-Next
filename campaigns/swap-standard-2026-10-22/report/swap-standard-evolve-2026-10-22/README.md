# Standard benchmark evolve integration — 2026-10-22

The framework now records fast/slow calibration and comparison evidence. No candidate performance winner is established. Confidence: high; a verified candidate comparison with complete correctness gates would change this conclusion.

Fast A/A rejected: maximum multiplicative usemem throughput difference is 63.2% and free-latency difference is 43.4%, exceeding the 20% ceiling. Confidence: high; stable repeated A/A under a new frozen protocol would change the noise finding.

| Action | Tier | Recorded status | Runs |
|---|---|---|---:|
| calibrate | fast | CALIBRATION_NOISY | 12 |
| calibrate | slow | INCOMPLETE | 2 |
| reference-check | fast | INCOMPLETE | 0 |
| evaluate | fast | BLOCKED | 0 |

Retained run attempts: 14 (13 completed, 1 interrupted/incomplete). Completed-run guest gates: 150/150; failed observations: 0. The 1 interrupted run has no finalized result and contributes no passing gates. Framework tests: 83 (verified count supplied by primary).

Test breakdown: 32 suite + 6 workflow + 41 controller + 4 layout = 83.

Evidence accounting confidence: high; missing ledger attempts or mismatched raw hashes would invalidate the export. Every exported raw result is checked against its recorded digest; available serial logs are checked too.

Fast A/A was rejected for noise; slow calibration stopped after one completed and one interrupted guest. Reference-check stopped at noisy-calibration preflight with zero boots; the historical candidate was blocked with zero boots. Confidence: high; differing retained terminal reports would change these statements.

Earlier integration commit 162ff75 exercised build/zswap and metadata/brd; this new slow A/A remains incomplete and supplies no repeatability result for those cases.

The flow change is orchestration: frozen inputs → paired calibration → fast admission → slow evidence → human review. No candidate kernel patch is included.

Files: [visual explainer](explainer.html), [summary](summary.json), [full sanitized evidence](evaluations.json), [explainer source](explainer.json).

## Limitations

Same-kernel A/A and reference results measure repeatability. Prior descriptor-lifetime-blocked candidates remain held where recorded. All policy candidate acceptance gates are listed as missing in the explainer; guest integration observations have a separate count. Metadata memory deltas are descriptive. No result automatically promotes a candidate.

Visual QA: both themes rendered in Chromium without horizontal overflow or JavaScript errors; top and data panels inspected. See [validation](visual-validation.json).

Campaign stopped with its STOP sentinel retained. No owned build or guest remains running. Stabilize the usemem baseline before a new calibrated comparison; the current noise evidence stays frozen.
