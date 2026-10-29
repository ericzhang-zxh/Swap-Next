# Swap Next

<p align="center">
  <br />
  <a href="https://ericzhang-zxh.github.io/Swap-Next/"><strong>View Daily Experiment Results</strong></a>
  <br />
  <sub>Reports, decisions, and evidence from each campaign</sub>
  <br /><br />
</p>

A laboratory for finding Linux swap optimizations. Each candidate is a
frozen-kernel change, from a small patch through a larger redesign. A benchmark
boots it next to the baseline in a QEMU guest, and OpenEvolve records the outcome and
selects references for the next proposal.

[DESIGN.md](DESIGN.md) covers the shared design: the swap cost model, the
upstream landscape, measurement principles and the role of OpenEvolve.
Each exploration direction runs as a campaign and reports in
[campaigns/](campaigns/).

## Layout

```text
linux/            frozen upstream submodule; never modified
campaigns/        one directory per campaign; generated campaign and line indexes
  <campaign>/     campaign.json, policy.json, frozen protocol.json
                  ledger/, candidates/, patches/, archive/, report/
                  runs/ is local raw evidence and remains ignored
benchmark/        trusted builds, guest workloads, parsers and measurement rules
evolve/           controller, probe/latency workflow, population and task briefs
  openevolve/     pinned upstream ProgramDatabase and PromptSampler
```

Clone with `git clone --recurse-submodules`, or run
`git submodule update --init linux evolve/openevolve`.

## Workflow

New performance work starts with [the standard suite](benchmark/swap-standard/README.md)
(usemem, kernel build and Valkey), followed by repeated A/A calibration and a
frozen campaign protocol. The historical evolve adapters below retain their
original workloads and scores for reproducibility. They have not been admitted
as evaluators for the new suite.

Kernel builds and guests run on a Linux KVM worker; see
[benchmark/SETUP.md](benchmark/SETUP.md).
Experiments launched by Grok Bot run on its cloud box under QEMU TCG (no KVM).
Revision 3 is closed. Revision 6 is
[campaigns/xswap-tcg-kbench-2026-10-29/protocol.json](campaigns/xswap-tcg-kbench-2026-10-29/protocol.json).
Revision 7, proposed and not opened, is
[campaigns/xswap-tcg-kbench-rev7-2026-10-29/protocol.json](campaigns/xswap-tcg-kbench-rev7-2026-10-29/protocol.json).
See [AGENTS.md § Grok Bot runs](AGENTS.md#grok-bot-runs-cloud-box-qemu-tcg).

```sh
python3 evolve/control/controller.py --campaign <c> open-campaign --line <line> --machine <machine>
evolve/.venv/bin/python evolve/loop.py swap-standard next --campaign <c>
python3 evolve/control/controller.py --campaign <c> new <name> --hypothesis '<mechanism and falsifier>' \
  --mechanism '<case>:<counter>:<direction>' --brief <brief-id> --parent <baseline-or-sampled-commit>
# Implement and commit in the controller-created candidate worktree.
python3 evolve/control/controller.py --campaign <c> check <name>
evolve/.venv/bin/python evolve/loop.py swap-standard calibrate --tier probe --campaign <c>
evolve/.venv/bin/python evolve/loop.py swap-standard evaluate --tier probe --campaign <c> \
  --candidate <name> --correctness <proof.json>
# The agent selects probe passes and records why they enter fast screening.
```

The controller keeps candidates inside the allowed files and line budget.
The evaluator probes mechanisms, then runs AB/BA latency pairs for selected candidates.
A fast-tier pass enters the exploratory population; baseline advancement additionally
requires improvement evidence above calibration noise. A fast pass is a screen;
a human decides whether anything goes upstream.

What the harness cannot measure is listed once, in
[DESIGN.md § Limitations](DESIGN.md#limitations).

## Provenance and license

Our code and patches are GPL-2.0-only ([LICENSE](LICENSE)). Linux and
OpenEvolve keep their own licenses. Code and reports were written with
substantial AI assistance. AI tools add no `Signed-off-by`; a human reviews and
certifies anything sent upstream. See [AGENTS.md](AGENTS.md) for contributor rules.
