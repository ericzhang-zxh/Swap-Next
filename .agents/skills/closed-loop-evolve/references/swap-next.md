# Swap Next binding

Read [AGENTS.md](../../../../AGENTS.md) and [DESIGN.md](../../../../DESIGN.md)
first. DESIGN.md owns the cost model, the upstream landscape and the measurement
principles; each campaign's findings and next steps live in its `results/` report. All kernel, build and VM work runs on the Linux worker over SSH.

## Components

| Path | Role |
|---|---|
| `evolve/control/` | controller, scope policy, formal analysis (disabled), campaign state |
| `evolve/loop.py` | OpenEvolve adapter: `loop.py <kernel\|xswap\|xswap-structure> status\|next\|evaluate\|calibrate`. `calibrate` runs for xswap and xswap-structure. `loop.py swap-standard` delegates to `standard_workflow.py`, which also calibrates. kernel has no calibration step |
| `evolve/openevolve/` | pinned upstream submodule (not a fork) |
| `benchmark/<suite>/` | trusted build, guest, evaluator and `protocol.json` |
| `results/`, `patches/` | campaign reports and independently based patches |

The base policy is `evolve/control/config/policy.json`. A named campaign uses
`evolve/control/campaigns/<c>/policy.json` and is selected with
`controller.py --campaign <c>`, which goes before the subcommand. `loop.py`
for kernel, xswap and xswap-structure takes no campaign flag: it reads
`benchmark/<suite>/protocol.json`. `standard_workflow.py` on main reads
`benchmark/swap-standard/protocol.json`. The xswap-next-2026-10-24 snapshot
selected `benchmark/swap-standard/protocol-xswap-next-2026-10-24.json` through
`select_protocol`, which is not defined in `standard_workflow.py` on main.
Before evaluating, check that the protocol's campaign and baseline match the
controller's.

The controller and the adapter count budgets differently. For example, an
imported reference uses a controller record but is not an evaluated
candidate. Reconcile the two and apply the smaller remaining budget.

## One round

```sh
python3 evolve/control/controller.py --campaign <c> new <name> --hypothesis '<mechanism, expected effect, falsifier>'
# implement and commit inside worktrees/<c>/<name>
python3 evolve/control/controller.py --campaign <c> check <name>
evolve/.venv/bin/python evolve/loop.py xswap evaluate --candidate <name>
evolve/.venv/bin/python evolve/loop.py xswap next
python3 evolve/control/controller.py --campaign <c> close <name> --reason '<decision and evidence>'
```

When the campaign stops, close it with the review page:

1. Update `results/<c>/README.md` (status, findings, limits) and its review notes.
2. Follow [explaining-campaign-results](../../explaining-campaign-results/SKILL.md)
   to generate `results/<c>/explainer.json` and `explainer.html` from the
   evaluation reports. Follow its verdict-first, visual-first presentation contract;
   keep exact data and audit details collapsed. Check both themes and mobile,
   then link the page from the README.
3. Follow [AGENTS.md](../../../../AGENTS.md#report-publication). Upload and
   publish the campaign report, then hand it to the owner for review. Commit
   experiment work directly to `main` without a pull request. Preserve failed
   or inconclusive verdicts. Publishing the report is not candidate promotion.
   If the owner explicitly withholds a push or asks to keep the report private,
   honor that request. Otherwise finish delivery without asking again. An
   agent-authored publication flag does not override this rule.
4. Inspect the diff, build the Pages index and fast-forward `main`. Verify that
   commit's Pages deployment, live campaign URL and index. Never force-push
   `main`.

For an older experiment checkout, inspect current `origin/main:AGENTS.md` and
this binding on origin/main before closeout. Reconcile delivery rules without
changing frozen scientific inputs, STOP files or experiment budgets.

What each adapter action does:

| Action | Effect |
|---|---|
| `status` | creates the ignored state directory; launches nothing |
| `next` | writes a task brief; starts no model |
| `evaluate` | builds the candidate and boots AB/BA pairs on both backends |
| `calibrate` | boots A/A pairs on real guests for xswap, xswap-structure and swap-standard. kernel has no calibration step. Evaluation requires a calibration report whose suite hashes match the current files |

## Campaign state

`xswap-2026-10-21` is closed. Its deadline has passed and the harness has been
relocated since. Later campaigns, including xswap-structure, xswap-swapin,
xswap-p123 and xswap-next, keep their own policy, protocol and report. Read
the newest `results/<c>/` report before treating an earlier status line as
current. A new campaign still needs:

- its own policy and protocol;
- a fresh baseline build and initrd;
- fresh A/A calibration;
- the measurement fixes in [the 2026-10-21 report](../../../../results/xswap-2026-10-21/README.md#next-steps-for-this-direction) when it continues that suite.

Never reset a budget by clearing a ledger or database.

| Record | Path |
|---|---|
| controller candidates | `evolve/control/state/[<c>/]candidates.json` |
| search ledger and database | `evolve/<suite>/state-layout-v1/` |
| evaluation reports | `benchmark/<suite>/evaluations/<id>/report.json` |
| xswap calibration | `benchmark/xswap/state-layout-v1/calibration.json` |
| xswap-structure calibration | `benchmark/xswap-structure/state-layout-v1/calibration.json` |
| xswap attempts | `benchmark/xswap/state-runtime-layout-v1/attempts.json` |
| standard-suite ledger | `evolve/swap-standard/state-layout-v1/` for `protocol.json` |
| xswap-next snapshot ledger | `evolve/swap-standard/state-xswap-next-2026-10-24/` on snapshot `15bf186`; not created by `standard_workflow.py` on main |
| guest lock | `benchmark/kernel/.runtime.lock` |

The untracked `Evolve/` directory is an archive of pre-relocation runs. Read it
when reconciling, but never import it as fresh evidence.

`evolve/control/state/STOP` (and `state/<c>/STOP` for xswap) stops owned
processes. A tool call that ends does not stop a running build or VM, so
confirm that it has exited.

## Checks

```sh
python3 -m unittest discover -s evolve/control/tests -v
python3 -m unittest discover -s benchmark/tests -v
python3 -m unittest discover -s benchmark/xswap -p 'test_*.py' -v
```

`XSWAP_EVIDENCE_FIXTURE` and `SWAP_NEXT_EVIDENCE_FIXTURE` enable the
real-run parser tests. These checks never boot a kernel.
