# Evolution workflow

This directory owns candidate control, search adapters, and the pinned OpenEvolve
source dependency. Builds, workloads, protocols, parsers and measurement evidence
belong to [benchmark](../benchmark/README.md).

- [control](control/README.md): our controller, policies, acceptance analysis and tests.
- `kernel/` and `xswap/`: our proposal/feedback adapters.
- `openevolve/`: unmodified upstream Git submodule at
  `59dfe764b5ab4478ac00214432fcac33bbe2bf4b` (Apache-2.0).

Previously the requirements snapshot fetched the same OpenEvolve revision through
a Git URL. The submodule now makes that source visible in this checkout; the
snapshot installs it locally in editable mode. No OpenEvolve version upgrade is
implied. Run installation from the repository root after initializing the submodule.
Our controller remains separate code and is not an upstream OpenEvolve modification.

Install the snapshot into evolve/.venv as described in
[benchmark setup](../benchmark/SETUP.md), then use:

```sh
evolve/.venv/bin/python evolve/kernel/loop.py status
evolve/.venv/bin/python evolve/kernel/loop.py next
evolve/.venv/bin/python evolve/xswap/loop.py status
```

Each adapter keeps its database, ledger, selection RNG and task briefs under
evolve/<suite>/state-layout-v1. The xswap calibration report is explicitly
written to benchmark/xswap/state-layout-v1/calibration.json for its evaluator.
Archived Evolve runtime is never searched or imported. There is no unattended
model worker, automatic merge, or promotion. The dated xswap deadline remains
frozen; relocation does not authorize another campaign.
