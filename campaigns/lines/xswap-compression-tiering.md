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

Current baseline: 5e84ca928deeacb4eee656806a003f27d1eca82f (codex-compress-lib-r4-2026-11-10)
