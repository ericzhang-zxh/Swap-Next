# Swap Next binding

Read these paths in the current checkout; this reference is not a replacement
for their live policy. Run all kernel/sparse work on the user's designated Linux
worker over SSH, including builds and VM execution. Keep the pinned linux/
checkout clean. Project-authored artifacts are English.

## Ownership and authoritative inputs

- evolve/control/: candidate controller, scope, formal analysis, campaign state.
- evolve/kernel/ and evolve/xswap/: OpenEvolve selection and feedback adapters.
- evolve/openevolve/: pinned upstream submodule; our controller is not an
  OpenEvolve fork. Inspect the gitlink and installed import path.
- benchmark/: trusted build/guest/evaluation code, configs, workloads and protocols.
- results/ and patches/: historical observations and independently based patches.

For upstream completeness questions, start with patches/xswap-reference/README.md
and results/xswap-2026-10-21/review.md for source provenance and measured limits,
then verify the relevant current upstream discussion or author branch. A historical
Phase I/II snapshot does not establish what its authors still intend to complete.

Read AGENTS.md, evolve/control/{PRINCIPLES,CODE_PATTERNS,RUNBOOK}.md,
the selected control policy, benchmark/README.md, benchmark/settings.json,
and benchmark/<suite>/protocol.json. For a new environment also read
benchmark/SETUP.md. settings.json is a recorded inventory, not runtime overrides;
validate_settings.py checks source fingerprints, not runtime correctness.

Base policy is evolve/control/config/policy.json. Named campaigns use
evolve/control/campaigns/<campaign>/policy.json. Controller and adapter budgets
may count different things (an imported reference can consume a controller
record without being an evaluated candidate); reconcile both, never pick the
larger allowance. Formal runtime/acceptance flags being false must not be changed
to make a pilot acceptable. An explicitly authorized discovery pilot is a
separate, bounded route, not full formal acceptance.

## Commands and their actual effects

Run commands from the superproject root, using the documented Python environment.
The block below illustrates individual operations, not an unconditional runnable
sequence; it uses the named xswap route. A placeholder is not a suggested campaign name.

```sh
python3 evolve/control/controller.py --campaign <campaign> status
python3 evolve/control/controller.py --campaign <campaign> protocol
python3 benchmark/validate_settings.py
python3 evolve/control/controller.py --campaign <campaign> new <candidate> --hypothesis '<mechanism and test>'
# Implement and commit only the allowed candidate worktree changes.
python3 evolve/control/controller.py --campaign <campaign> check <candidate>
evolve/.venv/bin/python evolve/xswap/loop.py evaluate --candidate <candidate>
evolve/.venv/bin/python evolve/xswap/loop.py next
python3 evolve/control/controller.py --campaign <campaign> close <candidate> --reason '<decision and evidence>'
```

Use the unnamed controller only for the base kernel suite. Named campaign
selection belongs before the controller subcommand. The adapter has NO
--campaign option: it reads benchmark/<suite>/protocol.json. Ensure its campaign
and baseline match the controller before evaluation.

xswap/loop.py calibrate performs real A/A builds/boots and writes a calibration
report; it is not a read-only check. It is required before xswap candidate
evaluation with matching suite hashes. The kernel adapter has no calibrate
command and lacks A/A support; do not invent that interface or claim equivalence.
loop.py status creates its ignored state directory but launches no experiment.
loop.py next writes a selection/task brief; it does not start a model worker.
The active assistant proposes and executes the next authorized round.

The dated xswap-2026-10-21 protocol is historical: it completed three candidate
trials, has a fixed deadline and has been followed by harness relocations.
Do not restart it from an empty relocated search database. Its A/A had large
metadata-state variation. Fresh layout checks do not revalidate it.
A new authorized campaign needs a distinct policy, budget and frozen protocol
binding, fresh baseline/initrd evidence and calibration. The existing adapter
uses one protocol file per suite; switching campaigns is a deliberate preparation
step with prior evidence preserved, not an imaginary CLI flag.

## Resume and evidence

Controller records: evolve/control/state/[<campaign>/]candidates.json.
Search records: evolve/<suite>/state-layout-v1/{ledger.json,database/}.
Benchmark reports: benchmark/<suite>/evaluations/<evaluation-id>/report.json.
Xswap calibration: benchmark/xswap/state-layout-v1/calibration.json.
Xswap attempts: benchmark/xswap/state-runtime-layout-v1/attempts.json.
Shared guest lock: benchmark/kernel/.runtime.lock.

Historical Evolve/ artifacts remain local archives. Controller state was moved
to evolve/control/state/ without rewriting the recorded protocol hashes.
Inspect archives when reconciling a resumed task; never import historical
calibration as fresh evidence or clear an old ledger to obtain a new budget.

Global STOP is evolve/control/state/STOP; the xswap runner also checks its
campaign STOP. These sentinels govern owned processes, not arbitrary host jobs.
A build/VM cannot be assumed stopped merely because the tool call ended.

Static and parser checks use:
```sh
python3 -m unittest discover -s evolve/control/tests -v
python3 -m unittest discover -s benchmark/tests -v
python3 -m unittest discover -s benchmark/xswap -v
```
Supply XSWAP_EVIDENCE_FIXTURE for its real-evidence tests. Legacy kernel tests
use SWAP_NEXT_EVIDENCE_FIXTURE. Missing fixture classes explicitly skip.
Neither synthetic tests nor replaying old raw logs are fresh guest validation.
Use .agents/skills/kernel-patch-review/SKILL.md for kernel patch review;
do not add AI Signed-off-by trailers. Publishing raw evidence or patches remains
subject to the user's existing authorization and the repository's privacy rules.
