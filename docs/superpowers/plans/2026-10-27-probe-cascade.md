# Probe cascade implementation plan

Part 2 of the approved framework, amended by the evolution review. Run only
on the Linux worker; tests are guest-free. Keep old protocols byte-identical.

1. Add pure probe band, signal validation and metadata analysis in
   `benchmark/swap-standard/probe.py`, with finite/missing/noisy cases tested.
2. Add mechanism parsing to controller candidate creation. Require the policy's
   explicit signal declaration; validate case/key against the frozen protocol.
3. Add probe calibration and candidate evaluation to the standard workflow.
   Use separate pools, exact source-tree/commit/fingerprint identities,
   current probe evidence before fast and an agent-supplied selection reason.
   Retain invalid and interrupted attempts. Never auto-admit to fast.
4. Add revision 4 KVM validity without changing revision 3's TCG rules.
   Keep probe run counts distinct from latency pair counts. Pin child settings.
5. Add the non-executable revision 4 template with 36 probe and 84 fast guest
   ceilings, eight probe and two fast candidates. Keep missing plain correctness
   capability explicit. Open no campaign and launch no workload.
6. Add resume ownership recovery and counted reservation integration. Preserve
   existing deadlines, budgets and STOP. Every runner launch consumes its ticket.
7. Run focused tests, then the full project checks. Return a commit and concise
   evidence. Primary integrates population hooks and the full fixture lifecycle.
