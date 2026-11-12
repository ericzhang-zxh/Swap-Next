# xswap-compression-tiering line

Campaigns in opening order, with their recorded baselines and outcomes.

Fixed line anchor: `5e84ca928deeacb4eee656806a003f27d1eca82f`. This is an identity, not an inferred root-relative performance result.

## codex-compress-lib-2026-11-10

Status: closed; machine: hurricpc; opened: 2026-11-10; closed: 2026-11-10.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

[Campaign report](../codex-compress-lib-2026-11-10/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-v1](../codex-compress-lib-2026-11-10/candidates/c1-shared-store-v1.json) | closed | Infrastructure-incomplete: the frozen c1-debug input sets SLUB_TINY=y, which disables the required KASAN. K1 compiled but no candidate guest or timing ran. Preserve this contract, code and spent 3 guests/3 builds; a separately frozen corrected C1 contract must deduct these costs and elapsed time from the original phase caps, with no reset or candidate outcome claim. |

## codex-compress-lib-r2-2026-11-10

Status: closed; machine: hurricpc; opened: 2026-11-10; closed: 2026-11-10.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

[Campaign report](../codex-compress-lib-r2-2026-11-10/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-r2](../codex-compress-lib-r2-2026-11-10/candidates/c1-shared-store-r2.json) | closed | Infrastructure-incomplete: the retained c-debug run completed but strict parsing rejects the expected invalid-codec diagnostic; diagnostic-only replay also identifies false rejection of KUnit zero-skip summaries. Preserve original raw and counted costs (two probe guests, one build). No timing occurred. Continue only under corrected trusted parsing with remaining original logical-phase resources and deadline, unchanged kernel source, and fresh counted correctness evidence. |

## codex-compress-lib-r3-2026-11-10

Status: closed; machine: hurricpc; opened: 2026-11-10; closed: 2026-11-10.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

[Campaign report](../codex-compress-lib-r3-2026-11-10/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-r3](../codex-compress-lib-r3-2026-11-10/candidates/c1-shared-store-r3.json) | closed | Infrastructure-incomplete: the two-node correctness guest triggered topology_sane during boot because the trusted implicit single-package CPU topology conflicts with the two NUMA nodes. Preserve the failed warning gates and all three counted attempts; stop this frozen protocol before a separately reviewed topology correction. |

## codex-compress-lib-r4-2026-11-10

Status: closed; machine: hurricpc; opened: 2026-11-10; closed: 2026-11-10.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

[Campaign report](../codex-compress-lib-r4-2026-11-10/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-r4](../codex-compress-lib-r4-2026-11-10/candidates/c1-shared-store-r4.json) | closed | Infrastructure-incomplete: the explicit two-socket NUMA guest passed all functional and kernel-warning gates, but the frozen validity check rejected boot-time TSC instability and HPET fallback. Preserve its original integration_pass=true and run_valid=false, both counted attempts, and the frozen contract. No timing or full correctness acceptance. |

## codex-compress-lib-r5-2026-11-10

Status: closed; machine: hurricpc; opened: 2026-11-10; closed: 2026-11-10.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

[Campaign report](../codex-compress-lib-r5-2026-11-10/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-r5](../codex-compress-lib-r5-2026-11-10/candidates/c1-shared-store-r5.json) | closed | calibrate failed; inspect campaigns/codex-compress-lib-r5-2026-11-10/runs/session/action-a38c3d737d1e3842e1c39e21-0dd8a119.log. Retain all started attempts. |

## codex-compress-lib-r6-2026-11-10

Status: closed; machine: hurricpc; opened: 2026-11-10; closed: 2026-11-11.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

[Campaign report](../codex-compress-lib-r6-2026-11-10/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-r6](../codex-compress-lib-r6-2026-11-10/candidates/c1-shared-store-r6.json) | closed | Campaign deadline exhausted; retain all attempts and finish report delivery. |

## codex-compress-lib-r7-2026-11-11

Status: closed; machine: hurricpc; opened: 2026-11-11; closed: 2026-11-11.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

[Campaign report](../codex-compress-lib-r7-2026-11-11/report/REPORT.md)

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-r7](../codex-compress-lib-r7-2026-11-11/candidates/c1-shared-store-r7.json) | closed | The planned baseline diagnostic reproduced the rejected sample and captured two successful decoder returns in its first target observation. All eight functional guests and both disabled-build rows passed. This diagnosis is not a calibration sample or performance comparison. |

## codex-compress-lib-r8-2026-11-11

Status: closed; machine: hurricpc; opened: 2026-11-11; closed: 2026-11-12.

Baseline: `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Baseline origin: upstream or imported reference.

| Candidate | Status | Reason |
| --- | --- | --- |
| [c1-shared-store-r8](../codex-compress-lib-r8-2026-11-11/candidates/c1-shared-store-r8.json) | closed | Both isolated-observer diagnostics passed with no loss or misses. The eight correctness guests and both disabled builds passed. The bounded diagnostics do not supply calibration or comparison. |

Current baseline: 5e84ca928deeacb4eee656806a003f27d1eca82f (codex-compress-lib-r8-2026-11-11)
