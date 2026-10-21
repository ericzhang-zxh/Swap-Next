# Candidate control system

This directory is separate from the pinned `linux/` submodule. Run commands from the superproject root.

```sh
python3 evolve/control/controller.py doctor
python3 evolve/control/controller.py status
python3 evolve/control/controller.py protocol
python3 -m unittest discover -s evolve/control/tests -v
python3 evolve/control/controller.py new trial-001 --hypothesis "A concrete optimization hypothesis"
```

The controller creates `worktrees/trial-001` from the public upstream SHA in `config/policy.json`. Implement one allowed change and commit it in that worktree, then run `python3 evolve/control/controller.py check trial-001`. Check runs only scope checks, `git diff --check`, and upstream checkpatch. It does not execute candidate code. Candidate creation expects the pinned Linux checkout to be clean.

[../../benchmark/SETUP.md](../../benchmark/SETUP.md) describes the separate isolated-build/KVM pilot. Full statistical acceptance is disabled; all findings require review. Runtime state lives under ignored `evolve/control/state/`. `touch evolve/control/state/STOP` blocks new controller stages and tells the pilot runner to stop its owned build/guest processes. Close a completed candidate with `python3 evolve/control/controller.py close trial-001 --reason 'archived; not promoted'`; its worktree and evidence remain.

See [PRINCIPLES.md](PRINCIPLES.md), [METRICS.md](METRICS.md), [CODE_PATTERNS.md](CODE_PATTERNS.md), [RESULT_FORMAT.md](RESULT_FORMAT.md), and [RUNBOOK.md](RUNBOOK.md). Policy v1 and the benchmark pilot have different scopes: a successful pilot is never full v1 acceptance.
