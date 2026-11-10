# Runtime incident 005: NUMA clocksource validity

R4 removed the earlier topology warning on unchanged candidate 7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad (tree 8b085adc109e3b5467c3de998f11b04517f052a5). Its fresh two-node guest passed all 17 functional and kernel-warning gates. The saved integration_pass is true, but run_valid is false with clocksource_fallback. Native correctness still requires a valid run; the complete matrix remains incomplete.

## Exact observations

- c1r4-b-common-001 passes all 19 gates with run_valid=true, wall time 22.540467 seconds.
- c1r4-c-numa-001 exits zero, wall time 58.538318 seconds, pre-QEMU time 0.027361 seconds.
- Library KUnit placement matches requested nodes 0 and 1. library_unit, guest_hotplug and memcg_balance each pass with valid evidence/reset.
- Serial line 501 reports: tsc: Marking TSC unstable due to TSCs unsynchronized. The boot selects HPET at line 604. The CPU hotplug subcase starts later (CPU 1 offline at line 710).
- Both no_kernel_warnings and no_new_kernel_warnings are true. The frozen validity rule independently rejects the clocksource event.
- NUMA result SHA-256: 42dc4f4631bbe24bce491d47e40977b50ac8462bda1db988c81303f3d01201ba.
- NUMA serial SHA-256: 18ac9f90880616d3cb229f77f1a5b385e171f7301d230c39bbfba7c82aa86a45.
- All 28 pre-change runtime files and the image are retained in runs/closeout-runtime; archive index SHA-256 a7e42aa5364874f86fc737dea3b3b3a0ac09d25461c684efe6c17296b22d818d.

## Closure and resources

The coordinator helper stopped before c-debug; no later matrix case, new build, calibration or timing ran. R4 retains two probe attempts and zero new builds. The logical C1 phase now totals ten guest attempts and four builds; its original owner-approved ceiling remains 120 total attempts, ten builds and the original wall limit. The stricter R4 deadline is 1794403573.5792072 and is retained for any continuation.

The original split leaves 22 probe and 88 fast units. A fresh full eight-case correctness matrix plus twelve calibration and four candidate probes requires 24 probe units; the fast plan requires 84 units. An aggregate-preserving reallocation under a separate frozen contract is a coordinator decision pending independent resource review. No budget, outcome, protocol or validity marker is rewritten here.

## Confidence and limitations

Confidence is high in the per-run observations and validity rejection. The corrected topology has fresh warning-free execution evidence, while full configuration coverage and calibrated performance remain missing. Clocksource cause and a supported auxiliary-environment correction are assigned to independent H18 review. This incident neither exempts clocksource fallback nor treats candidate correctness as complete. C2 and C3 runtime remains dependent on C1 correctness.
