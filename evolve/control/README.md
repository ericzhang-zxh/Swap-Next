# Candidate controller

`controller.py` creates candidate worktrees from the frozen seed, keeps them
inside the allowed files and line budget, and runs static checks. It never
executes candidate code. Run it from the repository root on the Linux worker.

```sh
python3 evolve/control/controller.py [--campaign <c>] doctor | status | protocol
python3 evolve/control/controller.py [--campaign <c>] new <name> --hypothesis '<...>'
python3 evolve/control/controller.py [--campaign <c>] check <name>     # scope, git diff --check, checkpatch
python3 evolve/control/controller.py [--campaign <c>] close <name> --reason '<decision>'
python3 -m unittest discover -s evolve/control/tests -v
```

- **Policy**: `config/policy.json` is the base policy. A named campaign uses
  `campaigns/<c>/policy.json`. Each candidate's worktree is
  `worktrees/[<c>/]<name>`.
- **State**: runtime state lives in the ignored `state/[<c>/]`.
  `touch evolve/control/state/STOP` halts new controller stages and the
  runners' owned builds and guests.
- **Acceptance**: `analyze` implements the [formal acceptance protocol](METRICS.md).
  It is disabled until that protocol's gates and calibration exist.

Rules: [PRINCIPLES.md](PRINCIPLES.md) (boundaries and invariants) and
[CODE_PATTERNS.md](CODE_PATTERNS.md) (kernel code taste and review).
