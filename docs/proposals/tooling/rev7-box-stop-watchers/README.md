# Rev7 box STOP watchers (proposed, unreviewed)

These are the box-local shell scripts that wrote campaign `STOP` files during
[xswap-tcg-kbench-rev7-2026-10-29](../../../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/).
They are committed byte-for-byte as they ran on grok-cloud, as evidence and as
a starting point for tooling. Nothing in the controller, workflow or runners
calls them, and no one has reviewed them. Adopting any of them is an owner
decision (see [rev8-from-rev7-campaign.md](../../rev8-from-rev7-campaign.md)).

The scripts hard-code box paths for the live checkout and run directory. A
reviewed version would take the campaign directory as an argument.

| Script | Role | Outcome in rev7 |
| --- | --- | --- |
| `watchdog.v1-falsepositive.sh` | First watchdog: TCG-only QEMU check, one QEMU at a time, probe/fast/total guest caps from `ledger/budget.json`. | At 10:46:34 PDT it read the empty `/proc/<pid>/cmdline` of an exiting QEMU as non-TCG and touched `STOP`, blocking fast calibration eval `16fe9d24` after 7 of 40 guests. That marker is preserved as `STOP.watchdog-falsepositive-20261029T1046`. |
| `watchdog.sh` | v2: re-reads an empty cmdline once and skips an exiting QEMU. | Ran for the later steps (stopped through `watchdog.off`). |
| `c1c-rerun-watch.sh` | Round 2 (c1c) budget watcher: at most 1 validity rerun and at most 102 rev7 guests. | Wrote the intentional `STOP` at 14:13:12 PDT on the second INVALID (`clocksource_fallback`) attempt, before `loop.py` booted the reserved r2 rerun; c1c fast eval `66a07143` ended BLOCKED. |
