# Xswap discovery results — 2026-10-21

Three feedback-driven experiments completed. **None is accepted as a performance improvement.** All three passed the bounded guest gates, but mapped-cluster state varied greatly in A/A and candidate effects were mixed. No kernel change was promoted or merged.

The run used the separately imported Phase I v4 + Phase II v1 reference; Phase III was excluded. It does not compare xswap against ordinary swap or establish that xswap itself is faster.

## Completed work

- 35 independent guest attempts: 2 successful smoke boots, 8 A/A boots, 24 candidate/reference boots, and 1 retained startup-configuration failure.
- 34 boots passed data integrity, fork/COW, xswap PTE identity, live xswap destruction, physical swapoff, backend activity and no-warning gates. Each successful workload supplied 16,384 first-access samples.
- Exact replay reproduced all 26 imported commits and the reference tree through a separate controller worktree.
- One reference and three candidate kernels compiled; each candidate passed scope, diff and checkpatch checks.
- The initial reference input config warned about a repeated DEBUG_FS assignment. The input was deduplicated; all four normalized build configs match, and candidate builds emitted no warnings.
- Controller tests: 41 passed. Xswap parser/provenance tests: 26 passed, including a real disk-run fixture.
- Guest isolation: 4 GiB RAM, 2 vCPUs, private 8 GiB virtio disk, no network or host mounts. No host kernel, swap or reboot changes.

## Observed candidate means

Each cell shows reference → candidate mean over only two independent runs per backend. These are observations, **not causal effect estimates**. Latency is the mean of per-run p99, not a pooled p99. Mapped clusters measure one metadata mapping, not total physical memory.

| Trial | Disk mapped clusters | Zswap mapped clusters | Disk p99 (us) | Zswap p99 (us) | Discovery score |
|---|---:|---:|---:|---:|---:|
| xswap-shrink-min4 | 1058.5 → 219.0 | 1642.5 → 2445.5 | 368.7 → 336.6 | 259.3 → 251.5 | 0.672 |
| xswap-grow-cap8 | 1058.5 → 219.0 | 1350.5 → 1496.5 | 335.8 → 333.0 | 223.1 → 233.5 | 0.862 |
| xswap-grow-target75 | 1898.0 → 949.0 | 2774.0 → 2920.0 | 363.3 → 384.9 | 257.7 → 218.1 | 0.897 |

1. **Shrink minimum 8 → 4 chunks:** some extra shrink activity, but mixed retention. Zswap candidate tails ended with only 82/121 free clusters while mapped ranges remained large; further lowering the minimum alone was not a convincing next step.
2. **Growth cap 4 → 8 chunks:** zswap recorded growth operations fell from 15–16 to 13 in both candidate runs. This is the clearest mechanism lead, but memory and latency did not establish a net improvement.
3. **Retain cap 8, target occupancy 65% → 75%:** recorded growth operations increased to 18–19 on disk and 23 with zswap. The tighter target did not reliably reduce settled mappings.

## Why no winner is declared

A/A used exactly the same reference image on both sides. Disk mapped-cluster values were 219 or 1,898; zswap values were 219 or 2,774. Thus even an apparent many-fold average reduction can arise without a code change. Shrink counters correlated with the lower retained state; asynchronous reclaim and allocation layout are plausible contributors, not a fully isolated causal diagnosis. The aggregate A/A discovery score concealed this variation, so per-run evidence is essential.

The test checks a deterministic compressible 64 MiB target under 5 GiB allocation pressure. It has no fragmented or multi-device workload, oscillating-pressure matrix, independent confirmation/holdout, allocation/IO fault injection, memcg limits, large-folio validation or sanitizer matrix. Six snapshots miss the peak during the pressure process. Swapped-PTE first access can involve cache/readahead and scheduler effects. These limits block promotion even when the pilot gates pass.

## Next research step

Keep the imported reference unchanged. Before a larger search, add phase-specific allocation/retention accounting and growth/shrink tracing, then stabilize or stratify the retention state in a separately frozen baseline protocol. The larger growth cap is a candidate for that investigation, not a recommended production setting. Do not tune away the current negative results.

## Evidence and reproduction

- [Machine-readable per-run summary](summary.json): allowlisted metrics, snapshots, counters, gates and source/image/raw-log hashes.
- [Source and invariant review](review.md).
- [Reference patch provenance](../../patches/xswap-reference/README.md) and exact replay helper.
- [Three independent experimental patches](../../patches/xswap-experiments/manifest.json); they are alternatives, not a series.
- [Harness and frozen protocol](../../Evolve/xswap/README.md).

Raw serial logs, guest disks, build outputs and OpenEvolve database remain on the Linux worker. Public exports omit machine paths and identifiers. OpenEvolve stores feedback and selects references; the active assistant proposed each experiment. No unattended model service or future scheduled run was installed.
