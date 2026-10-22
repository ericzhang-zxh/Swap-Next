# Swap Next

A laboratory for finding Linux swap optimizations. Each candidate is a small
patch on a frozen kernel. A benchmark boots it next to the baseline in KVM, and
OpenEvolve records the outcome and selects references for the next proposal.

[DESIGN.md](DESIGN.md) covers the shared design: the swap cost model, the
upstream landscape, measurement principles and the role of OpenEvolve.
Each exploration direction runs as a campaign and reports in
[results/](results/); review pages are published at
<https://ericzhang-zxh.github.io/Swap-Next/>.

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
results/          one report per campaign
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

What the harness cannot measure is listed once, in
[DESIGN.md § Limitations](DESIGN.md#limitations).

## Provenance and license

Our code and patches are GPL-2.0-only ([LICENSE](LICENSE)). Linux and
OpenEvolve keep their own licenses. Code and reports were written with
substantial AI assistance. AI tools add no `Signed-off-by`; a human reviews and
certifies anything sent upstream. See [AGENTS.md](AGENTS.md) for contributor rules.
