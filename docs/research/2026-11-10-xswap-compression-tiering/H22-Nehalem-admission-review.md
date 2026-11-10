# H22: Nehalem auxiliary topology admission review

Status: **PASS for R5 correctness admission** on the exact snapshot below. No blocking admission finding remains. The coordinator may consume the existing `c1r5-b-common-001` reservation once through the native runner, then continue the frozen correctness matrix under its retained gates and budgets. Confidence: high for admission; actual Nehalem guest behavior remains a runtime question.

## Source reviewed

- H19 implementation: `92b221bcb32b9fad1182547736a97c20d1d560cd`, based on `dd23123a98b667b95c07c483afe9dd56345b98c7`.
- Exact implementation diff SHA-256: `404fca689de7f81798a7d06b6e43932f8e1968231967bf8fb43b4a07f6969602` (`git show --format=`).
- Authoritative scope: [H19 ticket](tickets/H19.json); implementation evidence: [H19 result](H19-result.md).
- CPU rationale: [H18 review](H18-clocksource-validity-review.md), current document SHA-256 `9fcd6d7dcf454337d5566448df701bfb37e6e0e8b04bcb7ba1bd072ac76a38fd`.

The six changed files stay inside the assigned scope. The new `numa2-nehalem-v3` identity is restricted by the native catalog to `c1-debug-v2` / `numa-lifecycle` / compressed XSwap correctness. The runner derives one `Nehalem-v1,vme=off,enforce=on` option and records the effective vector in both the launch command and `qemu_accel`. Normal and older topology commands retain their existing CPU selection.

The proof path binds CPU, accelerator, machine, SMP, memory objects and node assignment; it rejects duplicate/alternate option spellings and alternate device/global configuration channels. The new parser requires exactly one Intel CPU0 observation with family/model/stepping 6/26/3 inside one kernel-log block. Numeric identity, both real library placements, online nodes, hotplug/reset and warning gates remain required. The native matrix verifier calls the real catalog and reparses the retained serial evidence.

No implementation finding is currently open. Confidence: high for the inspected source and guest-free checks. A merged-tree divergence, missing native proof path, changed old outcome or actual guest identity mismatch would change this disposition.

## Independent verification

Fourteen focused tests passed on the Linux worker against the exact H19 commit, with no skipped test:

- `test_compression_evidence.NehalemNumaTopologyTests`, including inherited topology rejection cases.
- Both new Nehalem runner tests, including the mocked pre-launch capture of `started.json` and the exact command passed to `Popen`.
- `evolve.test_compression_coverage.NehalemCoverageTests`, including complete native eight-row/two-build matrix validation and record mutations.

The selected tests cover canonical and malformed CPU identity, wrong/missing flags, duplicate/aliased command options, wrong config/group/workload/timing, effective-record mismatch, both NUMA placements, warning/sanitizer rejection and retained clocksource invalidity. `git diff --check` also passes.

Independent replays of untouched R3 and R4 NUMA serial logs through H19 reproduce every saved parser gate, metric and subcase exactly:

| Retained run | Parser gates matched | Kernel-warning gate | Re-derived clocksource invalidity |
| --- | ---: | --- | --- |
| `c1r3-c-numa-001` | 16, excluding runner-owned exit gate | false | false |
| `c1r4-c-numa-001` | 16, excluding runner-owned exit gate | true | true |

Their result hashes remain `2767157a386326880422a1939f90a6ae807c6434ee22736f96a2c72f15a8fe83` and `42dc4f4631bbe24bce491d47e40977b50ac8462bda1db988c81303f3d01201ba`, respectively. R3's warning failure and R4's invalid result are preserved.

H19 separately reports 171 standard-suite tests (one existing missing-checkout skip) and 49 native coverage tests. Those broader counts are the implementation worker's evidence; H22 independently ran the selected 14 tests and retained-raw replays above.

## Final R5 admission snapshot

The final review is bound to [H22's ticket](tickets/H22.json) and campaign `codex-compress-lib-r5-2026-11-10`.

| Input | Exact identity |
| --- | --- |
| Integrated H19 implementation | `f442a9849b506dbf9c74aa38bfd373c611894e48` |
| Frozen R5 contract commit | `1144d831a9d2e27f9d1c681ed405a98bbfcf8c01` |
| Protocol SHA-256 | `e9e282998de6bc59c2563b398f5968c33f1a5ee219a06cca6e15267d9a9511e3` |
| Policy SHA-256 | `283245b9ee065feb8b89858127d1dc03ca564e91bc72ce356c74e516d9af5881` |
| Continuation SHA-256 | `0fde862de9da0c4fabccb8903cda1f5d36515407dc71854424013f4445161765` |
| Unchanged K1 kernel commit | `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad` |
| Unchanged K1 tree | `8b085adc109e3b5467c3de998f11b04517f052a5` |
| Retained candidate patch SHA-256 | `69e085f0b3703ae2929c0cc8e863b6f606fce1b15e8a4d3ab3fd378ef785f704` |
| Native canonical K2 review hash | `817c2760536d69a5779de34ee4fb9abd91ba3202e5bde2a2c2d4a3c45c5d44a7` |

All six integrated implementation files equal the audited H19 blobs and the current working files byte for byte. All three R5 frozen inputs equal their committed bytes. The native configuration catalog and standard workflow contract checks pass; the profile readout is ready with no missing capability. Capability readiness alone carries no execution authority. Existing owner authorization and this bounded admission govern the coordinator's launch.

The complete eight-guest matrix and two disabled-build rows are preserved. The R4-to-R5 protocol comparison changes only campaign/approval descriptions, the auxiliary NUMA topology, the remaining fast cap, total ceiling and shortened wall cap. Timing cases, `single` / `max` accelerator, guest resources, configuration pins, sample counts, repetition, noise limits, validity rules, warnings, sanitizers, required correctness gates and compression observer/workload are identical. Only `c-numa` selects `numa2-nehalem-v3`.

The candidate worktree is clean at the exact K1 commit/tree. The control kernel remains clean at its frozen pin. The current controller input digest matches the candidate record; static checker identity and all three retained static-log hashes match. Actual changed paths and the retained patch equal the source diff, and an independent `git diff --check` passes. `SCOPE_PASS` retains the original checkpatch exit 1 and its explicit administrative advisory, with filtered exit 0.

Native `reviews.list_reviews` through `mechanisms.validate` verifies the current K2 record and its cited evidence. Both candidate and baseline native veto queries return no blockers. The mechanism binds the current raw protocol hash and native canonical review hash. The coordinator's preparatory raw-file-versus-canonical review-hash correction is now resolved; no guest result, source identity, frozen input or counted cost was changed by that correction.

## Carried accounting and launch state

All four historical protocol and budget byte hashes match `continuation.json`; actual reservations and counted build ledger rows independently reproduce these costs. All four contracts remain closed, with no campaign STOP file present. Their recorded failures and raw evidence remain historical inputs.

| Contract | Counted guests | Counted builds |
| --- | ---: | ---: |
| Original C1 | 3 | 3 |
| R2 | 2 | 1 |
| R3 | 3 | 0 |
| R4 | 2 | 0 |
| Total before R5 | **10** | **4** |

The explicit transfer of two unused fast slots to probe yields **24 probe + 86 fast = 110 R5 guest slots**, with **six builds**. The full phase therefore remains capped at 120 guests and ten builds. The planned fresh matrix (8), probe calibration (12) and candidate probe (4) consume all 24 probe slots. Fast calibration (60) and candidate comparison (24) leave two fast validity slots. This is one unchanged kernel hypothesis across infrastructure continuations.

The actual R5 budget is `created=1794350186.6756349`, `probe_guests=1`, `guests=0`, `builds=0`. The single reserved probe slot is already included in that one, not an additional allowance. The actual deadline is `1794350186.6756349 + 52823 = 1794403009.6756349`, earlier than the inherited R4 ceiling `1794403573.5792072`. Native campaign cap validation passes; policy, protocol and campaign limits agree. R5 is open on `hurricpc`, the machine claim names R5, contributor records agree, and both current STOP paths are absent.

Exactly one initial reservation exists: `c1r5-b-common-001`, status `RESERVED`, SHA-256 `56e2b98a60ca34d2c88e2542c1be4756023e86ddfc2dba0ed67e0a79964b7ecf`. Its probe pool, frozen protocol, baseline-common build, workload, mode, backend, configuration and `single` topology match the native case. No R5 `runs/guests` directory, runtime ledger or complete correctness proof exists at admission.

The native progress reader currently returns `passed=false`, `failed=false`, `attempted=true`, `pending=false` with `counted correctness attempt has no completed raw result: c1r5-b-common-001`. This is the known prelaunch reservation state, not a completed failed guest. The coordinator must consume that same audited reservation once through the native launch path; the premature close action must not be executed or used to erase the reservation. No next action or state transition was executed by H22.

## Reusable build verification

For each artifact below, independent native `verify_build_binding` passes against the current environment and original counted provenance. Native `_configured_build` additionally verifies the manifest, exact source, input config, actual final config and actual `bzImage` hashes. No compiler or build was launched.

| Reusable build | Original counted contract / evaluation | Manifest SHA-256 |
| --- | --- | --- |
| `c1-base-common-20261110` | Original C1 / `3868cc40b0944c8f9b13b3aa529b5005` | `8f15f75eb6ae661d7531f99392902ae184e1f58d04989064d5098f8db8c0a5b2` |
| `c1-5e84ca928dee-legacy` | Original C1 / `4894c2e365c1463292ae02dd5914fffd` | `ddac55cc53053dae857517e7c3f0dffd0815f61f89c5e5c92051e990ecdcb2cc` |
| `c1-7d5a3cfab2ab-debug-v2` | R2 / `38f0482dac984d48a7d4e9cc7289f1b0` | `d27ba832157cc32c334d3ecf9decdf7d18e90c2438dfa857ad61656e0fd1b6ff` |

The two baseline artifacts bind `5e84ca928deeacb4eee656806a003f27d1eca82f` / tree `657cffbcbb1bff41ba1de6c232377cead2c2a837`; debug-v2 binds unchanged K1. Reuse retains the original counted build identities and creates no independent runtime sample. R5 still needs fresh configuration-specific runtime coverage and the remaining required builds.

## Limitations

This review has not launched a VM or compiler, edited implementation files, changed campaign state, committed, pushed, published or delegated further work. Only this review document was updated. Synthetic fixtures and retained-build checks establish admission behavior; the first fresh counted NUMA guest must establish actual CPU identity, clocksource validity, both node placements, hotplug and reset. Complete valid correctness, fresh calibration, performance or equivalence acceptance, and final report/family review remain later gates. No H22 process remains running. Reopen admission if any exact source, frozen input, review, artifact, reservation, ownership, STOP, budget or deadline binding changes.
