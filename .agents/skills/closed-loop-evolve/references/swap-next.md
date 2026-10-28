# Swap Next binding

Read current [AGENTS.md](../../../../AGENTS.md), [DESIGN.md](../../../../DESIGN.md),
the campaign record and its line history before changing or running anything.
All kernel, build and VM work runs over SSH on the Linux worker. Loading this
workflow does not start an experiment.

## Campaign ownership

`campaigns/<c>/` owns `campaign.json`, `policy.json`, immutable `protocol.json`,
`ledger/`, `candidates/`, `patches/`, `archive/` and `report/`. Raw `runs/` is
ignored. The base file allowlist stays in `evolve/control/config/policy.json`.
Historical suites retain fixed suite protocols and read-only evidence; the
migration manifest records their locations.

Write policy and protocol, then use:

```sh
python3 evolve/control/controller.py --campaign <c> open-campaign --line <line> --machine <machine>
# Recovery of an existing open campaign preserves budgets and STOP:
python3 evolve/control/controller.py --campaign <c> resume-campaign --reason '<recovery>'
evolve/.venv/bin/python evolve/loop.py swap-standard status --campaign <c>
evolve/.venv/bin/python evolve/loop.py swap-standard next --campaign <c>
```

Each machine has at most one open campaign and a serialized local claim.
Every guest requires open status, matching machine and protocol, claim, both
STOPs, remaining deadline/budget and a matching single-use reservation. To
reserve an auxiliary correctness attempt without launching it:

```sh
python3 evolve/control/guest_budget.py --campaign <c> --run-id <run> \
  --build <build> --backend <backend> --mode <mode> --workload correctness
```

Pass its reservation path and run ID to the runner. Failed setup, invalid
samples and correctness attempts remain counted. Calibration renewal and
validity reruns also consume the same campaign pools. Clearing a ledger or
starting another checkout does not reset the campaign budget.

## One feedback round

1. Read the durable brief and choose its sampled parent or the baseline. State
   the hypothesis, mechanism and falsifier. A child must change its parent's
   tree; scope is the cumulative diff against the campaign baseline.
2. Use the controller to create/check the isolated candidate, then obtain the
   required exact-commit correctness evidence. Keep mode/config/backend coverage
   explicit. Revision 4 plain full correctness is not supplied by the existing
   xswap-only guest; keep that real-run capability blocked.
3. Probe the declared signal and metadata guard under the frozen protocol.
   The agent chooses which probe passes enter fast and records why. No probe
   score auto-advances a candidate.
4. The paired latency screen admits exploratory fast passes. A neutral parent
   may be useful. Advancement requires improvement beyond calibrated noise;
   preserve the line anchor. Report parent deltas separately from cumulative
   baseline effects.
5. Update the population from the same evidence. Preserve immutable outcomes,
   source identity, fingerprints and negative knowledge. Correctness failure,
   later regression and stale identity remove active parent eligibility.

Use `--campaign <c>` on standard workflow commands. Archived source hashes and
historical protocols remain reproducible; they are not current measurements.

## Close and deliver

Use `close-campaign --reason`, which regenerates campaign/line indexes. Keep
patches and failed outcomes in the campaign directory. Generate the review page
with [explaining-campaign-results](../../explaining-campaign-results/SKILL.md)
from the same evidence: verdict first, whole system, subsystem, concrete change,
then measurements. Keep detailed data folded, limits visible, and test mobile
and both themes.

Follow the standing report-publication policy in AGENTS.md: commit to main,
build the Pages site from `campaigns`, publish and verify the exact deployment,
live campaign page and index. Keep report delivery separate from code promotion.
Only an explicit owner request keeps the report private. An experiment STOP or
exhausted budget stops execution, not authorized closeout.

The layout migration preserves frozen bytes, then rewrites report links in a
separate commit. Another machine must run `migrate.py import-state` for its own
ignored evidence. Conflicts fail before writes; local import receipts do not
come from the shared layout completion marker.

## Checks

These are the project tests that [Campaign lifecycle](../../../../AGENTS.md#campaign-lifecycle)
requires before pushing `main`.

```sh
python3 -m unittest discover -s evolve/control/tests -v
python3 -m unittest discover -s benchmark/tests -v
for suite in swap-standard xswap xswap-structure xswap-hole-probe kernel; do
  evolve/.venv/bin/python -m unittest discover -s benchmark/$suite -p 'test_*.py' -v
done
evolve/.venv/bin/python -m unittest evolve.test_standard_workflow -v
```

`XSWAP_EVIDENCE_FIXTURE` and `SWAP_NEXT_EVIDENCE_FIXTURE` enable the
real-run parser tests. These checks never boot a kernel.
