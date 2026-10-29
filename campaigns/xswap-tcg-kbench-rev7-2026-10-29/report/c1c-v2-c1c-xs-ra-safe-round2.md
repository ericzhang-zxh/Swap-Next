# Round-2 review: c1c `v2-c1c-xs-ra-safe` @b69e47c9 (fail-closed)

READ-ONLY review of campaign `xswap-tcg-kbench-rev7-2026-10-29`. I did not build, boot, rerun, void, commit or push. Times are PDT (UTC−7). Ratios are baseline/candidate, so a value above 1 means the candidate is faster. I recomputed each ratio from `pairs` in `runs/evaluations/66a07143…/report.json`.

## Verdict: **NEEDS-MORE-EVIDENCE**

The fast eval 66a07143 is `BLOCKED` ("BLOCKED: campaign: STOP") with 6 of 8 planned pair-slots. Protocol rev7 decides on the median with `comparison_pairs` 4. `analysis.compare(decision="median")` raises "median comparison requires at least 4 independent pairs". So **there is no fast decision: no FAST_PASS and no REGRESSION**.

No REJECT trigger is present:
- correctness passed;
- no pre-registered falsifier fired;
- the KILL cannot be evaluated (see §6);
- the partial *scored* medians are inside their guards.

There is one **advisory red flag**: disk seq.p99 is outside the A/A envelope in both pairs.

**Parent judgement:** c1c is a clean, correctness-passing, mechanism-confirmed candidate with an unproven performance profile. Do not promote, open the slow tier, or describe the result as "passed". See §4 on the void: as the tooling stands, the planned void cannot run against an evaluation, and it must not be used to make this eval look complete.

## Check table

| # | Check | Result | Evidence | Confidence |
|---|---|---|---|---|
| 1a | Record sha a949549f exists | **Yes.** `sha256sum candidates/v2-c1c-xs-ra-safe.json` = a949549f118ad5ec…d811. It is unchanged since it was logged. | `campaigns/…/candidates/v2-c1c-xs-ra-safe.json` | high |
| 1b | Hashed and logged before the first boot | **Yes.** File mtime and `created_unix` are both 13:54:31. LOG line 13:54:39: "PRE-REGISTRATION RECORD … sha256 a949549f… (before first boot)". First c1c guest (correctness) `.start` and reservation are at 13:56:09. | LOG.md; `c1c-correctness.start`; reservation `reserved_unix` 1793307369 | high |
| 1c | Content | **Yes.** It contains: "KILL: MEDIAN zram-64k seq.p99 ratio (baseline/candidate) < 0.834 … 0.90 … advisory only"; FALSIFIERS (zram swap_ra not ~0; disk swap_ra not ~115k; disk seq.mean median < 2.5; page_io.c WARN/SIGBUS; correctness failure); probe key `swapin-disk:swapin_vmstat_delta.swap_ra:up` (also `mechanism`); "Correctness on the disk backend with swap_ra > 0"; "zswap-mixed async-backend test NOT RUN". | record `hypothesis`, `mechanism` | high |
| 1d | Committed to git | **No.** `candidates/` is untracked (`git status`: `?? …/candidates/`). The hash plus log entry meets M1's "at least hashed and timestamped" alternative, not the commit option. The draft `c1c-hypothesis.txt` has a different sha (1b78d176…), as expected: it is the text, not the record. | `git status --short` | high |
| **M1/M2** | | **Satisfied** (hash and log route; median statistic; 0.834). | — | high |
| 2a | Correctness 17/17 | **Yes.** All 17 gates true: boot, cmdline_identity, workload_complete, kernel_log_present, no_kernel_warnings, thp_policy, swap_activity, backend_exercised, swap_routing, correctness_evidence, data_roundtrip, fork_cow, concurrent_fault, destroy_live_pages, swapoff_live_pages, no_new_kernel_warnings, qemu_exit. The 5 protocol `required_correctness_gates` (data_roundtrip, fork_cow, concurrent_fault, swapoff_live_pages, no_new_kernel_warnings) are among them. `run_valid` true, `kernel_diagnostics` []. Backend disk, `source_commit` b69e47c9, image d574b737. | `runs/guests/c1c-…-correctness-1/result.json`; protocol.json | high |
| 2b | swap_ra 12 as evidence | **Weak but non-zero.** 12 neighbour folios were admitted and read, so the hint and recheck *keep* path ran for at most a few faults. There is **no** evidence that the recheck *reject* (drop/unwind) path ran, because no counter records it. Also: swap_ra_hit 7 (c1: 7), pgmajfault 16409 (c1: 16415), pswpin 49169 (c1: 49221). | same; c1 `…/c1-v2-c1-xs-sync-ra-correctness-1/result.json` | high (facts) |
| 2c | Why 12 versus 4104 | **Most likely A3 working as designed, not the gate wrongly rejecting.** In the correctness workload the main read loop visits pages in a shuffled order (correctness.c 76-78, 102), and each of the 48 children touches one page (88-91). So adjacent faults, the precondition in `xswap_fault_readahead` (swap_state.c 897-903; c1 had the same rule at its 816), are rare in both kernels. That is why hits are 7 in both. The ~4092 extra swap_ra in c1 must then come from a path c1c gates and c1 did not. The obvious one is swapoff's `try_to_unuse` → `swapin_readahead` while SWP_WRITEOK is cleared, which c1c's target check now refuses (A3). Workload size is identical (16384 samples in both). Cluster vs VMA mode is the same build and config in both, so it cannot explain the difference. **This is an inference; I have no per-path counter.** | correctness.c; swap_state.c 886-909, 1094, 1200 | medium |
| 2d | Serial logs grepped | **Done independently on all 12 round-2 logs** (correctness 1, probe bc73887e 3, fast 66a07143 8 including both INVALIDs). Pattern: WARNING, WARN_ON, BUG, SIGBUS, page_io.c, KASAN, lockdep, "possible circular", uptodate, Oops, panic, "Call Trace", "bad page". The only matches are benign: `panic=-1` on the cmdline (×3) and the PCI "report a bug" line. warning-level `pr_warn` lines do reach serial.log (the clocksource "Marking … unstable" lines appear), so the grep is meaningful. **Caveat:** the build is `--no-instrumentation`, so a KASAN or lockdep match was never possible. A clean grep is not a lockdep or KASAN result. | `runs/guests/*/serial.log` | high |
| 3 | Probe falsifiers | **None fired.** bc73887e PROBE_PASS: disk swap_ra 115149 (hit 115143; c1 fast disk 114702-115150), so "~115k" holds. zram-64k swap_ra 0 (pgmajfault 262142, the baseline path), so "~0" holds. brd metadata 0.110886 B/slot. No WARN/SIGBUS in the 3 probe logs. | `evaluations/bc73887e…/report.json` `probe_signals`; grep | high |
| 4a | zram-64k-b in pair 1 | **The candidate arm.** Its reservation identity is build `std-b69e47c9118b`, backend zram-64k; arm a is `kb-xs-desc-v1`. Both attempts are `clocksource_fallback`: serial shows "Marking clocksource tsc unstable due to frequency skew" (and "Watchdog remote CPU 1 read timed out" in r1). The same failure appears in 2 *calibration* logs (e8b7a7e3 2-disk-a and 0-zram-64k-a), so it is a host/TCG phenomenon and not attributable to c1c. r2 was reserved (`STARTED`) but never booted, and it was counted in the budget. Pair-1 zram-64k-a never ran. | reservations; report `runs`; serial; rerun-watch log | high |
| 4b | INCOMPLETE per protocol | **Yes.** Fewer than `comparison_pairs` 4, and the eval was stopped by STOP before the protocol's `reruns_per_arm` 2 was used up. The coordinator's C3 limit (1 rerun) was stricter than the protocol, and it is what stopped the eval. Fail-closed: **no FAST_PASS, and none can be inferred from partial pairs.** | protocol.json `tiers.fast.comparison_pairs`, `validity.reruns_per_arm`; analysis.py 158-162 | high |
| 4c | Planned void | **No pre-registered rule, and no tool for it.** `protocol.json` and `policy.json` contain no "void" key. The only void tool, `evolve/control/void_calibration.py` (commit 9c1468a, branch `cursor/void-stop-calibration-9dd7`, no PR, unreviewed: round-1 flag), refuses anything with `action != "calibrate"` ("not a calibration attempt", L107-108). Voiding 66a07143 would therefore need **new tooling or a hand ledger edit, and neither is acceptable without owner review.** A void appends a receipt and releases a slot (L136-137); it must never turn INCOMPLETE into a decision. | void_calibration.py 3-9, 105-128, 136-190; `rg void` on protocol/policy | high |
| 4d | Re-evaluating the same tree | **Blocked by the workflow as it stands.** `standard_workflow.py` 597-606 raises "duplicate candidate content tier attempt; prior tree retained" for any earlier executed fast eval of the same tree or commit. So a completion run of c1c under fingerprint dcca47b0 is impossible unless a reviewed void-for-evaluation mechanism exists or the protocol changes (new fingerprint). | standard_workflow.py 597-606 | high |
| 6 | KILL | **NOT EVALUABLE** (not passed). Only 1 zram pair, ratio 1.057. The pre-registered statistic is a median over the planned pairs (4). | report `pairs[0]` | high |

## Red-flag calls (partial data: n=2 disk, n=1 zram; not a protocol decision)

Guard = `exp(-noise_log)` from calibration **e8b7a7e3** (CALIBRATED, p90 envelope), `ledger/calibration-fast.json`. Rev7 makes `.p99_ns` metrics **advisory** (`advisory_metric_suffixes`), so they are reported but do not gate.

| Metric | Pair ratios | A/A noise_log → guard | Inside? | c1 round-1 (n=4, median) | Call |
|---|---|---|---|---|---|
| disk seq.mean (primary, scored) | 2.542, 2.846 | 0.0829 → 0.920 | yes, large gain | 3.054 | **noise-free gain** (TCG-only effect) |
| disk seq.p99 (advisory) | 0.856, 0.870 | 0.0939 → 0.910 | **no, both pairs** (log −0.155, −0.139) | 0.941 (pairs 0.912-0.986) | **RED FLAG (advisory)** |
| disk rand.mean (scored) | 0.904, 0.880 | 0.1347 → 0.874 | yes, but 0.880 is only 0.007 log above the guard | 0.942 (0.914-1.040) | **WATCH** |
| disk rand.p99 (advisory) | 0.949, 0.977 | 0.1119 → 0.894 | yes | 0.911 | noise |
| zram seq.mean (scored) | 0.949 | 0.2023 → 0.817 | yes | 1.402 (gain gone, as designed) | noise |
| zram seq.p99 (advisory, KILL metric) | 1.057 | 0.1813 → 0.834 | yes | 0.636 (c1's failure is fixed) | KILL not evaluable; partial looks recovered |
| zram rand.mean / rand.p99 | 1.018 / 1.060 | 0.169 / 0.122 | yes | 0.981 / 0.951 | noise |

**Disk seq.p99.**
- Both pairs are below the guard, and both are below c1's lowest pair (0.912).
- Absolute values: baseline 748938 / 743271 ns, candidate 875040 / 854548 ns.
- The plausible mechanism is that the faulting task waits on a larger I/O (target plus neighbours) on the occasional cold fault, while most faults become cache hits. Readahead lowers the mean but makes the tail heavier.
- c1c adds per-fault costs on top of c1: a `ci->lock` hint check (swap_state.c 792-804), and a `ci->lock` recheck per neighbour after insertion (827-845). These lengthen the critical path a little, which could explain c1c's tail being worse than c1's on the *same* disk mechanism. That last link is a hypothesis; I measured nothing.
- On the readahead window: cluster mode is fixed at page_cluster, so the window does not adapt down. (Inferred: virtio_blk rotational → cluster mode, as noted in the pre-check.)
- Because the metric is advisory, it **would not** produce REGRESSION even if the 4-pair median stayed at about 0.86. It must still be reported as a real candidate tail cost unless completion pairs refute it.

**Disk rand.mean.**
- This is **mechanistically expected**. Random access breaks adjacency only probabilistically: some random faults land next to the previous one, admit readahead, and waste I/O plus cache insertion. Pages are evicted before use (rand hit rate is not reported separately).
- c1 showed the same direction (0.942) and still passed.
- c1c is somewhat worse in this partial (0.892 median of 2) and close to the guard. With 2 more pairs it could fail the **scored** guard, and that *would* be a REGRESSION. Watch.

**Hand CI [0.775, 0.951] for disk seq.p99.**
- The arithmetic reproduces: t(df=1) = 12.71 on the mean log, with log ratios −0.1555 and −0.1393 (mean −0.1474, sd 0.0115).
- With n=2 it rests on a normality assumption that cannot be checked. A df=1 t interval is extremely sensitive.
- It is not a protocol statistic. Use it as a descriptive flag only, never as inference.

## Integrity notes

- **Identity holds throughout.** The report shows `candidate_commit` b69e47c9, `candidate_tree` 58d43c94, fingerprint dcca47b0, `probe_id` bc73887e, `mechanism` = the probe key. The correctness `source_commit` and image d574b737 match the build.
- **Budget.** budget.json shows `guests` 79 and `probe_guests` 15, so 94 rev7 guests, including the reserved but unbooted r2. That is under the round cap of 102 and the hard cap of 111. The candidate set with executed non-probe evals is {c1, c1c}, against `max_candidates` 3.
- **The STOP was intentional.** It was written by `c1c-rerun-watch.sh` at 14:13:12, with the reason text in `campaigns/…/STOP`. It is left in place, which is correct. The watcher is a box-local script, not reviewed harness code. It implemented a coordinator rule that is stricter than protocol, and that is legitimate as an operator budget stop.
- **Host pressure.** Host load rose around the INVALIDs (r1 `after_exit` loadavg_1m 2.66, memory PSI some avg60 2.36). LOG shows RAM available 7838 MiB at 14:14, against 12410 at 13:56. That is consistent with host-side TSC skew under TCG.
- **Do not lose rows.** Whatever is decided, the 9 run rows (including both INVALIDs and the r2 STARTED), the 8 guest directories and `report.json` (status BLOCKED) must be preserved unmodified. Any void must be an **appended** record that references them.

## Next steps for Hurric (owner decisions, in priority order)

**(a) Formal gates on hurricpc-wsl** (not run by anyone yet; suggested order, cheapest and most diagnostic first):
1. `sparse` (C=1) on `mm/swap_state.c`.
2. `gcc_swap_off` (CONFIG_SWAP=n) build, then `gcc_zswap_on` build.
3. **lockdep** (PROVE_LOCKING) boot with the disk swapin and correctness workloads (A2: `ci->lock` under the folio lock in the new paths).
4. **KASAN** with the same workloads, then **KCSAN** (the READ_ONCE hint reads, and the `swap_readahead_info` races that the comment calls advisory).
5. **io-error injection** on the disk backend during readahead (the pre-check's stock-SIGBUS question; io_failure gate).
6. `fail_page_alloc` / `failslab` during readahead (allocation_failure; unwind on charge failure).
7. `memcg_limits`, cgroup v2 and **v1 memsw** (the unwind's swap_cgroup id gap).
8. `large_folio` mTHP enabled, to confirm order-0-only admission (swap_state.c 939, 857) and no mTHP regression.

**(b) Harness and protocol proposals for the final PR** (each needs a PR and owner approval):
1. **A1 runtime test:** async physical backend (disk) **with** zswap enabled, plus forced zswap writeback (`zswpwb > 0`), plus swapoff of the physical backend *under* concurrent faulting load. Require `swap_ra > 0` and a per-path counter for recheck rejects, so the drop path is proven to run.
2. **A `needs_review` result flag** (analysis.py already emits `needs_review: False`) set when an advisory metric breaches its guard in every pair, so the disk seq.p99 case surfaces mechanically.
3. **Rerun and stall handling:**
   - clocksource-fallback mitigation (e.g. `tsc=reliable` or an explicit `clocksource=` in the guest cmdline as a protocol change, with A/A recalibration);
   - a pre-registered **void rule** for evaluations, inside the fingerprinted protocol: who may void, which statuses, and that a void never yields a decision;
   - rows immutable, with the void as an appended record;
   - an arm-specific wall-outlier threshold (zram ~45 s and disk ~65-80 s share one 1.5× factor);
   - arming the first-guest wall gate, which has `wall_median_min_samples` 3 and currently has no prior sample on a fresh case.
4. **Budget sizing** so that one INCOMPLETE is recoverable: reserve at least 1 full pair (4 guests) plus the protocol's 2 reruns per arm per candidate. Today's plan had 1 reserve, and a single flaky arm exhausted it.

**(c) Funding.**
- **A completion run of the c1c fast tier is worth funding only via a protocol change.** The duplicate-tree rule (standard_workflow.py 597-606) blocks a re-evaluation under dcca47b0, and there is no reviewed evaluation-void. Practical route: rev8 (clocksource mitigation plus void rule), recalibrate, then a full 4-pair fast eval of c1c.
- Rough cost: 16 fast guests plus reruns, plus calibration (rev7 used 10 pairs = 40 guests).
- **A KVM arm** is needed before *any* claim about disk: the ~2.5-3× disk seq.mean effect is TCG-only, and the disk tail flag might be a TCG I/O-emulation artefact. I recommend it as a separate owner decision after the formal gates.

**(d) Process.**
- rev7 is still PR #8, **unmerged with no recorded owner approval**. Every rev7 verdict, this one included, is provisional until it is approved.
- The void tooling (`cursor/void-stop-calibration-9dd7`, 9c1468a) has **no PR**. It and `c1c-rerun-watch.sh` / `watchdog.sh` (box-local operator scripts that wrote STOP files) belong in the PR bundle for review.
- Commit the candidate records (`candidates/` is untracked) at the candidate boundary.

## Limitations

- No guest, rerun, build or tool execution by me. Evidence is files, git and greps only.
- The 2c attribution (c1's 4104 came from the swapoff/unuse readahead) is an inference from code and workload structure. No per-path counter exists.
- The red-flag calls use partial n=2/n=1 data and are not protocol decisions. A guard comparison on 2 pairs has low power and a high variance median.
- Guards come from calibration e8b7a7e3 (p90 envelope of 10 A/A pairs). I did not re-derive the envelope.
- The serial-log grep cannot detect lockdep or KASAN findings on a non-instrumented build.
- rev7 approval status, and the coordinator's 111 cap and C3 rule, come from the LOG and the coordinator. They are not in a committed policy file.
