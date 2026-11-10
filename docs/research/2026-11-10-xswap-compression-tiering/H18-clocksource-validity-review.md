# H18: R4 clocksource validity and continuation review

Status: diagnosis and resource-accounting review complete. A versioned auxiliary CPU configuration is source-supported; its implementation and fresh counted runtime admission remain coordinator-owned.

Reviewed control snapshot: `dd23123a98b667b95c07c483afe9dd56345b98c7`.
Kernel: `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, tree `8b085adc109e3b5467c3de998f11b04517f052a5`.
Scope: read-only diagnosis, native recovery inspection and remaining-resource arithmetic. Only this review document was written. No guest, build, campaign mutation or further delegation was performed.

## Disposition

**R4 remains invalid and closed.** Its NUMA guest passed its recorded functional and warning gates, but the unchanged validity rule rejects its boot-time TSC fallback. The cause is the guest CPU model combined with the new two-package topology. The retained message comes from a conservative kernel classification, before any compression-library or hotplug work.

For a new frozen auxiliary configuration, recommend the explicit QEMU CPU string `Nehalem-v1,vme=off,enforce=on`, keeping the R4 two-socket mapping. It is a named Intel emulation model with a supported feature set, not a request to trust an unreliable clock. The kernel's synchronization test and clocksource watchdog remain active. All normal single-topology correctness and timing cases must retain their existing `max` CPU.

A separately frozen continuation with **24 probe + 86 fast = 110 remaining guests**, at most six builds, and an absolute deadline no later than **1794403573.5792072** preserves the owner's aggregate C1 limits. It requires an explicit two-slot transfer from the unused fast allowance; the old pool split is not silently preserved. The full planned run costs 108 guests and leaves two fast validity attempts, with no probe spare.

## Retained observation and diagnosis

The R4 campaign is natively closed. Its budget records two probe attempts, zero fast attempts and zero builds. The full phase has spent ten guests and four builds.

| R4 NUMA evidence | Verified result |
| --- | --- |
| Run | `c1r4-c-numa-001` |
| Exit / integration | 0 / `integration_pass=true` |
| Scientific and warning gates | All 17 recorded gates are true |
| Required subcases | Library placement, CPU hotplug and memcg balance pass with valid evidence/reset |
| Measurement validity | `run_valid=false`; sole reason `clocksource_fallback` |
| Boot chronology in retained kernel-log block | TSC classified unstable at serial line 501; HPET selected at 604; CPU 1 offlined at 710 |
| CPU/package layout | `-cpu max -smp 4,sockets=2,cores=2,threads=1`; CPUs 0-1 on node 0, CPUs 2-3 on node 1 |
| Guest CPU identity | Serial line 528 identifies AMD QEMU TCG CPU, family 6/model 6/stepping 3 |

The exact kernel path is:

1. `arch/x86/kernel/tsc.c:1551-1554` calls `unsynchronized_tsc()` and emits this precise reason when it returns true.
2. `tsc.c:1254-1283` first handles an absent/already unstable TSC and the special clustered-chassis check. It accepts `CONSTANT_TSC` or an already reliable clock. Otherwise, a non-Intel CPU with `topology_max_packages() > 1` is classified unsynchronized.
3. `arch/x86/kernel/cpu/amd.c:628-635` derives `CONSTANT_TSC` and `NONSTOP_TSC` from CPUID 0x80000007 EDX bit 8. QEMU 8.2.2's TCG `max` defaults to AMD and does not support that `invtsc` bit.
4. The special APIC branch is an IBM Summit2 DMI classification (`arch/x86/kernel/apic/apic.c:2559-2603`), not a generic two-node NUMA test. This guest's recorded command supplies no such machine identity, and its log has no multi-chassis detection.

The decisive condition is **multiple CPU packages**, not merely two memory nodes. R4 corrected the LLC/node inconsistency by making the two packages explicit; that also made the AMD heuristic applicable. No `arch/x86` file differs between the original anchor and this candidate. The observed message is distinct from the measured-warp path in `arch/x86/kernel/tsc_sync.c`, which emits a measured cycle warp and a different instability reason. Confidence: high. A conflicting CPU identity, an earlier actual clock failure, or evidence of altered x86 source would change this diagnosis.

Raw identities, all rechecked:

| Artifact | SHA-256 |
| --- | --- |
| R4 NUMA result | `42dc4f4631bbe24bce491d47e40977b50ac8462bda1db988c81303f3d01201ba` |
| R4 NUMA serial | `18ac9f90880616d3cb229f77f1a5b385e171f7301d230c39bbfba7c82aa86a45` |
| R4 frozen protocol | `d7f4c5ff044dc227a26f75a78e50edd5927b4d6d97dd20727762aad9a7cd3ab6` |
| R4 closeout archive index | `a7e42aa5364874f86fc737dea3b3b3a0ac09d25461c684efe6c17296b22d818d` |

All 28 archive entries, including the guest image and initramfs, match their retained hashes. See [runtime incident 005](runtime-incident-005.md) for the owned incident record.

## Supported auxiliary correction

The installed binary reports QEMU 8.2.2, Ubuntu package `1:8.2.2+ds-0ubuntu1.18`; its read-only `-cpu help` lists `Nehalem-v1`. The source audit used the pinned upstream v8.2.2 files. The named model's requested non-VMX CPUID features are within TCG's support masks after explicitly disabling VME. Its VMX metadata is removed by ordinary feature dependencies because VMX itself is absent. `enforce=on` makes any remaining unsupported selection an error instead of silently filtering it. No CPU instance or VM was started for this inspection. [QEMU model, support masks and filtering source](https://github.com/qemu/qemu/blob/v8.2.2/target/i386/cpu.c)

The TCG clock path is shared across emulated packages: RDTSC reads `cpu_get_tsc(env) + env->tsc_offset`; system x86 uses `cpus_get_elapsed_ticks()`. The recorded multithreaded TCG mode has no icount override, so this reaches `cpu_get_ticks()`, which serializes access to a shared clock and prevents a decreasing base value. On this x86 host it uses the host cycle counter. Per-CPU offsets and real clock problems can still matter. [RDTSC helper](https://github.com/qemu/qemu/blob/v8.2.2/target/i386/tcg/misc_helper.c#L64), [x86 clock adapter](https://github.com/qemu/qemu/blob/v8.2.2/hw/i386/x86.c#L542), [elapsed ticks](https://github.com/qemu/qemu/blob/v8.2.2/system/cpus.c#L236), [TCG operations](https://github.com/qemu/qemu/blob/v8.2.2/accel/tcg/tcg-accel-ops.c#L197), [shared timer](https://github.com/qemu/qemu/blob/v8.2.2/system/cpu-timers.c#L43), [host counter](https://github.com/qemu/qemu/blob/v8.2.2/include/qemu/timer.h#L884)

In the pinned kernel, Intel family 6/model 26 is covered by the older-model constant-TSC rule in `arch/x86/kernel/cpu/intel.c:289-302`. This avoids the early non-Intel multi-package rejection. The proposed model advertises neither invariant TSC nor TSC_ADJUST. Therefore it does not satisfy the three-feature automatic watchdog-disable condition in `tsc.c:1243-1247`; `tsc_sync.c:433-453` still enters the actual cross-CPU test, because the TSC_ADJUST shortcut returns false when that feature is absent (`tsc_sync.c:188-189`). Confidence is high in this source prediction and medium in a clean future guest, which has not run.

The trusted implementation should:

- Add a new, narrowly admitted topology ID for `c1-debug-v2` / `numa-lifecycle` / compression correctness only. Preserve the existing `numa2` and `numa2-sockets-v2` identities and behavior.
- Keep four vCPUs, 4096 MiB, the exact two-socket/two-core mapping and both existing node memory/CPU assignments. Keep every subcase, warning, sanitizer, topology and validity gate.
- Derive exactly one CPU option from that trusted identity, record the effective accelerator/CPU command, and bind it in native proof validation. Preserve duplicate/alias rejection for CPU, SMP, machine, memory and NUMA options.
- Keep `accelerator.qemu` and all `single` timing cases unchanged. A global CPU replacement would change the timing contract and is outside this proposed correction.
- Validate the actual boot CPU identity, node placement, hotplug outcome and unchanged clocksource gates on the first fresh counted NUMA case. Retain any failure with its reservation.

Adding `invtsc` is unsupported by these TCG masks. Forcing unsupported flags, using `tsc=reliable`, disabling watchdogs, hiding fallback markers, or removing the TSC/HPET solely to avoid a marker would not meet this review. Merely rewriting the vendor string is less reproducible than the explicit named model and is not the recommended configuration.

Upstream source hashes read during this review:

| QEMU v8.2.2 file | SHA-256 |
| --- | --- |
| `target/i386/cpu.c` | `5f5b56ec10f866303ee017b6e52716499f915522a10b685ada92527b50e104ee` |
| `target/i386/tcg/misc_helper.c` | `b408da91d1008321b4189f0573730e3d29cedb2a3f2190e84da9a5ab8a7decbb` |
| `hw/i386/x86.c` | `47b4601fc6c676c83dde2a90185b767e0038da808f393eea77524ad882e6d751` |
| `system/cpus.c` | `24022894229f954ac745b0739a6a2b62a76997025fa6740b11d9b984a885f439` |
| `accel/tcg/tcg-accel-ops.c` | `49d3dff387ec2b34ac04d155663b6b3f8b4f9ef89531a588b7d3a6c52ce828e9` |
| `system/cpu-timers.c` | `f24aae24b750292d72c318f1b6ab73a1500611a0e5b3d1ff72407953e9ee22fd` |
| `include/qemu/timer.h` | `13307d94cbb5bf150b19fe8f378b00bf76c12fa82ba462b097403cd6853b3b90` |

## Native retry and supersession audit

The exact-case native validator rejects the untouched R4 result with `correctness evidence has invalid measurement conditions`. Read-only `matrix_progress()` returns `passed=false`, `failed=false`, `pending=false`, verifies only `b-common`, and reports the same invalidity. Here `failed=false` means no `CorrectnessFailure` was established; the matrix remains blocked.

The H6 facility cannot replace this candidate observation:

- `evolve/control/correctness_proof.py:336-352` restricts recovery to flat baseline cases with the exact baseline source and common/legacy configuration.
- Its archived classification requires only the old missing-topology identity defect, valid timing conditions and no additional failed gates (`:235-242`).
- Calling that read-only classifier on the R4 NUMA observation rejects it as `infrastructure supersession is restricted to flat baseline cases`.
- `matrix_progress()` rejects multiple retained attempts for one case (`:649-655`), and `_check_matrix_reservations()` rejects omitted counted attempts (`:597-606`).

The protocol's `reruns_per_arm=2` is consumed by the probe/performance loops in `evolve/standard_workflow.py:787` and `:1008`. It is not a general candidate-correctness supersession facility. A second same-campaign NUMA result cannot erase R4. The native route available here is a separately frozen, explicitly linked continuation after the infrastructure configuration is corrected, with old results and costs retained.

## Remaining resources

[Owner authorization](authorization.json) fixes three logical phases, each at most 120 guests, ten builds and 18 hours. The original C1 pool split was 32 probe/88 fast. The retained attempts sum as follows:

| Frozen C1 version | Probe spent | Fast spent | Builds spent |
| --- | ---: | ---: | ---: |
| Original | 3 | 0 | 3 |
| R2 | 2 | 0 | 1 |
| R3 | 3 | 0 | 0 |
| R4 | 2 | 0 | 0 |
| Total | **10** | **0** | **4** |

The untransferred remainder is 22 probe/88 fast. A fresh full matrix needs eight probe guests, probe A/A needs twelve, and the candidate probe needs four: **24 probe**. Fast A/A requires 60 guests and the candidate comparison 24: **84 fast**.

The proposed 24/86 split therefore transfers two unused fast slots to probe while retaining the 110 total remainder. Cumulative use at the new cap would be 34 probe plus 86 fast, exactly 120 total. At the planned 108 fresh guests, cumulative use would be 118. This is a change to the pool allocation, not an increase in the owner's aggregate allowance or a new scientific candidate.

I consider the rebalance legitimate within the approved preparation/continuation scope if the coordinator explicitly freezes it as a new contract and records:

1. All four old budget/protocol hashes, ten prior guests, four prior builds, failed outcomes and the infrastructure reason.
2. New limits of 24 probe, 86 fast, no more than six builds, the unchanged sample counts/measurement rules, and no more than the original one kernel hypothesis.
3. An actual new `budget.created + wall_seconds <= 1794403573.5792072` before any launch. This is 2026-11-11 13:26:13.579207 UTC, the stricter R4 deadline. Preserve every older deadline and STOP/closed state.
4. Exact native revalidation of reused build artifacts; historical guest results do not become new matrix observations.

An in-memory copy of R4 with only the proposed 24/86 budget values passes the current native `protocol_rules()` resource checks. This confirms mechanical ceiling compatibility, not acceptance of a yet-unimplemented CPU topology or a new campaign.

Count feasibility is high confidence: 108 planned guests fit under 110, and five expected new configuration builds fit under six if the three existing baseline/debug artifacts remain reusable. Wall-time completion remains unmeasured; native elapsed-time limits still stop execution. The two spare fast attempts cannot fund a probe retry in an already frozen 24/86 contract. A further invalid correctness case cannot be silently retried or relabeled to preserve the plan.

## Limitations

The proposed CPU model was source-audited and found in the installed binary's model list; it has not booted under this harness. Upstream v8.2.2 source was inspected alongside the Ubuntu binary version, not rebuilt from the distribution source package. No performance, whole-matrix correctness, independent-XSwap or pressure-demotion result was added. New trusted code, frozen continuation admission and final campaign/family report review are separate coordinator-assigned steps.
