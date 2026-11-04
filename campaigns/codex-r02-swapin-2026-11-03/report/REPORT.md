# Can a cold swap-in skip a repeated lookup?

**inconclusive** — Inconclusive: baseline calibration failed before candidate runtime testing. Retain the patch; diagnose measurement stability next.

## A small repeated cost on every cold fault

Restoring a swapped page pauses the application. The caller already missed the cache, yet the synchronous helper looks again before an allocator that performs its own locked checks.

Hypothesis: remove the repeated cold-path lookup. Source review passed; the candidate was not built or booted. Fresh baseline correctness passed, but unstable metadata calibration stopped runtime evaluation.

Evidence: campaigns/codex-r02-swapin-2026-11-03/research.json, campaigns/codex-r02-swapin-2026-11-03/patches/codex-r02-alloc-first-v1.patch

## From a paused application back to resident RAM

Schematic system view: page contents return from disk or compressed RAM. The highlighted cache path is shared; storage and decompression remain unchanged.

Evidence: campaigns/codex-r02-swapin-2026-11-03/research.json, campaigns/codex-r02-swapin-2026-11-03/protocol.json

## Zoom into the synchronous cache-miss path

Anonymous and shmem callers first look in the swap cache. On a miss, the helper enters an allocator with checks before and after allocation.

Evidence: campaigns/codex-r02-swapin-2026-11-03/patches/codex-r02-alloc-first-v1.patch, campaigns/codex-r02-swapin-2026-11-03/reviews/codex-r02-independent-v1.json

## Before and after: move lookup onto the raced-hit path

One independent candidate changes only the helper loop. Cold success skips its repeated lookup; a raced cache hit pays the allocator's lock before fetching a reference.

Evidence: campaigns/codex-r02-swapin-2026-11-03/patches/codex-r02-alloc-first-v1.patch, campaigns/codex-r02-swapin-2026-11-03/reviews/codex-r02-independent-v1.json

## Resolve the measurement gate before another trial

Every fresh probe guest was valid, while metadata stability failed. Candidate latency, runtime correctness and formal acceptance coverage remain open. The closed campaign launched no replacement measurement.

Candidate scope and independent review passed. Baseline runtime passed; candidate build, boot, shmem, large-folio and failure-path coverage did not run. Preserve these limits and the failed calibration with the patch.

Evidence: campaigns/codex-r02-swapin-2026-11-03/ledger/ledger.json, campaigns/codex-r02-swapin-2026-11-03/ledger/budget.json, campaigns/codex-r02-swapin-2026-11-03/ledger/session-closeout.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| a097eaa148a34678ad8f32675bf1624d |  | probe | CALIBRATION_NOISY |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
