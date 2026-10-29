# Proposals for TCG kbench revision 8 from the rev7 campaign

Status: **proposed, not applied.** Every item below is an owner decision
under [What needs owner approval](../../AGENTS.md#what-needs-owner-approval).
Nothing in this branch changes a protocol, the controller, the workflow, the
void tool's behaviour, a runner or a gate to implement them.

Source campaign:
[xswap-tcg-kbench-rev7-2026-10-29](../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/)
(report: [summary.html](../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/report/summary.html),
[round1.html](../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/report/round1.html),
[audit.md](../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/report/audit.md)).
Source reviews:
[c1 round 1](../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/report/c1-v2-c1-xs-sync-ra-round1.md),
[c1c precheck](../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/report/c1c-v2-c1c-xs-ra-safe-precheck.md),
[c1c round 2](../../campaigns/xswap-tcg-kbench-rev7-2026-10-29/report/c1c-v2-c1c-xs-ra-safe-round2.md).

## Decision items

| # | Proposal | Why (rev7 evidence) | Touches |
| --- | --- | --- | --- |
| 1 | **A1 runtime test.** Add a correctness case that runs an async (disk) backend with zswap enabled, forced writeback (`zswpout > 0`, `zswpwb > 0`) and swapoff under load, and records a counter of readahead recheck rejections. | c1c's A1 (speculative read of an unbacked slot → SIGBUS) is closed by code reading only. The c1 correctness run had `zswpout 0`; with the zswap backend the physical device is zram (synchronous), so readahead and the recheck never run. The c1c precheck asks that A1 stay recorded as NOT RUN. | guest workload, parser, protocol correctness gates |
| 2 | **`needs_review` on breached advisory guards.** Set `needs_review = true` when an advisory guard is breached in every pair. | Fast eval `68de12e0` (c1) was FAST_PASS with zram `seq.p99` ×0.636 and `guard_pass false` in all pairs, yet the workflow wrote `needs_review false` while the human Review said NEEDS-MORE-EVIDENCE. | analysis / workflow |
| 3 | **Clocksource / TCG stall mitigation and recalibration.** Pin or check the guest clocksource (for example fail early on `tsc unstable due to frequency skew`), then recalibrate fast noise under the mitigation. | Fast calibration `e8b7a7e3` needed 3 invalid reruns (`clocksource_fallback`, `wall_time_outlier`). c1c fast eval `66a07143` lost `1-swapin-zram-64k-b` and its rerun to `clocksource_fallback` (TSC skew in serial logs) and ended BLOCKED. | guest cmdline/image, validity rules, new calibration |
| 4 | **Pre-registered eval void rule.** Define, before a campaign opens, when an evaluate attempt can be voided; keep original ledger rows immutable and write only append-only void receipts. | The current void tool rewrites `execution_started` on the original calibration rows (the receipts keep the original `true`) and refuses evaluate rows (`not a calibration attempt`), so BLOCKED eval `66a07143` could not be voided. | `evolve/control/void_calibration.py`, ledger contract |
| 5 | **Arm-specific wall-outlier threshold; arm the first-guest wall gate.** Derive `wall_time_outlier` per backend arm from calibration, and enable the first-guest wall gate. | zram-64k and disk arms have different wall distributions under TCG; a single threshold produced a `wall_time_outlier` invalid in calibration, and the first-guest gate is unarmed. | validity rules |
| 6 | **Budget reserve.** Hold back at least 1 pair + 2 reruns per arm from the round budget. | Round 2 stopped on budget: the round watcher allowed 1 rerun total, and the second INVALID wrote STOP (14:13:12 PDT) before the reserved r2 rerun booted. Round 3 was not run for budget; 103/120 guests used. | budget plan, protocol `planned_guest_counts` |
| 7 | **c1c completion run under rev8, plus a KVM arm before any disk claim.** Complete c1c's fast tier under rev8; add a KVM confirmation arm (hurricpc-wsl) before any disk swap-in claim. | c1c fast is BLOCKED (6 of 8 slots in pairs 0–1; 16 planned). c1's disk `seq.mean` ×3.054 is a TCG-only screen effect; AGENTS.md forbids comparing across accelerators. | new campaign, owner-approved KVM run |
| 8 | **Formal gates on hurricpc-wsl.** sparse; `gcc_swap_off` / `gcc_zswap_on` builds; lockdep; KASAN; KCSAN; io-error injection; `fail_page_alloc` / `failslab`; memcg v2 and v1 `memsw`; mTHP `large_folio`. | 10 of 18 policy `required_gates` have no evidence for c1 or c1c. A2 (`ci->lock` context) is open until lockdep runs. The c1c precheck notes the readahead read-error path turns into SIGBUS on a later fault, which io-error injection would exercise. | hurricpc-wsl runs (owner-gated) |
| 9 | **Old r3 evidence import: SKIPPED.** Record that `migrate.py import-state` was not run for the old r3 evidence. | The `xswap-tcg-r3-2026-10-24` / `protocol-tcg-revision3` records are absent on `main` (checked at `9b4e3fe` and `25ad0ab`); no import receipt exists. Decide whether to import, mark void, or leave as is. | migration record |

## Limitations

The causes in items 3 and 5 are inferences from serial logs and the ledger
(medium confidence); a rev8 calibration with the mitigation would confirm or
refute them. The run-wide 120-guest mandate is a coordinator statement;
AGENTS.md defines 120 per campaign.
