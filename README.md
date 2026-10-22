# Swap Next

A laboratory for finding Linux swap optimizations. Each candidate is a small
patch on a frozen kernel. A benchmark boots it next to the baseline in KVM, and
OpenEvolve records the outcome and selects references for the next proposal.

Start with [DESIGN.md](DESIGN.md). It covers what we optimize, the upstream
xswap roadmap, what the first campaign found, and the ranked next hypotheses.

## Layout

```text
linux/            upstream Linux submodule, pinned at 744e5400 (never modified)
benchmark/        builds, KVM runner, guest workloads, parsers, frozen protocols
  kernel/         ordinary swap suite
  xswap/          xswap suite (imported Phase I/II reference)
evolve/
  loop.py         OpenEvolve adapter: `loop.py <suite> status|next|evaluate|calibrate`
  control/        candidate controller: worktrees, scope checks, policies
  openevolve/     upstream OpenEvolve submodule, pinned at 59dfe764
patches/          experimental patches and the imported xswap reference
results/          campaign reports
```

Clone with `git clone --recurse-submodules`, or run
`git submodule update --init linux evolve/openevolve`.

## Workflow

Kernel builds and guests run on a Linux KVM worker; see
[benchmark/SETUP.md](benchmark/SETUP.md).

```sh
python3 evolve/control/controller.py --campaign <c> new <name> --hypothesis '<mechanism, expected effect, falsifier>'
# edit allowed files in worktrees/<c>/<name>, commit locally
python3 evolve/control/controller.py --campaign <c> check <name>
evolve/.venv/bin/python evolve/loop.py xswap evaluate --candidate <name>
evolve/.venv/bin/python evolve/loop.py xswap next
```

The controller keeps candidates inside the allowed files and line budget.
The evaluator runs AB/BA guest pairs on disk and zswap. A human decides
whether anything goes upstream.

## Status

- **[xswap-2026-10-21](results/xswap-2026-10-21/README.md)**: three constant
  changes, 35 guest boots, no effect detected. Retained metadata is decided by
  whether a free-tail shrink succeeds during pressure. The changes did not
  move that.
- **[Ordinary swap pilots](results/pilot-summary.json)**: 24 boots. Locked
  table-read reuse and early overflow-scan exit showed no consistent latency
  gain. An RCU simplification was rejected in review because the cluster lock
  does not establish table lifetime on the unlocked allocation path.

What the evidence cannot support is listed once, in
[DESIGN.md § Limitations](DESIGN.md#limitations).

## Provenance and license

Our code and patches are GPL-2.0-only ([LICENSE](LICENSE)). Linux and
OpenEvolve keep their own licenses. Code and reports were written with
substantial AI assistance. AI tools add no `Signed-off-by`; a human reviews and
certifies anything sent upstream. See [AGENTS.md](AGENTS.md) for contributor rules.
