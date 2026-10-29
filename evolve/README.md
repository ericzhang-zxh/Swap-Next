# Evolution workflow

`loop.py swap-standard` dispatches to the trusted standard workflow. Candidate
worktrees and cumulative scope checks belong to `control/controller.py`;
`population.py` uses the pinned `openevolve/` ProgramDatabase and PromptSampler
without calling an LLM provider. The assistant proposes and implements changes.

Every campaign has a tracked directory under `campaigns/`: identity, policy,
frozen protocol, ledger, candidates, patches, population and report. Raw guest
runs and build products remain local. Historical suite state is listed in
`campaigns/MOVED.json`; it is not fresh calibration.

The loop is hypothesis → correctness → mechanism probe → agent selection →
paired latency screen → exploratory population → brief → inherited candidate.
`FAST_PASS` allows neutral exploration. Baseline advancement separately needs
improvement above calibration noise and preserves the line's original anchor.
Candidate trees and measurement identities prevent repeated code from buying
new attempts through different commit messages.

```sh
evolve/.venv/bin/python evolve/loop.py swap-standard status --campaign <c>
evolve/.venv/bin/python evolve/loop.py swap-standard next --campaign <c>
python3 evolve/control/controller.py --campaign <c> resume-campaign --reason '<recovery>'
```

Probe/fast execution follows the frozen campaign protocol and counted guest
reservations. The slow tier needs explicit owner approval per run. Formal
acceptance and code promotion remain human decisions. The revision 4 template
is preparation only; see [runtime readiness](../DESIGN.md#revision-4-readiness).
TCG kbench revision 6 is
[its protocol](../campaigns/xswap-tcg-kbench-2026-10-29/protocol.json).
Revision 7 is proposed and not opened; see
[its protocol](../campaigns/xswap-tcg-kbench-rev7-2026-10-29/protocol.json).

Use the [closed-loop workflow](../.agents/skills/closed-loop-evolve/SKILL.md)
and its [repository binding](../.agents/skills/closed-loop-evolve/references/swap-next.md).
