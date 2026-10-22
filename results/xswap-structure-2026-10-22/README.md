# Structural xswap campaign 2026-10-22

Status: preparation and observation-baseline build in progress. No candidate
performance result or promotion exists yet.

## Contract

The owner authorized autonomous closed-loop structural development for this
session. The execution window is 2026-10-22 08:05–16:05 UTC. The frozen
reference is Phase I v4 + Phase II v1 with read-only topology diagnostics:
`4f83412c1d59eaf6a4d2460cb47fe0177a3be0c4`.

The primary metric is mapped clusters after the first pressure/read/settle
cycle. Mechanism observations distinguish nonempty clusters, free descriptors,
highest occupied and shrink-blocking positions, and virtual cache-only versus
PTE-referenced slots. A second pressure cycle is diagnostic, after the primary
measurement. Latency, workload duration, data integrity, COW, live destroy,
swapoff and backend activity remain visible guardrails.

The [protocol](../../benchmark/xswap-structure/protocol.json) freezes 8 A/A boots,
10 paired comparisons per backend for each evaluated candidate, 96 total guest
attempts, at most 4 candidates and 8 builds. The actual guest allowance supports
at most two full candidate comparisons after calibration. Resource bounds remain
4 build jobs, one 4-GiB/two-vCPU guest at a time, an 8-GiB private disk, 600-second
guest timeout and 900-second build timeout. Stop before further launches when
free storage falls below 80 GiB.

The [policy](../../evolve/control/campaigns/xswap-structure-2026-10-22/policy.json)
allows a coherent structural patch series across the xswap allocation,
metadata, lookup and teardown paths. Every changed lifetime assumption requires
review before runtime. STOP, deadline, correctness failure, provenance failure
or exhausted resources stops the affected experiment.

## Initial hypotheses

1. Read-only topology observations can identify whether retained mappings
   contain high referenced slots, cache-only slots, or empty off-list blockers.
   Confidence: high for observability feasibility; runtime evidence pending.
2. A repeated pressure cycle may release cache-only blockers. Confidence: low.
   Persistent high referenced positions would change the diagnosis.
3. Low-first allocation may reduce high-slot placement without changing descriptor
   lifetime. Confidence: low for benefit; increased global-lock work is a cost.
4. Interior descriptor-page reclamation may recover capacity below pinned high
   slots. Confidence: medium for structural opportunity; mapping-aware walkers,
   whole-page groups, allocation publication and RCU draining must be designed
   before a runtime prototype.

## Limits

This is discovery. The original campaign remains historical. New instrumentation
can change timing, so comparisons use the same instrumented baseline. A rolling
per-cluster scan is not a device-wide atomic snapshot. Formal performance
acceptance remains disabled; missing matrix coverage is listed in the protocol.
Nothing is published, merged into main, or promoted automatically.

## Evidence

- Observation patch: controller campaign `xswap-observe-2026-10-22`, candidate
  `xs-observe-v1`; scope, diff and checkpatch passed.
- Runtime evidence belongs in `benchmark/xswap-structure/{runs,evaluations}`;
  controller records in `evolve/control/state/xswap-structure-2026-10-22`;
  OpenEvolve records in `evolve/xswap-structure/state-layout-v1`.
- Detailed local logs and machine-specific paths remain ignored runtime artifacts.
