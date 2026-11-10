# H16 topology correction and R4 admission review

**Disposition: PASS for bounded R4 admission at `04bc239db9bb1ddc20832f712461cec0e10de12b`. H16-001 is explicitly resolved at that revision. The retained R3 warning is classified as an infrastructure topology failure for the inspected inputs; no applicable kernel-source veto was found or cleared.**

Reviewer: `final_independent_review`, independent of implementation. Final pre-launch snapshot: **2026-11-10 21:52:13 UTC**. Consume the existing baseline ticket exactly once through the trusted runner, then require fresh complete correctness before calibration. This admission grants no candidate performance acceptance.

## R3 warning attribution and retained outcome

**Confidence: high in the infrastructure attribution.** The actual recorded command used `-cpu max -smp 4 -m 4096`, with CPUs 0–1 assigned to a 2-GiB node 0 and CPUs 2–3 to a 2-GiB node 1. The kernel reports that CPU 2 and CPU 0 are LLC siblings despite occupying different nodes. This is a disagreement between the advertised CPU/cache topology and the supplied NUMA map.

The exact warning is `arch/x86/kernel/smpboot.c:329 topology_sane`, reached through `set_cpu_sibling_map` and `start_secondary`. `match_llc()` at lines 442–469 checks matching LLC IDs and calls the node-consistency warning. That source and `init/main.c` are byte-identical between baseline `5e84ca92` and candidate `7d5a3cf`. In the exact kernel, `init/main.c:1667` calls `smp_init()` before `do_basic_setup()` at line 1675. The new library registers through `subsys_initcall(page_compress_init)` at `mm/page_compress.c:392`, after this boot topology setup. The retained stack identifies CPU bring-up, rather than a library operation, as the warning context.

I verified all **28/28** archived runtime files and replayed all three R3 logs using their archived parser. Baseline common reproduces all 19 successful gates; candidate debug reproduces all 20 successful gates. Candidate NUMA reproduces exactly two failed gates, `no_kernel_warnings` and `no_new_kernel_warnings`; its three compression subcases are PASS, reset, and evidence-valid. The updated H15 parser also reproduces those same saved metrics, gates, and subcases. The warning is still rejected.

| R3 evidence | SHA-256 |
| --- | --- |
| NUMA raw result | `2767157a386326880422a1939f90a6ae807c6434ee22736f96a2c72f15a8fe83` |
| NUMA serial log | `a2720fdfe500355593421ab2770bb6710aca481ccaabc58b04a94e881ba44f57` |
| Runtime archive index | `a6a788c5146b06a64e339a4126e49f10219bae39ff7c66a8ea800ff9406d9867` |

R3 remains a failed, counted, infrastructure-incomplete contract. A fresh explicitly mapped topology that reproduces this warning would reopen the attribution and stop dependent execution. Native applicable-review checks are empty for the exact source; this review does not use a plain pass to erase a source finding.

## H15 scope and exact proof

H15 commit `4510de0ef81ab307d62740650bfe6e457a6089a3` was integrated as `7e540705b9f8d3a0f7e46d8168a03b6c0d3cf72f`. It changes the host catalog, runner, parser, and their tests. Guest image, guest-init, bench.sh, compression workload, and swap-in workload bytes remain equal to the R3 archive.

Only `numa2-sockets-v2` selects:

```text
-smp 4,sockets=2,cores=2,threads=1 -m 4096
-object memory-backend-ram,id=c1-node0,size=2048M
-object memory-backend-ram,id=c1-node1,size=2048M
-numa node,nodeid=0,memdev=c1-node0,cpus=0-1
-numa node,nodeid=1,memdev=c1-node1,cpus=2-3
```

The generated command has one SMP definition. It retains four vCPUs, total 4 GiB, both NUMA nodes, frozen `-machine pc`, frozen `-cpu max`, and the existing TCG accelerator. The new identity resolves only for the `numa-lifecycle` correctness group with `c1-debug-v2`; native protocol validation rejects its use in timing or other correctness groups. The proof binds the complete SMP string, exact memory/node options, and CPU/machine options. The parser requires actual online nodes 0–1 and successful KUnit placement observations on both nodes. Diagnostic gates are unchanged.

Legacy `single` still generates `-smp 4 -m 4096`. Legacy `numa2` still adds its original node arguments to that same implicit SMP definition. Old protocols and results retain their original identities and bytes.

## H16-001 resolution

The initial H15 proof accepted a valid new-topology record with an appended `-M q35`, despite claiming exact machine binding. Read-only `qemu-system-x86_64 -M help` confirms this machine alias exists. This was a trusted-proof validation finding, separate from the candidate kernel source.

Fix `a40180680f403d4ef7c86878fcea93aa7df562be`, integrated as **`04bc239db9bb1ddc20832f712461cec0e10de12b`**, rejects `-M`/`--M` and attached forms only for the new topology. I independently replayed six variants against the pre-fix and fixed code: all six were previously accepted and are now rejected. Canonical new and legacy records still pass.

All **18** focused topology, revision-8 protocol, and compression-runner tests pass at the final revision:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=benchmark/swap-standard:. python3 -m unittest test_compression_evidence.SocketNumaTopologyTests test_compression_evidence.Revision8ProtocolTests test_runner.CompressionRunnerTests
```

The inspected trusted files equal the final commit. Their SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| configurations.py | `bb290ff3a2e8d903a8f66cbfcf4990d9db7993524c02c7fbc93397478662017e` |
| evidence.py | `25b3ad0d0c293fb2cb32d48b008f2dfc85fcf4277f09fb27011635edb895989f` |
| run.py | `3977dc7dd33e9475bc4cd4f5869740017aef497b5ff6e791958b69fd3ce75ca0` |

## Frozen R4 contract and accounting

R4 protocol, policy, and continuation record match freeze commit `1068700`. Recursive comparison with R3 finds the single behavioral change `c-numa.topology_id = numa2-sockets-v2`, reduced resource fields, and continuation metadata. Native catalog and protocol-rule validation accept all eight runtime cases, both disabled builds, and unchanged timing/acceptance rules.

| Frozen file | SHA-256 |
| --- | --- |
| protocol.json | `d7f4c5ff044dc227a26f75a78e50edd5927b4d6d97dd20727762aad9a7cd3ab6` |
| policy.json | `3276c52c9cefa0d3927b067d07d5148fb3a1783873233238189cf4ab5fc2d22b` |
| continuation.json | `d82003d82543712abaaff64ae089220723b9762ac20e88d5008190b9d9571405` |

All three prior campaigns are closed, their budget/protocol hashes match the continuation, and native closeout records completed both close commands with exit code 0. Their retained cost is eight probe guests and four builds.

| Resource | Prior retained spend | R4 ceiling | R4 counted at snapshot | Logical C1 ceiling |
| --- | ---: | ---: | ---: | ---: |
| Probe/correctness guests | 8 | 24 | 1 reserved | 32 |
| Fast guests | 0 | 88 | 0 | 88 |
| All guests | 8 | 112 | 1 reserved | 120 |
| Builds | 4 | 6 | 0 | 10 |

Native spending is complete: nine guest units/four builds spent, 111 guests/six builds committed. Native line admission is ready with no reasons. The family cap remains 360 guests/30 builds across three logical phases. The planned eight correctness, twelve probe-calibration, and four candidate-probe attempts consume all **24 probe slots**, leaving no probe retry margin. The fast plan uses 84 of 88 slots.

Actual creation time `1794347289.5792072` plus 56,284 seconds gives deadline **2026-11-11 13:26:13.579207 UTC** (`1794403573.5792072`), 519.741741 seconds earlier than R3. Native deadline validation passes.

**Frozen descriptive metadata erratum:** `planned_guest_counts.total_ceiling` still says 115 and `wall_estimate.note` still says 58,398 seconds. The enforced fields are **112 total guests and 56,284 seconds**, as verified above. Runtime code does not consume either stale descriptive field. The frozen file remains unchanged.

## Candidate and launch snapshot

The controller-created R4 worktree is clean at unchanged commit `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, tree `8b085adc109e3b5467c3de998f11b04517f052a5`, with the original anchor. Native static status is `SCOPE_PASS`; all three checker log hashes match.

Native review validation verifies the explicitly reused K2 record `92c7344114c3c4064dac779cf2f3f77b3bd8398ff0c045bede84136c67a4e28d`, its original source-review evidence, and the new mechanism binding to the R4 protocol. Applicable source vetoes are empty.

Native configured-build reuse passes for baseline common, baseline legacy, and candidate debug-v2, including source/configuration/image, builder/toolchain, original protocol/ledger, and counted-cost provenance. Original costs remain with their source campaigns. R4 requires fresh runtime coverage.

Native open completed with exit code 0. The claim names R4 and both STOP files are absent. Exactly one ticket exists: `c1r4-b-common-001`, **RESERVED**, with no guest directory. Its protocol and native identity match the frozen baseline common case. R4 budget is one reserved probe, zero fast guests, and zero builds.

A subsequent native next-action read offers `close_candidate` because the counted reservation has no completed raw result. I independently confirmed that the ticket is still RESERVED, has no `started_unix`, and has no guest directory; the budget is unchanged. This is the pre-launch reservation boundary, not a completed failed run. Admission is limited to consuming that existing unstarted ticket once through the trusted runner. An already STARTED, ambiguous, or failed attempt remains subject to stop/reconciliation; this review permits no replacement ticket or retry to bypass it.

## Limitations

Warning attribution uses retained runtime evidence and exact source initialization order; no additional baseline NUMA counterfactual or corrected-topology guest was executed by this reviewer. Fresh warning-free, complete correctness remains required. This review does not repeat the full K1 audit, accept performance, or finish the family review. No kernel build, guest, reservation, campaign mutation, delegation, commit, push, or publication was performed. All checks ran over SSH; the only write was this review. No reviewer process remains running.
