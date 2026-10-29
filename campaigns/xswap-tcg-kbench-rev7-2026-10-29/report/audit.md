# Audit: round 1 of xswap-tcg-kbench-rev7-2026-10-29 (box-local draft, 2026-10-29 PDT)

Read-only audit. No commits, pushes, PRs, or evidence edits were made. Files written: `round1.html`, `gen_round1.py` (generator; every number goes through `N()` and carries `data-src`), `gen_round1.v1.py` (pre-revision copy), `dmesg-balloon-excerpt.txt` (box kernel log lines captured 13:48 PDT), `shot.png` (render check), and this file. Revision 2 at 13:49 PDT applies the coordinator's reply.

## Citation aliases used in round1.html (host paths kept out of the public text)
| alias | box path |
|---|---|
| `campaigns/…` | <box>/Swap-Next-main/campaigns/… (worktree detached at 9c1468ac) |
| `rundir:` | <box>/runs/grok-cloud-tcg-rev7-20261029/ |
| `archive:` | <box>/archive-20261029/ |
| `review:` | <box>/reviews/c1-v2-c1-xs-sync-ra-round1.md |
| `drafts:` | <box>/report-drafts/xswap-tcg-kbench-rev7-2026-10-29/ (captured excerpts) |
| pinned code links | github.com/ericzhang-zxh/Swap-Next/blob/{ab800d77,9c1468ac,87dc7357}/… |

## Claimed vs found
| claim | found | source |
|---|---|---|
| rev6 closed | closed 2026-10-29; reason not recorded | rev6 campaign.json `status`,`closed`; rundir:LOG.md (`--reason '<coordinator reason>'`) |
| rescore CALIBRATED (evidence only) | CALIBRATED; rev6 recheck CALIBRATION_NOISY; 0 new guests; ledger_modified false; NOT adopted | rescore receipt `verdict`, `rev6_recheck_same_inputs.status`, `guests`, `ledger_modified`, `workflow_adoption` |
| probe calibration 86fc2f67 | CALIBRATED, 9/9 PASS, metadata band 0.109746–0.112177 | ledger/calibration-probe.json |
| fast calibration 43 guests, 3 stall reruns | 43 runs = 10 pairs×4 + 3 invalid; reasons: clocksource_fallback; clocksource_fallback+wall_time_outlier; wall_time_outlier. Calling them "stalls" is the executor's inference | ledger/calibration-fast.json `runs[]`; rundir:LOG.md L19–20 |
| noise envelope | p90; disk seq.mean 0.0864, zram seq.mean 0.2242; ceiling 0.25 | calibration-fast.json `analysis.noise_relative` |
| void a7930c57 (watchdog false-STOP) | voids 16fe9d24 BLOCKED, 7 PASS guests; ran with tool @9c1468ac | rundir:void-receipt.json; ledger rows 1, 3 |
| void 820fdc14 (RAM balloon) | voids 0c2cd749 INCOMPLETE, 1 reserved guest, no QEMU; tool from 87dc7357 extracted (sha 6980e69a… matches git) | rundir:void-receipt-2.json; ledger rows 4, 5 |
| c1 correctness pass | CORRECTNESS_PASS, 17/17 gates, disk only, zswpout 0 | 68de report `correctness`; runs/guests/c1-…-correctness-1/result.json |
| probe 3a554e3b pass | PROBE_PASS; zram swap_ra 114684 vs band −1..1 | 3a55 report.json `analysis.probe_signals` |
| fast 68de12e0 FAST_PASS | FAST_PASS (median rule); disk seq ×3.054, zram seq ×1.402 (pair 1 0.955), zram seq p99 ×0.636 guard_pass false (advisory); performance_accepted/auto_promote/eligible_for_slow false; 4 pairs < policy min_pairs 10 | 68de report.json `analysis.*`; policy.json `measurement.min_pairs` |
| disk base 227–249 µs → 71–81 µs | base 216.4–248.8 µs, cand 71.0–80.5 µs | 68de report.json `pairs[].a/b` |
| Review NEEDS-MORE-EVIDENCE + asks | confirmed, 7 asks | review: |
| budget 90/120 global, 81 rev7 | rev7: fast 69/96 + probe 12/24 = 81/120; 81 reservation manifests (86fc 9, 16fe 7, 0c2c 1, e8b7 43, c1-corr 1, 3a55 3, 68de 17); 80 guest dirs. 90 = rev6 9 + rev7 81, but each campaign has its own 120 cap | ledger/budget.json; campaign.json `budget`; ledger/guest-reservations/; rev6 ledger/budget.json |
| cleanup removed lists | 24 "OK removed" in LOG.txt; removed.tsv lists only 12; SHA256SUMS 24/24 OK (re-checked) | archive:LOG.txt, removed.tsv, SHA256SUMS |
| df -i | IFree 1,399,185, IUse 32% at 10:18:44 (end of the pre-rev7 cleanup); run log later reads 1,294,442 (13:21) and 1,085,156 (13:34) | archive:LOG.txt; rundir:LOG.md L27+ |
| formal gates NOT RUN | 10 of 18 policy required_gates have no evidence | policy.json `required_gates`; c1-correctness.log `gates` |
| import-state open | no receipt under the git common dir `swap-next-migration/`; MOVED.json has no imports | AGENTS.md L181–183; migrate.py `state_paths` |

## Discrepancies
1. "Run from ab800d77" is only partly true. The rev6 close, rev7 open, 86fc and 16fe ran at ab800d77. Everything from 11:20 PDT ran at 9c1468ac, and void 820fdc14 used a tool from 87dc7357 (mixed code). The fingerprint stayed dcca47b0 the whole time, because the void tool is outside it.
2. "Final PR bundles everything" is not the current state. PR #8 (head ab800d77) is open and unmerged, and branch cursor/void-stop-calibration-9dd7 has no PR.
3. ~~The "global 90/120" denominator is wrong.~~ Revised: per coordinator, 2026-10-29, 120 is also the mandate cap for the whole 3-round run, so 90/120 is valid as the run-wide view. AGENTS.md L101 only defines 120 as a per-campaign default cap; no file states the run-wide mandate. The draft shows both views.
4. The fast calibration plan was 40 guests; it used 51 including voided ones. Round 1 used 21 vs a planned 20. Only 27 fast guests remain, enough for one more 17-fast round, not the "three rounds" in status-after-void2.json.
5. LOG.md L27 says disk base was 227–249 µs; the ledger (authoritative) shows 216.4–248.8 µs. Flagged in the draft.
6. LOG.md L21 says 2-disk-a-r1 was "run_valid but workflow INVALID"; the ledger (authoritative) has run_valid false (wall_time_outlier, clocksource_invalid false). Flagged in the draft.
7. The rev6 close reason is not recorded (TODO in the draft).
8. removed.tsv (12 rows) is incomplete compared with LOG.txt (24 removals).
9. RAM cause: the receipt says "virtio balloon" as fact; LOG.md at the time said "likely". The draft now says "likely virtio_balloon" (see verification 5).
10. The workflow wrote needs_review false; the human review says NEEDS-MORE-EVIDENCE. The draft lists this as a protocol proposal; it is not self-applied.
11. Void tooling rewrites the original ledger rows (execution_started → False). The receipts keep the original value (true).
12. Live during the audit: archive:LOG.txt gained a 13:44:04 PDT entry archiving the aborted c1b build (std-1f31dd174a36) and some run-dir c1b files. This is outside round 1; the draft pins the cleanup section to lines up to "DONE run3".

## archive/ verdict
The workflow created it (population.py via `loop.py next` and the FAST_PASS admission). It is not cleanup output and not the void tool.
- At 9c1468ac, evolve/population.py L185–186 sets archive/population.json, L510 writes archive/briefs, and L266–268 writes archive/database plus population-source.json. standard_workflow.py L765 and L848 drive it, and population.py is in the fingerprint (standard_workflow.py L173).
- The mtimes match: brief at 12:57:30.586, c1-next.out at 12:57:30.59, runs/population.lock at 12:57:29, population.json at 13:21:18.39, and ledger row 68de finished at 13:21:18.38.
- void_calibration.py at both commits contains no "archive". <box>/archive-20261029 ended at 10:18:44, before rev7 opened at 10:21:35, and never touches campaign paths.
- It shows as untracked only because .gitignore covers campaigns/*/runs/ but not archive/. population.py L5–6 says archive/population.json "owns evidence and sampling sequence". Per coordinator, 2026-10-29, it is owned evidence and will be committed with the campaign records; the draft says so.

## Not verifiable from the box
- The owner's approval of rev7.
- The model per step (all five rows are visible TODOs).
- The rev6 close reason is from the coordinator; its technical content is verified (below), but the close command recorded only a placeholder.
- The owner's 01:32 statement that the old evidence is void (relayed by the coordinator).
- The run-wide 120 mandate (coordinator only).
- Whether the virtio balloon really caused the low MemAvailable.
- The metrics of the 7 voided 16fe guests (not inspected).
- Whether the gcc_swap_on build manifest corresponds to the c1 commit (only referenced, not re-hashed).

## Coordinator reply (per coordinator, 2026-10-29): verification
| # | coordinator statement | result | source |
|---|---|---|---|
| 1 | rev6 numerator −ΔMemAvailable made the probe calibration NOISY | **match** | `git show ab800d77~1:benchmark/swap-standard/evidence.py` L155 `d['used_kib'] = -d.get('MemAvailable', 0)`; ab800d77 commit message; rev6 ledger [0] CALIBRATION_NOISY, eval 469ee19c |
| 1 | rev7 numerator Δ(SUnreclaim+VmallocUsed+PageTables+Percpu) | **match**, with detail: the sum is ×4096/ΔSwapTotal; a VmallocUsed decrease or a missing counter fails `metadata_attributable` | ab800d77 evidence.py L41 `ATTRIBUTABLE_FIELDS`; rev7 protocol.json `cases.metadata-brd.metadata_accounting.numerator` = attributable_meminfo, `measurement_revision` |
| 1 | same 1% band, 25% ceiling | **match** | rev6 and rev7 protocol.json `probe_band.metadata_spread_fraction` 0.01 / 0.01; `noise_ceiling` 0.25 / 0.25 |
| 1 | 9 probe guests | **match** | rev6 ledger/budget.json probe_guests 9; rev7 protocol `metadata_rescore.predecessor_probe_spent` 9 |
| 1 | the re-score couldn't be adopted into rev6 | **partial mismatch**: rev7 protocol.json `metadata_rescore` anticipated adoption (`fresh_probe_calibration_required: false`, "Adopting the recomputation on the predecessor budget spends no guests"). The receipt says why it failed: there is no re-score/adopt ledger action, and rev6 status reports 'stale calibration fingerprint' | rescore receipt `workflow_adoption` |
| 2 | records for xswap-tcg-r3-2026-10-24 / protocol-tcg-revision3 are absent on main 9b4e3fe | **match (absent)**, but 9b4e3fe is not the current main: origin/main is 25ad0ab (PR #7 merge, 2 commits later). The records are absent there too | `git ls-tree -r` on 9b4e3fe and origin/main, 0 hits each |
| 2 | import-state needs those records | **not reproduced**. migrate.py `import_state` was not run, because it can write locks/journal/receipt. The code only shows that it inventories local legacy sources and preflights them | 9b4e3fe:evolve/control/migrate.py L507–560 |
| 2 | Hurric said old evidence is void (01:32) | **unverified**, attributed. The archived OLD-EVIDENCE-INDEX.md says "import attempted, impossible". AGENTS.md records an owner pre-approval at 01:36 PT for the rev6 protocol, a different statement | AGENTS.md L299 |
| 2 | no receipt written | **match** | no `<git-common-dir>/swap-next-migration/` on the box |
| 3 | mandate 120 for the whole run: 90 used, 30 left; rev7 cap 120 with 27 fast left; one round (c1c 20+1) | **arithmetic matches** (rev6 9 + rev7 81 = 90; 96−69 = 27; protocol `planned_guest_counts.one_round` 20). The **run-wide mandate itself has no file source**; AGENTS.md L101 defines 120 per campaign | ledger/budget.json ×2; campaign.json; protocol.json |
| 4 | ab800d77 probe, 9c1468ac later runs, 87dc7357 void tool only, fingerprint dcca47b0, all unmerged | **match, with detail**: ab800d77 also ran fast attempt 16fe9d24 (and the rev6 close/re-score); void a7930c57 used the 9c1468ac tool, and only 820fdc14 used the 87dc7357 tool. None of the 3 commits is an ancestor of origin/main | rundir:LOG.md L1–16; `git merge-base --is-ancestor`; ledger fingerprints (1 distinct value) |
| 5 | dmesg shows virtio_balloon / Out of puff | **match**: the box kernel log has "virtio_balloon virtio0: Out of puff! Can't get 1 pages" at 11:19:23 and 11:19:25 PDT (monotonic [34684.68], [34686.16]), about 1 min before the 0c2cd749 refusal (ledger row 4, 11:20:36), plus 4 lines at 11:43:30–32. This is the box (outer VM) kernel, not a guest serial log; 215 such lines exist since boot. dmesg -T wall times are approximate. The receipt's flat "the virtio balloon left about 4.6 GiB" is stronger than this correlation | drafts:dmesg-balloon-excerpt.txt (ring buffer can rotate, so it was saved) |
| 6 | needs_review=false vs human verdict as a protocol proposal | done; not self-applied | 68de report `analysis.needs_review` |
| 7 | archive/population.json is owned evidence and will be committed | done; consistent with population.py L5–6 | 9c1468ac:evolve/population.py |
| 8 | models table TODO | done (5 visible TODOs) | — |
| 9 | ledger authoritative over LOG.md | done; both mismatches flagged in the draft | 68de pairs[].a; calibration-fast runs[] |

## Turn 3 — summary.html (2026-10-29, ~14:31 PDT)

Generator: `gen_summary.py` → `summary.html` (data-src spans 306; 1 TODO = pin links to bundle commit; 0 parser errors; no host paths). `gen_round1.py` re-run: removed.tsv table limited to round-1-era rows (removed.tsv grew to 24 rows incl. `/tmp/` path), models section now points to summary.html. New evidence capture: `df-i-capture.txt` (live `df -i /` 14:25:36 PDT).

### Coordinator claims vs found (per coordinator, 2026-10-29)

| claim | found | file / key |
|---|---|---|
| c1c = b69e47c9, baseline-parented | yes | 66a07143 report.json candidate_commit, parent_comparison.parent_commit 5e84ca92 |
| record a949549f hashed 13:54:39, before first boot 13:56:09 | sha matches; file mtime/created_unix 13:54:31 (13:54:39 is the LOG.md line time); reservation 13:56:09, QEMU started.json 13:56:15; order holds | candidates/v2-c1c-xs-ra-safe.json; reservation reserved_unix; LOG.md L34 |
| correctness 17/17 on disk | yes (integration_pass, run_valid true) | runs/guests/c1c-…-correctness-1/result.json gates |
| probe bc73887e passed | PROBE_PASS | ledger.json [9] = report.json |
| fast 66a07143 BLOCKED/INCOMPLETE 6/8 | ledger status BLOCKED (INCOMPLETE is executor/review wording); 6 PASS of 8 arm-slots in pairs 0–1; 16 planned | report.json runs; protocol tiers.fast |
| zram-64k-b INVALID twice, tsc skew also in calibration | yes: "Marking clocksource tsc unstable due to frequency skew" in 66a0 1-zram-64k-b (L481), -r1 (L482), e8b7 0-zram-64k-a (L482), 2-disk-a (L480) | serial.log |
| not voided: tool refuses evaluate rows; rows unmodified | yes: void_calibration.py `action != "calibrate"` → "not a calibration attempt" (9c1468ac L108, 87dc7357 L166); void-3/3b.err REFUSED; row 10 == report.json, no void key; ledger sha e5db5dac, mtime 14:13:12 < void 14:17:49 | |
| review NEEDS-MORE-EVIDENCE, RED FLAG disk seq.p99, WATCH rand.mean | yes | review2 L5, red-flag table |
| round 3 not run (budget) | per coordinator only; LOG.md L41 records the coordinator decision | |
| c1 closed superseded, reason in ledger | reason is in candidates/v2-c1-xs-sync-ra.json `reason` and ledger/events.jsonl candidate_closed payload; NOT in ledger.json (no row for closes) | |
| guests 103/120 | 103 = rev6 9 + rev7 94 (79+15); reservations 94; dirs 92; GA.md matches; 90 after round 1 → +13 in round 2 | |
| latest df -i ≈1.19M free | LOG.txt last df is 985,679 free (13:44:15); 1,188,747 only in live box capture 14:25:36 | archive:LOG.txt; drafts:df-i-capture.txt |
| models grok-4.7 for bc-9fa8e17e / bc-33e85066 | unverifiable; commits authored "Cursor Agent", no model recorded | git log |

### Discrepancies (turn 3)
1. 13:54:39 vs 13:54:31 (log-line vs file time) — no effect on order.
2. "in the ledger": close reason lives in candidate record + events.jsonl, not ledger.json.
3. c1 close reason says "worktree … kept as evidence", but the worktree was archived and removed at 14:19:25 (LOG.md L44; archive:LOG.txt). Survives as a verified tar.zst only.
4. 1.19M inodes is not in LOG.txt.
5. "6/8 pair-slots" counts arm-slots in pairs 0–1; the planned fast tier is 16 slots / 4 pairs.
6. Non-issue: candidate protocol_sha256 cb3c6a09 ≠ protocol.json sha a058b8f5 because it is controller protocol_hash (campaign policy.json + analysis.py + controller.py), recomputed = cb3c6a09.
7. round1.html removed.tsv table had picked up later rows (incl. a /tmp/ host path) — fixed by limiting to round-1 rows.
