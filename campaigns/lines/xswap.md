# xswap line

Campaigns in opening order, with their recorded baselines and outcomes.

Fixed line anchor: `37de636c972a413f5c25e5b6c891fb4df2f53aed`. This is an identity, not an inferred root-relative performance result.

## xswap-2026-10-21

Status: closed; machine: hurricpc; opened: 2026-10-21; closed: 2026-10-21.

Baseline: `37de636c972a413f5c25e5b6c891fb4df2f53aed`.

Baseline origin: upstream or imported reference.

[Campaign report](../xswap-2026-10-21/report/README.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [xswap-grow-cap8](../xswap-2026-10-21/candidates/xswap-grow-cap8.json) | closed | Eight pilot boots passed. Zswap growth count fell to 13 from 15-16, but retention and latency do not justify promotion under the noisy baseline. |
| [xswap-grow-target75](../xswap-2026-10-21/candidates/xswap-grow-target75.json) | closed | Eight pilot boots passed. Tighter target increased growth operations to 18-19 disk and 23 zswap, with mixed mapping/latency outcomes. No performance acceptance or promotion. |
| [xswap-shrink-min4](../xswap-2026-10-21/candidates/xswap-shrink-min4.json) | closed | Eight pilot boots passed; no promotion: mixed metadata effects and large A/A state variation. Zswap retained more mapped clusters on average. |
| [xswap-source](../xswap-2026-10-21/candidates/xswap-source.json) | closed | Upstream series imported and built as independent reference; not an optimized candidate or performance acceptance |

## xswap-reference-replay

Status: closed; machine: hurricpc; opened: 2026-10-21; closed: 2026-10-21.

Baseline: `9a0542b19a541eda3f82934ee747c61ec3f18847`.

Baseline origin: upstream or imported reference.

| Candidate | Status | Reason |
| --- | --- | --- |
| [xswap-reference-replay](../xswap-reference-replay/candidates/xswap-reference-replay.json) | closed | Exact commit and tree replay verified; reference remains experimental. |

## xswap-observe-2026-10-22

Status: closed; machine: hurricpc; opened: 2026-10-22; closed: 2026-10-22.

Baseline: `37de636c972a413f5c25e5b6c891fb4df2f53aed`.

Baseline origin: upstream or imported reference.

| Candidate | Status | Reason |
| --- | --- | --- |
| [xs-observe-v1](../xswap-observe-2026-10-22/candidates/xs-observe-v1.json) | closed | Observation baseline built in namespaces; fresh disk and zswap smoke guests passed all pilot gates. Frozen as structural campaign reference, not a performance candidate. |

## xswap-structure-2026-10-22

Status: closed; machine: hurricpc; opened: 2026-10-22; closed: 2026-10-26.

Baseline: `4f83412c1d59eaf6a4d2460cb47fe0177a3be0c4`.

Baseline origin: upstream or imported reference.

[Campaign report](../xswap-structure-2026-10-22/report/README.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [xs-lockassert-v1](../xswap-structure-2026-10-22/candidates/xs-lockassert-v1.json) | closed | Isolated one-line assertion repair passed same-config lockdep disk control with all data/lifecycle/no-warning gates; baseline and tailcache v1 reproduced original warning. Retain repair, no performance or promotion claim. |
| [xs-lowfree-v1](../xswap-structure-2026-10-22/candidates/xs-lowfree-v1.json) | closed | 40/40 pilot gates pass; exploratory mean retention lower but regimes overlap and zswap mean p99 regresses 5.8 percent. Inconclusive discovery candidate, not accepted or promoted. Follow up independent bounded cache-only tail reclamation. |
| [xs-tailcache-v1](../xswap-structure-2026-10-22/candidates/xs-tailcache-v1.json) | closed | Lockdep disk smoke failed no-warning gate. Same warning reproduced on observation baseline; xswap_grow asserts untranslated per-CPU lock address. Stop performance comparison, retain failed boot, isolate assertion repair then revalidate revised candidate. |
| [xs-tailcache-v2](../xswap-structure-2026-10-22/candidates/xs-tailcache-v2.json) | closed | Lifecycle cleanup, no performance conclusion. Listed in blocked_commits pending descriptor lifetime review when the campaign ended. |

## xswap-p123-2026-10-23

Status: closed; machine: hurricpc; opened: 2026-10-23; closed: 2026-10-26.

Baseline: `b2beda7fe460f911b88d27890993347588d70748`.

Baseline origin: upstream or imported reference.

[Campaign report](../xswap-p123-2026-10-23/report/README.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json) | closed | Lifecycle cleanup, no performance conclusion. Commit 5e84ca92 became the baseline of xswap-next-2026-10-24 and xswap-tcg-rev3-2026-10-25, which superseded this campaign. |

## xswap-p123-lifetime-20261023

Status: closed; machine: hurricpc; opened: 2026-10-23; closed: 2026-10-26.

Baseline: `b2beda7fe460f911b88d27890993347588d70748`.

Baseline origin: upstream or imported reference.

| Candidate | Status | Reason |
| --- | --- | --- |
| [p123-lifetime-rcu](../xswap-p123-lifetime-20261023/candidates/p123-lifetime-rcu.json) | closed | Lifecycle cleanup, no performance conclusion. Never checked; the descriptor lifetime repair in 5e84ca92 was adopted as the baseline instead. |

## xswap-phase3-import

Status: closed; machine: hurricpc; opened: 2026-10-23; closed: 2026-10-23.

Baseline: `37de636c972a413f5c25e5b6c891fb4df2f53aed`.

Baseline origin: upstream or imported reference.

| Candidate | Status | Reason |
| --- | --- | --- |
| [xswap-phase3-import](../xswap-phase3-import/candidates/xswap-phase3-import.json) | closed | Phase III applied cleanly on 37de636c; tree 187cfe49 verified; scope, diff-check and checkpatch pass. Reference remains experimental. |

## xswap-swapin-2026-10-23

Status: closed; machine: hurricpc; opened: 2026-10-23; closed: 2026-10-23.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: [xswap-p123-2026-10-23/xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json), commit `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Origin evidence: [correctness review](../xswap-swapin-2026-10-23/report/lifetime-review.md).

[Campaign report](../xswap-swapin-2026-10-23/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [xs-ra-phys-v1](../xswap-swapin-2026-10-23/candidates/xs-ra-phys-v1.json) | closed | Fast evaluation 8a4b89fc0c8e44dd80c7675ef9c8c0fb REGRESSION: disk random p99 baseline/candidate 0.90495 below calibrated guard; no slow evaluation or promotion. |
| [xs-ra-zswap-v1](../xswap-swapin-2026-10-23/candidates/xs-ra-zswap-v1.json) | closed | Fast evaluation 31cced4875f8470dbdde1dd557fca236 REGRESSION: zswap sequential p99 baseline/candidate0.262609; sequential mean gain0.407% below3%noise. No slow evaluation or promotion. |

## confirm-h1-ra-phys-2026-10-23

Status: closed; machine: hurricpc; opened: 2026-10-24; closed: 2026-10-24.

Baseline: `unknown`.

Baseline origin: [xswap-p123-2026-10-23/xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json), commit `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Origin evidence: [correctness review](../xswap-swapin-2026-10-23/report/lifetime-review.md).

| Candidate | Status | Reason |
| --- | --- | --- |

## xswap-next-2026-10-24

Status: closed; machine: hurricpc; opened: 2026-10-24; closed: 2026-10-24.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: [xswap-p123-2026-10-23/xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json), commit `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Origin evidence: [correctness review](../xswap-swapin-2026-10-23/report/lifetime-review.md).

[Campaign report](../xswap-next-2026-10-24/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [xs-ra-cluster-v1](../xswap-next-2026-10-24/candidates/xs-ra-cluster-v1.json) | closed | REJECT_FAST: report 9ec21a04b74b4d46a7931c16112a6bdb records useful physical prefetch and disk seq mean -40.19%, but disk random p99 +29.46% and compressed random mean +7.96% fail guards. Targeted KASAN/lockdep, both release correctness backends and CONFIG_SWAP=n build pass. Retain the tradeoff; no slow confirmation or promotion. Two pairs leave causal attribution and between-run variation unresolved. |
| [xs-ra-sequential-v1](../xswap-next-2026-10-24/candidates/xs-ra-sequential-v1.json) | closed | REGRESSION in fast report 49add9b084d04941a459281838bbf3f3: disk seq p99 and rand p99 fail. swap_ra=0 in both candidate disk runs; source VMA-only admission is inactive with the rotational guest backend. Keep failed evidence; no causal speed claim, slow run or promotion. |
| [xs-zswap-linear-v1](../xswap-next-2026-10-24/candidates/xs-zswap-linear-v1.json) | closed | REJECT_FAST: report 15ded9c2bdf44b5fae1b3e83f0f75daf fails all four compressed latency guards; zswap seq mean +24.39%. Both release correctness backends and targeted KASAN/lockdep correctness pass. Disk-path movement has no matching mechanism and is not credited. Retain evidence, no slow tier or promotion. |

## xswap-tcg-rev3-2026-10-25

Status: closed; machine: grok-cloud; opened: 2026-10-25; closed: 2026-10-28.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: [xswap-p123-2026-10-23/xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json), commit `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Origin evidence: [correctness review](../xswap-swapin-2026-10-23/report/lifetime-review.md).

| Candidate | Status | Reason |
| --- | --- | --- |

## kbench-smoke-2026-10-27

Status: closed; machine: hurricpc; opened: 2026-10-28; closed: 2026-10-28.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: [xswap-p123-2026-10-23/xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json), commit `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Origin evidence: [correctness review](../xswap-swapin-2026-10-23/report/lifetime-review.md).

[Campaign report](../kbench-smoke-2026-10-27/report/README.md)

| Candidate | Status | Reason |
| --- | --- | --- |

## xswap-tcg-kbench-2026-10-29

Status: closed; machine: grok-cloud; opened: 2026-10-29; closed: 2026-10-29.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: [xswap-p123-2026-10-23/xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json), commit `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Origin evidence: [correctness review](../xswap-swapin-2026-10-23/report/lifetime-review.md).

| Candidate | Status | Reason |
| --- | --- | --- |

## xswap-tcg-kbench-rev7-2026-10-29

Status: open; machine: grok-cloud; opened: 2026-10-29; closed: —.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: [xswap-p123-2026-10-23/xs-desc-lifetime-v1](../xswap-p123-2026-10-23/candidates/xs-desc-lifetime-v1.json), commit `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Origin evidence: [correctness review](../xswap-swapin-2026-10-23/report/lifetime-review.md).

| Candidate | Status | Reason |
| --- | --- | --- |
| [v2-c1-xs-sync-ra](../xswap-tcg-kbench-rev7-2026-10-29/candidates/v2-c1-xs-sync-ra.json) | closed | Round 1 complete: FAST_PASS 68de12e0 (non-regression screen). Swap Review NEEDS-MORE-EVIDENCE (campaigns/xswap-tcg-kbench-rev7-2026-10-29/report/c1-v2-c1-xs-sync-ra-round1.md): zram seq.p99 regression and an open SIGBUS TOCTOU; not a parent per review. Superseded by c1c (baseline-parented, same mechanism plus safety gate). Closed to free the single active-candidate slot; worktree, branch and build kept as evidence. |
| [v2-c1c-xs-ra-safe](../xswap-tcg-kbench-rev7-2026-10-29/candidates/v2-c1c-xs-ra-safe.json) | active | — |

Voided calibration attempts:

| Attempt | Tier | Receipt | Guests | Reason |
| --- | --- | --- | --- | --- |
| 16fe9d242ebb4609a14a13fc119ace56 | fast | a7930c5706ca4578b8f5b37369b1efc0 | 16fe9d242ebb4609a14a13fc119ace56-0-swapin-disk-a PASS, 16fe9d242ebb4609a14a13fc119ace56-0-swapin-disk-b PASS, 16fe9d242ebb4609a14a13fc119ace56-0-swapin-zram-64k-a PASS, 16fe9d242ebb4609a14a13fc119ace56-0-swapin-zram-64k-b PASS, 16fe9d242ebb4609a14a13fc119ace56-1-swapin-disk-b PASS, 16fe9d242ebb4609a14a13fc119ace56-1-swapin-disk-a PASS, 16fe9d242ebb4609a14a13fc119ace56-1-swapin-zram-64k-b PASS | Fast calibration 16fe9d24 ended after a false campaign STOP from an external watchdog that treated an exiting TCG QEMU with an empty cmdline as non-TCG. No KVM or safety event occurred. |
| 0c2cd749d6594a7b9c6c3576b97b3d25 | fast | 820fdc14891e4413875cd25e2034ed3c | 0c2cd749d6594a7b9c6c3576b97b3d25-0-swapin-disk-a STARTED | Fast calibration 0c2cd749 reserved 0-swapin-disk-a then run.py refused before QEMU: need 5120 MiB available host RAM because the virtio balloon left about 4.6 GiB MemAvailable. No guest booted. |

Current baseline: 5e84ca928deeacb4eee656806a003f27d1eca82f (xswap-tcg-kbench-rev7-2026-10-29)
