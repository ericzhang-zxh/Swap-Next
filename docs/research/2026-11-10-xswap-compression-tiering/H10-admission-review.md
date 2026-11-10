# H10 replacement admission review

**Disposition: PASS for bounded R2 admission at `10a46bde9ba4b8a130cb9acdba5e598c410304f2`. No admission blocker was found. Consume the existing reserved baseline ticket exactly once through the trusted runner, then retain all normal configuration, correctness, calibration, and review gates.**

Reviewer: `final_independent_review`, independent of implementation. Audited pre-launch snapshot: 2026-11-10 21:04:17 UTC. This is an admission decision, not runtime or candidate acceptance.

## Frozen contract and source

The R2 policy, protocol, and continuation record match freeze commit `f9e937cfee3cd11d6f4c4645a12f021b95bb3897`. Session input pins match the actual files.

- Protocol SHA-256: `dd5d28e9b355c0c94cc85750c4393ce8e5f125756013ca82581a2132b1035ed0`.
- Policy SHA-256: `9fb597dc2e193cddba92bc7a4962b0d1be3fe85bd3cb83ad76ccaead8c656d75`.
- Candidate `c1-shared-store-r2` worktree is clean at the exact existing commit `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, tree `8b085adc109e3b5467c3de998f11b04517f052a5`.
- Original anchor remains `5e84ca928deeacb4eee656806a003f27d1eca82f`.

I recursively compared original and replacement protocol/policy objects. Behavioral changes are limited to using the separately pinned `c1-debug-v2` input for the two debug cases and reducing resource limits. Other differences identify and explain the continuation. Workloads, timing parameters, pair counts, thresholds, correctness gates, topology, and guest timeout remain unchanged.

Native catalog validation accepts all eight correctness cases and two disabled build configurations. Native capability readout reports `ready=true`, no missing capabilities, and only probe/fast tiers. This readiness is separate from owner authorization, which remains the existing bounded task contract.

The new candidate has an exact-commit `SCOPE_PASS`. Its K2 record explicitly labels the source review as reused evidence, retains the original report hash, and binds the mechanism record to the new protocol. No new independent review sample or source change is claimed. [H9](H9-resolution.md) resolves the prior trusted-planner finding.

## Counted resources and deadline

At the audited snapshot, `c1r2-b-common-001` is **RESERVED**, with no `started.json`, raw result, or guest directory. Its identity is baseline `c1-base-common-20261110`, disk/XSwap correctness, case `b-common`, configuration `c1-common`, single topology. Native reservation identity validation and the protocol hash match. The reservation already consumes one probe unit.

| Resource | Original retained spend | R2 counted at snapshot | R2 remaining | Logical C1 ceiling |
|---|---:|---:|---:|---:|
| Probe/correctness guests | 3 | 1 reserved | 28 | 32 |
| Fast guests | 0 | 0 | 88 | 88 |
| All guest attempts | 3 | 1 reserved | 116 | 120 |
| Builds | 3 | 0 | 7 | 10 |

Native `research.line_spending()` reports complete accounting, with four guest units and three builds spent, plus commitments of 116 guests and seven builds. Native `line_budget()` returns ready with no reasons. All original phase capacity is either spent or committed; its zero unallocated remainder does not mean the open R2 allocation is exhausted.

The initialized R2 clock is `1794344444.500093`; its frozen wall limit is 60,228 seconds. Its enforced deadline is therefore:

**2026-11-11 13:44:32.500093 UTC** (`1794404672.500093`).

This is **544.883562 seconds earlier** than the original deadline `1794405217.3836553`. The native guest deadline check passes. The continuation record preserves the original three guests/three builds and the 360-guest/30-build three-phase family cap.

## Native admission and build reuse

The durable native `open` execution completed with exit code 0 and recorded the exact new protocol/policy hashes. The original campaign is closed, the machine claim names R2, and both relevant STOP locations are absent. Current source inspection confirms guest entry checks campaign ownership/state, machine, claim, frozen inputs, capability, resource consistency, and the single-use ticket; build and guest reservation guards use the reduced frozen ceilings.

I replayed native `correctness_proof._configured_build()` against the R2 protocol and the unchanged shared baseline build. It passes source tree, input/final configuration, image, builder/toolchain, original source protocol, original ledger, and counted-cost checks.

| Baseline artifact | SHA-256 |
|---|---|
| `result.json` | `8f15f75eb6ae661d7531f99392902ae184e1f58d04989064d5098f8db8c0a5b2` |
| `configured-build.json` | `9575b9f4422433f8a97d5f32dd314d73bba1d82c72fe486202ffd899f618b407` |
| Final configuration | `63da430133ca0c4199f5256ddccc04a90129d580e7adc9b9fa0af2f90949262d` |
| Kernel image | `819c8bb2cd5b1ef247d7ef07184ecc243019bd39afc83f4cc775d4a780290e48` |

The artifact directory is `benchmark/kernel/builds/c1-base-common-20261110/`. Its original cost remains in old C1. This reuse creates no guest observation.

## Narrowed-resource validator

I inspected commit `10a46bde9ba4b8a130cb9acdba5e598c410304f2`. The revision-8 validator now accepts only positive integer ceilings at or below the original 32 probe / 88 fast / 10 builds / 64,800 seconds. Guest timeout stays 900 seconds. No measurement or acceptance rule changed.

Native `validity.protocol_rules()` accepts the actual R2 protocol and retains p90 envelope, 25% ceiling, 3% floor, median comparison, and existing validity rules. I also ran 20 read-only in-memory negative checks: above-ceiling, zero, negative, boolean, and fractional values for each of the four resource fields. All 20 were rejected.

## Evidence and limits

Primary references: `campaigns/codex-compress-lib-r2-2026-11-10/{protocol.json,policy.json,continuation.json,campaign.json,research.json}`, `ledger/budget.json`, `ledger/guest-reservations/c1r2-b-common-001.json`, `ledger/session.json`, the native open log `runs/session/action-4e52ba06763a0a3813d8d776-f013f58e.log`, and the exact-source review `reviews/k2-c1-shared-store-r2-7d5a3cf.json`. Original costs remain in `campaigns/codex-compress-lib-2026-11-10/ledger/budget.json`.

This audit verifies admission, identity, accounting, and baseline build reuse. The corrected configuration still needs a real final-config-verified build and complete runtime matrix, followed by fresh calibration. I did not launch, reserve, consume, build, alter state, execute the test suite, delegate, push, or publish. The only write is this review, and no reviewer process remains running.
