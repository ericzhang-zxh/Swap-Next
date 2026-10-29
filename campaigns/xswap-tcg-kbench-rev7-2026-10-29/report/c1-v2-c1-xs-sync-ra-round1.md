# Round-1 review: c1 `v2-c1-xs-sync-ra` @31eb4618 vs baseline `kb-xs-desc-v1` @5e84ca92

Campaign `xswap-tcg-kbench-rev7-2026-10-29` (TCG kbench rev7). Workflow checkout 9c1468ac, fingerprint dcca47b0. Bzimage image_sha c9dd4ea3. The review is read-only: nothing was built, booted, run, committed or pushed. Times are PDT (UTC−7).

## Verdict: **NEEDS-MORE-EVIDENCE** (fail-closed)

- **The screen result stands under the frozen rules.** The FAST_PASS (eval 68de12e0) was computed correctly under the rev7 rules. The 5 protocol correctness gates passed, on the disk backend only.
- **It is not a basis for acceptance.** The FAST_PASS is a non-regression screen. It does not show a zram win: the t-CI crosses 0, one of 4 pairs is a loss, and the baseline has a high pair. There is also a consistent zram seq.p99 regression (median 0.636), which was pre-registered as advisory. 10 of the 18 policy `required_gates` were never run. One kernel assumption with a SIGBUS consequence is open.
- **There is no next tier to accept into.** rev7 has "No slow tier" (protocol.json), and `eligible_for_slow` is false. Any slow or KVM confirmation needs Hurric's explicit approval (AGENTS.md L45-51, L268-270). ACCEPT-TO-NEXT-TIER is not available.
- **Process blocker, outside c1.** rev7 is an unmerged proposal (PR #8). Its own `approval` field says it does not open a campaign. Calibration was unblocked by void tooling from a branch that has no PR. The repo has no record of Hurric's approval to open rev7. Until he confirms it, every rev7 verdict is a diagnostic only.

## Summary table

| Check | Result | Evidence path / hash | Confidence |
|---|---|---|---|
| Diff identity | The patch file equals `git diff 5e84ca92 31eb4618`. Parent = baseline. Only `mm/swap_state.c` changes (+94/−10). | `patches/v2-c1-xs-sync-ra.patch` sha256 3d336c64… | high |
| Scope / size | In allowlist. 1/8 files, 104/1000 lines. Note: the base policy cap is 300; rev7 raised it to 1000. | `static.json` SCOPE_PASS; campaign `policy.json` d4ce3a0d… | high |
| checkpatch / diff-check | 0 errors / 0 warnings. diff-check clean. | candidate static evidence | high |
| sparse_no_new_diagnostics | **NOT RUN** | — | high (absent) |
| gcc_swap_on | Built (image c9dd4ea3; mtimes 09:35, reused) | build record | medium |
| gcc_swap_off / gcc_zswap_on | **NOT RUN** (no evidence of those configs) | — | high (absent) |
| Protocol correctness gates (data_roundtrip, fork_cow, concurrent_fault, swapoff_live_pages, no_new_kernel_warnings) | PASS. 1 guest, **disk backend only**. Readahead was exercised: swap_ra 4104, swap_ra_hit 7. zswpout 0, so the zswap-mixed path was not hit. | `runs/guests/c1-v2-c1-xs-sync-ra-correctness-1/result.json` sha256 71332a27…, `serial.log` eca71fdd… | high |
| allocation_failure, io_failure, memcg_limits, large_folio, lockdep, kasan, kcsan | **NOT RUN.** These are policy formal-acceptance gates (AGENTS.md L30-33). | — | high (absent) |
| Guest boot / cmdline identity | Matches the image_sha in the cmdline | serial.log | high |
| min pairs | n=4 = protocol `tiers.fast.comparison_pairs` 4. Below policy `measurement.min_pairs` 10. | protocol.json a058b8f5…; policy.json | high |
| Fast decision | FAST_PASS, overall median ratio 2.058. `eligible_for_slow` false. | ledger row 68de12e0 | high |
| Disk seq.mean | Median ratio 3.054 (pairs 3.203/3.018/2.847/3.090). Far above the noise of 0.0864. | 68de12e0 | high (TCG-specific) |
| Zram seq.mean | Median 1.402. Pairs 1.304/0.955/1.508/1.767. t-CI [−51.2%, +12.4%] crosses 0. | 68de12e0; `c1-fast-summary.txt` | low–medium |
| Zram seq.p99 (advisory) | Median 0.636. 3 of 4 pairs worse. Guard false. Advisory status was pre-registered. | protocol `advisory_metric_suffixes`, committed ab800d7 10:03 | high (pre-reg); high (regression is real) |
| Rand guards | Disk rand.mean 0.942 and zram rand.mean 0.981, both inside noise | 68de12e0 | medium |
| Mechanism | swap_ra goes from 0 to 114684 on zram (= 7/8 of 131072 seq samples). swap_ra_hit ≈ swap_ra. pgmajfault 262140 → 147456. | 3a554e3b probe; 68de12e0 vmstat | high |
| A/A calibration | e8b7a7e3 CALIBRATED. Zram seq.mean noise 0.2242 (log 0.2023). | ledger e8b7a7e3 | high |
| Reruns | 3 stall reruns, all within pre-registered validity rules. Originals retained. | e8b7a7e3 / 68de12e0 `runs` | high |
| Watchdog 9/40 → 9/56 | External executor monitor, outside the fingerprint. No scoring effect. | `watchdog.sh`, `watchdog.log` 12:06:03 | high |
| Voids a7930c57, 820fdc14 | Mechanical reasons, no scorable data, both before c1 existed. **But the tool is unreviewed core code, written after the failures it voids, and it mutates the original rows.** | `void-receipt*.json`; 9c1468ac/87dc7357 `void_calibration.py` L185-186 | high |
| Ledger timestamps / hashes | Consistent. cb3c6a09 (controller `protocol_hash`) and a058b8f5 (protocol.json file sha) are two different definitions, not a mismatch. | ledger.json | high |
| Direct scaffolding on main after the rule | None. origin/main HEAD is 25ad0ab9 (02:06). No commits since. | GitHub `list_commits main` | high |

## Kernel findings (`mm/swap_state.c` @31eb4618)

### Confirmed defects

None confirmed by reading.
- **Refcounts:** each neighbour folio gets a `folio_put`. The target ref is returned. A NULL return from `swapin_readahead` falls back to the existing sync path.
- **Locking:** the cluster lock is a spinlock, held only for the hint check. Nothing is allocated under it.
- **Large folios:** the `orders == BIT(0)` gate excludes them in `swapin_sync`. `swap_update_readahead` returns early for large folios.

### Unresolved assumptions (each needs evidence before acceptance)

1. **Speculative neighbour read of an xswap slot that has no backing (high consequence).**
   - Trigger: `xswap_readahead_wanted` (L778-793) samples the backend hint under `swap_cluster_lock_unpinned`, then drops the lock. The read happens later (TOCTOU).
   - Mechanism: if the slot is in use but has no phys, no zswap entry and no swapcache folio at read time (zswap store, refusal or writeback transitions), `swap_read_folio` in page_io.c takes the `WARN_ON_ONCE(1)` path. It unlocks a `!uptodate` folio, which stays in the swap cache.
   - Consequence: the real fault later sees a `!uptodate` folio and SIGBUSes (memory.c:5078).
   - Before the patch only demand faults reached this path. Now 7 speculative neighbours per fault do.
   - The correctness run had zswpout 0, so this path was never tested. Needs a trace of the xswap backend state machine plus a mixed zswap+phys stress test with writeback.
2. **Lock context of `ci->lock`.** The plain `spin_lock` in the hint check follows the existing page_io.c pattern. The added acquisitions per fault (gate + target + each neighbour) were never checked with lockdep.
3. **Swapoff behaviour change.** `try_to_unuse` → `swapin_readahead` (swapfile.c:3070) now reads ahead xswap physical neighbours. Before, xswap skipped readahead at device level. The commit message does not say this. `swapoff_live_pages` passed on disk only.
4. **Asymmetric filter in VMA mode.** In `swap_vma_readahead` (L1136-1142) the filter applies only to neighbours. A zswap-resident target reached through swapoff or VMA mode still triggers physical neighbour reads. This contradicts "keep compressed targets on the single-folio path", which holds in cluster mode only.
5. **Device pinning.** The physical backend device is not pinned by `get_swap_device` during a neighbour read. This is pre-existing, but the patch widens it from one target to up to 7 neighbours.
6. **memcg.** Neighbour folios are charged in fault context under the memcg limit (GFP_HIGHUSER_MOVABLE, possible direct reclaim). `memcg_limits` and `allocation_failure` were not run.

### Design observations and optional suggestions

- **The patch routes around a scope exclusion.** `swapin_sync` now calls `swapin_readahead` when `vmf && orders==BIT(0) && gate` (L847-873). This side-steps the `mm/memory.c` exclusion and overloads "sync" semantics. Suggestion: rename it, or document it at the call sites (memory.c:4986-5020, shmem.c:2266).
- **The VMA history is written on every xswap fault** (L804-827): on every non-adjacent fault, and on every adjacent fault in cluster mode. xswap faults also feed the global cluster-readahead hit state. Expect cache-line traffic on shared VMAs. Not measured.
- **Zram cost shift (probable p99 mechanism).** On a SYNCHRONOUS_IO backend, the faulting task now decompresses the whole window inline before it returns. This explains a lower mean together with a higher p99: candidate p99 226k–340k ns vs baseline 151k–241k ns. Report it as a real regression next to the win (CODE_PATTERNS), not as noise. Suggestion: a smaller window, or async neighbours, for synchronous backends.
- **The lineage is not cited.** c1 is the H6+H7 lineage (`<box>/swap-next-proposals/H7-xs-ra-cluster-v2.md`; H6 was screened under KVM in xswap-next-2026-10-24, disk −40%). `c1-selection-reason.txt` and `c1-hypothesis.txt` do not mention this. It is a different protocol, so there is no forking-paths problem inside rev7. The report should still cite the lineage.

## Statistics

- **n=4 is enough for the screen, not for acceptance.** It meets the protocol's fast `comparison_pairs` (4) and the analysis.py median rule (≥4). It does not meet policy `min_pairs` 10. With 4 pairs the smallest exact sign-test p is 0.125 (two-sided), even for 4/4.
- **What FAST_PASS means.** In `analysis.compare()` with decision "median", every non-advisory metric must have a median log ratio ≥ −noise. Nothing requires the primary metric to improve beyond noise. So a zram t-CI crossing 0 still counts as FAST_PASS, and that is internally consistent. As a non-regression screen the rule is sound. It cannot support a win claim. The zram line is "neutral-to-positive, unresolved".
- **Effects against the A/A envelope (e8b7a7e3).**
  - Disk seq.mean: log(3.054) = 1.12, about 13× the 0.0864 noise. All 4 pairs are far above it.
  - Zram seq.mean: log(1.402) = 0.338, about 1.67× the 0.2023 noise. But pair 1 is 0.955, a loss.
  - Baseline zram pair 3 is 56040 ns, above the A/A valid range of about 34.8k–49.3k. Without it, the median would be about 1.304–1.508.
  - My recomputation of the zram nearest-rank p90 reproduces 0.2023 (pair 3). The stall-affected A/A pair 0 (0.351) is rank 10 and does not set the envelope.
- **The p99 "ADVISORY" label was pre-registered.** `advisory_metric_suffixes [".p99_ns"]` and "p99 latency is advisory" are in protocol.json, committed in ab800d7 at 10:03, before the 10:21 open. It is not a post-hoc relabel. The regression itself is consistent (3/4 pairs) and mechanistic, so it must be reported.
- **Disk 3.054× is plausible in mechanism, but TCG inflates it.**
  - The counters support it: 7/8 of seq faults become swap-cache hits, candidate seq p50 is about 10–16k ns vs baseline 160–178k, and disk walls drop from 78–91 s to 60–65 s.
  - The size is TCG-specific. Each emulated virtio request is expensive, so the saving per avoided request is inflated.
  - The H7 proposal's own TCG estimate was −35% to −55%. The observed −67% exceeds it.
  - There is no KVM arm, and AGENTS.md forbids comparing across accelerators. Treat 3.05× as a TCG screen effect only.

## Mechanism

- **Did swap_ra move because of this patch?** Yes.
  - Baseline swap_ra is 0 by construction (xswap readahead was disabled, and rev6 recorded swap_ra 0).
  - The candidate shows swap_ra 114684 = 7/8 × 131072 seq samples, swap_ra_hit ≈ swap_ra, pgmajfault −44%, and pswpin unchanged.
  - c1's parent is the baseline, so there is no inherited contribution.
- **Is it the targeted counter?** Yes. It is the declared `swapin-zram-64k:swapin_vmstat_delta.swap_ra:up` from c1-hypothesis.txt, and it matches the protocol's round-1 keys.
- **What it does not show.** The mechanism is fully engaged on zram, yet the zram mean gain is unresolved and p99 regresses. On a synchronous backend the saved faults are partly paid for by inline decompression.

## Integrity

- **Stall reruns.**
  - Calibration: 0-zram-a INVALID clocksource_fallback; 2-disk-a INVALID twice (clocksource+wall_time_outlier, then wall_time_outlier).
  - Fast: 3-disk-a (baseline) INVALID wall_time_outlier at 123.1 s.
  - All follow the pre-registered validity rules (reruns_per_arm 2), and the invalid attempts are kept in `runs`.
  - Caveat 1: the wall-outlier median mixes both arms (standard_workflow.py ~L640-745). The fast candidate's disk walls (60–65 s) lower the threshold, so slow baseline runs are more likely to be invalidated. 123 s exceeds even a baseline-only threshold (about 1.5 × 78–91 s), so the outcome here is unchanged.
  - Caveat 2: the wall gate was not armed for the first zram guest (0 prior walls). It admitted a stall-affected 0-zram-a-r1 (82.3 s, the highest baseline zram value) into calibration. This had no effect on p90.
  - There is a standing tension with "slow samples never dropped": validity invalidation is a pre-registered exception, and it should be listed in the report.
- **Watchdog cap 9/40 → 9/56 (12:06:03).** The watchdog is an executor safety monitor outside the fingerprint. It only touches STOP. The raise left room for protocol-allowed reruns, and the hard cap of 111 is unchanged. It was applied mid-calibration, and the candidate rounds had equivalent headroom (12/76). It cannot affect scores.
- **Voids.**
  - a7930c57 (false watchdog STOP; 7 PASS A/A guests discarded) and 820fdc14 (pre-QEMU host-RAM refusal, no guest booted) both predate c1 (created 12:58). Neither carries scorable or candidate data.
  - Process risk:
    - The void tool clears `execution_started` and sets `void_receipt` on the original rows (`void_calibration.py` L185-186). This defeats the frozen "no calibration retry under this fingerprint" gate (standard_workflow.py L571-579). The original value survives only in the receipt.
    - The void criteria were written after the failures they void: 9c1468a at 11:17, after the 10:46 block, and 87dc735 at 11:42, after the 11:21 failure.
    - 820fdc14 ran a tool extracted from 87dc7357 while the 9c1468ac tree was checked out. That is mixed code, and the void tool is not in the fingerprint.
  - I found no sign of calibration shopping, because both reasons are mechanical and logged externally. The mechanism should still be owner-reviewed before it is reused.
- **Ledger.** 9 rows, all fingerprint dcca47b0, chronological and consistent with LOG.md and the receipts. Proof result sha 71332a27 matches the file on disk.

## Process

- **rev7 is an unmerged proposal.** PR #8 (`cursor/tcg-protocol-rev7-metadata-aa91`, head ab800d77) is open and not merged (opened 10:04). Its body and protocol `approval` field say it "does not open a campaign". AGENTS.md L268-270 says a new TCG revision needs Hurric's explicit approval, and AGENTS.md on main still says rev7 is "Proposed, not opened". The campaign was opened at 10:21 on that checkout. I found no recorded approval from Hurric; the coordinator should produce it or obtain it.
- **The void tooling bypassed PR review.** The workflow checkout 9c1468ac and the void tooling (9c1468ac, 87dc7357) are on `cursor/void-stop-calibration-9dd7`, which **has no PR** (not among PRs #3–#8). That is core controller code (AGENTS.md L112-118), it changed calibration-retry behaviour, and it was used in the run without owner review. This is a breach of the "scaffolding via PR" rule in effect, though not a commit to main.
- **Main is clean.** No direct scaffolding commits after Hurric's ~15:51 rule; origin/main HEAD is still 25ad0ab9.
  - Earlier: PR #7 (rev6 scaffolding) was merged 40 s after it opened (02:05 → 02:06) by account `ericzhang-zxh`. That predates the rule, and I cannot tell whether a bot did it (low confidence).
  - The 2026-10-27/28 scaffolding commits authored by Eric Zhang directly on main also predate the rule.
- **Campaign artefacts are local only.** The campaign dir is mostly untracked locally, and README.md and lines/xswap.md have unstaged changes. Nothing has been committed for rev7 except the PR #8 files.

## Parent-for-round-2 judgement

- **Not a sound parent yet.**
  - AGENTS.md L242-244 (Grok Bot loop) says "Every candidate's parent is the campaign baseline". controller.py L303-309 accepts an exact parent commit. Until Hurric resolves that conflict, round-2 candidates should use the baseline as parent.
  - c1 follow-ups can still be built from the baseline as cumulative diffs that include c1's change. Scope and line limits apply to the cumulative diff.
- **Acceptable inside the exploratory population**, as a neutral-to-positive screen (AGENTS.md "Evolution"). It is not baseline-advancing: zram does not exceed noise with a resolved CI, and the scored p99 guard failed (advisory).
- **Upgrade it to a candidate parent only if** the SIGBUS assumption is closed and the zswap-mixed correctness test passes.

## Next steps for the hypothesis bot

1. **Close assumption 1.** Trace xswap slot states: store, refusal, writeback, shrink. Show that a slot with neither phys nor zswap nor swapcache is unreachable to a speculative read. Otherwise re-check under `ci->lock` at read time, or skip `swap_read_folio` for an unbacked slot and drop the folio without leaving a `!uptodate` cache entry.
2. **Propose a correctness run on zswap-mixed xswap.** zswap enabled, with writeback forced (zswpout>0, zswpwb>0), plus swapoff under load. Do not run it in this review.
3. **Address the zram p99 cost shift.** Make the window size depend on the backend (`SWP_SYNCHRONOUS_IO` physical backend → smaller window, or async neighbour submission). Pre-register p99 as the kill criterion: median p99 ratio ≥ 0.90.
4. **Make swapoff behaviour explicit.** Either restore the xswap skip for the `try_to_unuse` path, or document and test it. Apply the zswap-target rule in VMA mode too (assumption 4).
5. **Run the formal-acceptance gates before any acceptance claim.** Request on hurricpc-wsl (owner-gated): sparse, gcc_swap_off/gcc_zswap_on, lockdep, KASAN, KCSAN, failslab/fail_page_alloc and io-error injection, memcg limits, a large-folio (mTHP 64K swapin) configuration.
6. **Correct the lineage and expectations in the reports.** Cite the H6/H7 lineage in c1's record. State the disk effect as TCG-only, with KVM confirmation an open owner decision.
7. **Raise the process items with the coordinator.** Get Hurric's approval for rev7, and open a PR for the void tooling (9c1468ac/87dc7357) before more rev7 verdicts are recorded.

## Limitations / checks not performed

- **Builds and analysers.** No compile, sparse, gcc_swap_off/zswap_on build, lockdep, KASAN, KCSAN or fault injection (they would run on hurricpc-wsl; deliberately not run).
- **Guests.** No guest, benchmark or rerun was reproduced. All numbers are read from the ledger and run files under `campaigns/xswap-tcg-kbench-rev7-2026-10-29/` and `<box>/runs/grok-cloud-tcg-rev7-20261029/`.
- **Untested configurations.** No zswap-mixed correctness evidence exists, and there is no KVM arm.
- **Kernel analysis is by reading only** (31eb4618 swap_state.c; memory.c, page_io.c, swapfile.c, shmem.c context). The xswap state machine was not traced end to end.
- **GitHub state** was read through the connector on 2026-10-29. The local origin refs were not fetched.
- **Owner approval** for rev7 could not be verified from the repo or PRs.
