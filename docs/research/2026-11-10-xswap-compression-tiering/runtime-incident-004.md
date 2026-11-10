# Runtime incident 004: conflicting virtual CPU and NUMA topology

The R3 baseline common and candidate debug guests passed their complete per-run gates. The candidate NUMA guest completed with valid compression subcases but failed both kernel-warning gates. Execution stopped at that first failure; no later matrix row or timing measurement ran.

## Retained observations

- Exact candidate remains 7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad, source tree 8b085adc109e3b5467c3de998f11b04517f052a5.
- c1r3-b-common-001 passed 19 gates. c1r3-c-debug-001 passed 20 gates, including six subcases and three real library KUnit tests with KASAN enabled.
- c1r3-c-numa-001 exited zero and run_valid is true, but integration_pass is false. no_kernel_warnings and no_new_kernel_warnings are false.
- The actual boot warning is arch/x86/kernel/smpboot.c:329 topology_sane: CPU#2 LLC-sibling CPU#0 not on same node [1!=0].
- The NUMA library_unit, guest_hotplug and memcg_balance subcases each passed with their reset records. Requested nodes 0 and 1 were observed on their matching nodes.
- The warning occurs during CPU boot before page_compress initialization. The trusted command uses implicit single-package -smp 4 with CPUs 0-1 in node 0 and CPUs 2-3 in node 1.
- NUMA raw serial SHA-256: a2720fdfe500355593421ab2770bb6710aca481ccaabc58b04a94e881ba44f57.
- NUMA raw result SHA-256: 2767157a386326880422a1939f90a6ae807c6434ee22736f96a2c72f15a8fe83.
- All 28 pre-correction runtime files are preserved in runs/closeout-runtime, archive SHA-256 a6a788c5146b06a64e339a4126e49f10219bae39ff7c66a8ea800ff9406d9867.

## Correction and accounting

R3 closes infrastructure-incomplete with three probe guests, zero fast guests and zero new builds. Original C1 plus R2 plus R3 total eight guest attempts and four builds. A continuation has at most 24 probe guests, 88 fast guests and six new builds and must end by the earlier R3 deadline 1794404093.3209484. Earlier raw results, frozen protocols, budgets and deadlines remain unchanged.

H15 prepares a separately named numa2-sockets-v2 topology with two sockets, two cores per socket and one thread per core, keeping the same four vCPUs and two 2-GiB NUMA nodes. It is restricted to auxiliary NUMA correctness and must pass independent source/proof review before a new frozen protocol collects fresh evidence. Kernel-warning gates remain mandatory. No kernel source change, performance measurement or code promotion is part of this correction.

## Confidence and limitations

Confidence is high that the boot warning originates from the virtual topology mismatch, based on the exact QEMU command, warning location and initialization order. A fresh correctly mapped topology that produces the same warning would contradict that diagnosis. The candidate's full configuration-bound correctness matrix and calibrated timing remain incomplete. C2 and C3 execution remains dependent on full C1 correctness.
