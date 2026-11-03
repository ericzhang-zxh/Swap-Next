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
campaigns/        research line agendas; one directory per campaign; generated indexes
  <campaign>/     campaign.json, policy.json, frozen protocol.json
                  ledger/, candidates/, patches/, archive/, report/
                  runs/ is local raw evidence and remains ignored
benchmark/        trusted builds, guest workloads, parsers and measurement rules
evolve/           controller, probe/latency workflow, population and task briefs
  openevolve/     pinned upstream ProgramDatabase and PromptSampler
```

Clone with `git clone --recurse-submodules`, or run
`git submodule update --init linux evolve/openevolve`.

## Start or resume a research loop

Ask your contributor agent to use
[closed-loop-evolve](.agents/skills/closed-loop-evolve/SKILL.md) and start a
research line. The active agent proposes, implements and explains; project code
persists the next action and verifies measurements. An agent session is needed
through delivery. This is not a background model service.

```sh
# Use your stable contributor identity, not another campaign's owner.
export SWAP_NEXT_CONTRIBUTOR=your-stable-id
# A new campaign uses a prepared policy/protocol and your own line agenda.
evolve/.venv/bin/python evolve/loop.py start --campaign <c> --line <line> --idea <idea> --machine <machine>
# Recover the same campaign, including report delivery after execution closes.
evolve/.venv/bin/python evolve/loop.py resume --campaign <c>
```

Follow the returned action until delivery is complete or an exact external
blocker remains. Trusted command actions run through
`evolve/loop.py execute --campaign <c> --action <action-id>`; reasoning and edit
actions identify the artifact the agent must supply. Re-read `next-action`
after each result. Never infer completion from a command exit code alone.
[The session contract](evolve/session-schema.md) documents actions and decision
payloads. Existing suite-specific commands remain available.

Each contributor owns separate line and campaign state. Start selects only your
lines; Resume only continues your sessions. Other contributors' work is a
read-only reference, not a shared to-do queue. Shared upstream/cache evidence
remains reusable. A busy machine does not authorize releasing someone else's
claim or taking over their experiment.

A **line** owns a durable question, prioritized ideas, upstream alternatives,
complexity/value criteria and lifetime resource ceilings. A **campaign** freezes
one bounded attempt. A **candidate** is an isolated implementation, which may
optimize, simplify, redesign or repair. Start from
[research-schema.md](evolve/research-schema.md) and the approved profiles in
`evolve/profiles/`. Larger architectural work with missing measurement coverage
returns the exact capability gap before execution. Candidate workers cannot
expand a trusted profile.

The loop retains exact parent/tree identities, static and structured reviews,
correctness evidence, mechanism observations, calibrated latency comparisons,
and a reasoned value decision. An unresolved review veto blocks inheritance
and dependent execution immediately. Fast results are exploratory; slow
confirmation requires explicit approval for each execution. No code is promoted
automatically.

Upstream alternatives use [frozen comparison arms](evolve/comparison-schema.md).
The [shared reference cache](evolve/reference-cache-schema.md) retains reusable
build, review, correctness, calibration and performance provenance. A cache hit
is checked against current inputs and vetoes. Reuse retains its original
measurement date; expired or incompatible measurements remain historical
references. Reports distinguish new measurements and reused evidence.

STOP and spent execution budgets still allow patch preservation, report
creation, visual checks and publication. Numerical report content comes from
the retained evidence. Delivery records separately track generation, visual
verification and verified live publication.

Kernel builds and guests run on a Linux worker; see
[benchmark/SETUP.md](benchmark/SETUP.md). Grok Bot uses its cloud box with TCG;
[AGENTS.md](AGENTS.md#grok-bot-runs-cloud-box-qemu-tcg) owns those rules.
[The campaign index](campaigns/README.md) records campaign state. Frozen older
protocols preserve their contracts. Read [DESIGN.md](DESIGN.md#limitations) for
measurement limits.

## Provenance and license

Our code and patches are GPL-2.0-only ([LICENSE](LICENSE)). Linux and
OpenEvolve keep their own licenses. Code and reports were written with
substantial AI assistance. AI tools add no `Signed-off-by`; a human reviews and
certifies anything sent upstream. See [AGENTS.md](AGENTS.md) for contributor rules.
