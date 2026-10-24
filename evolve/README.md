# Evolution workflow

- `loop.py`: the OpenEvolve adapter for every suite. Benchmarks live in
  [benchmark](../benchmark/README.md).
- [control](control/README.md): candidate controller, scope policies,
  formal acceptance analysis (disabled), and tests.
- `openevolve/`: unmodified upstream submodule at `59dfe764` (Apache-2.0).
  `requirements.snapshot.txt` installs it in editable mode.

```sh
evolve/.venv/bin/python evolve/loop.py <kernel|xswap|xswap-structure> status
evolve/.venv/bin/python evolve/loop.py <kernel|xswap|xswap-structure> next
evolve/.venv/bin/python evolve/loop.py <kernel|xswap|xswap-structure> evaluate --candidate <name>
evolve/.venv/bin/python evolve/loop.py <xswap|xswap-structure> calibrate
evolve/.venv/bin/python evolve/loop.py swap-standard calibrate --tier fast
```

State per suite lives in `evolve/<suite>/state-layout-v1/`: the database,
ledger, selection RNG and task briefs. The xswap calibration report goes to
`benchmark/xswap/state-layout-v1/calibration.json`, where its evaluator reads it.

`next` samples a reference and inspirations from the archive and writes a
brief. The assistant in the session proposes and implements the candidate.
No background model worker runs. All candidates are currently based on
the frozen seed, so sampling does not yet shape lineage; see
[DESIGN.md § Where OpenEvolve fits](../DESIGN.md#where-openevolve-fits).

For campaign preparation, recovery and stop decisions, use the
[closed-loop-evolve skill](../.agents/skills/closed-loop-evolve/SKILL.md).

The `swap-standard` suite adds `--tier fast|slow|auto`, `plan`, and a fast-only
`reference-check`. See [the tier contract](../benchmark/swap-standard/README.md#evolve-tiers).
It reuses the controller and OpenEvolve reference database, with a directly
supervised evaluator to enforce subprocess lifetime and preserve interrupted
attempts. Only measured slow results eligible for human review become references.
