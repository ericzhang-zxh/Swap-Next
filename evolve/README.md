# Evolution workflow

- `loop.py`: the OpenEvolve adapter for every suite. Benchmarks live in
  [benchmark](../benchmark/README.md).
- [control](control/README.md): candidate controller, scope policies,
  formal acceptance analysis (disabled), and tests.
- `openevolve/`: unmodified upstream submodule at `59dfe764` (Apache-2.0).
  `requirements.snapshot.txt` installs it in editable mode.

```sh
evolve/.venv/bin/python evolve/loop.py <kernel|xswap> status
evolve/.venv/bin/python evolve/loop.py <kernel|xswap> next        # write a proposal brief
evolve/.venv/bin/python evolve/loop.py <kernel|xswap> evaluate --candidate <name>
evolve/.venv/bin/python evolve/loop.py xswap calibrate             # A/A boots; xswap only
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
