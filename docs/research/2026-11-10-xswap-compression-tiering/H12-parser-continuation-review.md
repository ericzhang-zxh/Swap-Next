# H12 parser and R3 continuation admission review

**Disposition: PASS for H11's bounded parser repair and R3 admission at `0e1a90f08d51ba815aa92666c6411d0a5f17e77d`. No blocking finding was identified. The coordinator may consume the existing baseline reservation exactly once through the trusted runner and continue the fresh correctness matrix within the frozen resources.**

Reviewer: `final_independent_review`, independent of implementation. Final pre-launch snapshot: **2026-11-10 21:26:29 UTC**. This is parser and admission review; candidate runtime and performance acceptance remain separate gates.

## Parser scope and strictness

**Confidence: high.** Integrated H11 commit `9e946f3a654854362aa74cbda805dc06d3269059` changes only `benchmark/swap-standard/evidence.py` and its compression-evidence tests. The current parser is byte-identical to that commit, SHA-256 `748ad9a8ab7463d0845925d51cfda21775e5d0fc5f23159477bff4abf4966d83`. The current guest image manifest equals the retained R2 manifest; no guest source or image was changed by H11.

At `evidence.py:431`, the exact expected invalid-codec printk is accepted once inside the `invalid_codec` observation state and retained as a typed diagnostic. Other codec names, extra text, duplicates, another subcase, and placement before begin or after reset remain failures. The existing semantic errno, unchanged codec, storage, charging, data, decode, and reset checks are still required. Global kernel diagnostic scanning is unchanged.

At `evidence.py:221`, the optional KUnit summary pair must match the exact three-pass/zero-fail/zero-skip totals in order, after the three required successful tests and before suite success. The original no-summary fixture remains supported. Nonzero counts, contradiction, incomplete or repeated summaries, real SKIP/TODO directives, failed tests, and NUMA observation failures remain rejected.

Independent checks:

- All **7** `CompressionFramingTests` passed using `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=benchmark/swap-standard:. python3 -m unittest test_compression_evidence.CompressionFramingTests`.
- **22** in-memory mutations of the actual retained R2 serial were rejected: six diagnostic identity/placement variants, removal of either semantic invalid-codec observation, seven summary count/pair variants, SKIP, TODO, failed unit test, NUMA mismatch, and WARNING/KASAN/KCSAN diagnostics.

A fresh correctly bound run with a semantic failure or an unrecognized diagnostic must still fail. Any contrary replay would reopen this disposition.

## Retained R2 observation

I independently parsed the unchanged `c1r2-c-debug-001/serial.log` with H11 in memory. All **19 parser gates** were true; all six subcases were PASS, reset, and evidence-valid. The expected printk is retained under `expected_diagnostics`; kernel diagnostics are empty.

| Retained artifact | SHA-256 |
| --- | --- |
| `serial.log` | `87c7ebe30f51fd8ce45a14b188a7140bef043fc806cac95011f9b8793b788280` |
| `result.json` | `2c8ac864d761e796c0d439f4f069502fed3d8f26e8031bd0da4d4651966b9d6e` |

Both hashes were identical before and after replay. The saved result retains `parse_complete=false`, `integration_pass=false`, and its original parse error. It remains a failed counted attempt. R2's native closeout completed both close commands with exit code 0 and `performance_accepted=false`.

## Frozen continuation and resource accounting

**Confidence: high.** R3's protocol, policy, and continuation record match freeze commit `0e1a90f`. Recursive comparison with R2 finds only continuation identity/explanation and reduced resource fields. Configuration pins, matrix, workloads, observation requirements, timings, pair counts, thresholds, validity rules, and guest timeout are unchanged. Native catalog validation accepts all eight runtime cases and both disabled build cases.

| Frozen file | SHA-256 |
| --- | --- |
| `protocol.json` | `d454195000ec05241c2c3a325060abed3960360723163b8ed2ed0038f9b77edf` |
| `policy.json` | `156a05b7f9d29ba0aa5cf88938d033e1bb69a5cb72577cff04e2656f4cb53557` |
| `continuation.json` | `7634fdaceeb58b490cc4578cf80594f072a7754da9c4375df18e6daf863b59c0` |

Both earlier campaigns are closed. Their actual budget and protocol hashes match the continuation record. Original C1 retains three probe guests/three builds; R2 retains two probe guests/one build.

| Resource | Prior retained spend | R3 ceiling | R3 counted at snapshot | Logical C1 ceiling |
| --- | ---: | ---: | ---: | ---: |
| Probe/correctness guests | 5 | 27 | 1 reserved | 32 |
| Fast guests | 0 | 88 | 0 | 88 |
| All guests | 5 | 115 | 1 reserved | 120 |
| Builds | 4 | 6 | 0 | 10 |

Native `line_spending()` reports complete accounting: six guest units/four builds spent, with 114 guests/six builds committed. `line_budget()` is ready with no reasons. The zero unallocated remainder represents the existing R3 allocation, not exhaustion of its remaining pool. The 360-guest/30-build family cap remains recorded unchanged.

Actual R3 creation time `1794345695.3209484` plus 58,398 seconds gives deadline **2026-11-11 13:34:53.320948 UTC** (`1794404093.3209484`): 579.179145 seconds earlier than R2 and 1,124.062707 seconds earlier than original C1. Native deadline validation passes.

## Source, build reuse, and native admission

The R3 candidate worktree is clean at unchanged commit `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, tree `8b085adc109e3b5467c3de998f11b04517f052a5`. Anchor `5e84ca928deeacb4eee656806a003f27d1eca82f` and the `linux/` pin are unchanged. The exact-source static result is `SCOPE_PASS`; all three checker log hashes match.

Native review loading verifies the K2 evidence and R3 alias record `68e2b1f84d8946fdf3ea59a688f9510eaf47f059a96bdaa04c2156821dc23899`. It explicitly labels reuse of the same source review; native applicable-review blockers are empty. `mechanism.json` binds that record, exact source, and the R3 protocol.

I replayed native `correctness_proof._configured_build()` for all three reusable artifacts. Each passes source tree, input/final configuration, kernel image, builder/toolchain identity, original protocol, original ledger, and counted-cost validation:

| Build | Manifest SHA-256 |
| --- | --- |
| `c1-base-common-20261110` | `8f15f75eb6ae661d7531f99392902ae184e1f58d04989064d5098f8db8c0a5b2` |
| `c1-5e84ca928dee-legacy` | `ddac55cc53053dae857517e7c3f0dffd0815f61f89c5e5c92051e990ecdcb2cc` |
| `c1-7d5a3cfab2ab-debug-v2` | `d27ba832157cc32c334d3ecf9decdf7d18e90c2438dfa857ad61656e0fd1b6ff` |

Original build costs remain in their source campaigns. Reuse supplies build artifacts only; all R3 runtime correctness and calibration observations must be fresh.

Native R3 open completed with exit code 0 and the frozen hashes. The machine claim names R3 and both STOP files are absent. `c1r3-b-common-001` remains **RESERVED**, with no guest directory or started result. Its protocol hash and native reservation identity match `b-common`/`c1-common`/single topology. Session evidence is in `runs/session/action-2eef1ae25890b9cf1fb6cdbf-7e10d004.log` under R3.

## Limitations

This review does not repeat the full K1 source audit, grant runtime or performance acceptance, or turn the diagnostic replay into a new sample. Only seven focused tests and the stated read-only native/adversarial checks were executed by this reviewer. No build, guest, reservation, outcome mutation, delegation, commit, push, or publication was performed. All work ran over SSH; the only write was this review. No reviewer process remains running.
