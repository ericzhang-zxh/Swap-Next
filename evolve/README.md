# OpenEvolve adapters

This directory owns the pinned OpenEvolve dependency and proposal/feedback loop
adapters only. Builds, workloads, protocols, parsers and evidence belong to
[benchmark](../benchmark/README.md). Candidate scope and formal acceptance
belong to [system](../system/README.md).

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
