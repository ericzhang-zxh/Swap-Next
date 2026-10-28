# kbench setup smoke, 2026-10-27

Integration smoke for the swap-standard switch to Chris Li's kbench setup
(backends, THP policy, kernel build). KVM, 8 vCPU / 8192 MiB, plain mode,
kernel `kb-xs-desc-v1` (`5e84ca92` with THP enabled). One guest per case; no
calibration and no comparison.

| Run | Case | Result | Notes |
|---|---|---|---|
| 1 | all three | setup failed in 4 s | THP loop wrote the read-only `hugepages-8kB/enabled`; fixed with `thp_set` |
| 2 | swapin / zram-64k | all gates pass | 64 KiB only `[always]`; routed to zram0; seq mean 1.63 µs, rand mean 19.7 µs |
| 2 | usemem / zswap | all gates pass | 2 MiB only `[always]`; routed to zram1; zswpwb 529,896 |
| 2 | build / zram | memcg OOM | 470M memcg, `make -j32` defconfig; objtool killed after about 17 min |

## Finding: the kbench build does not fit 470M on this source tree

Confidence: high for this tree and guest. objtool on vmlinux reached
anon-rss 465,668 kB with 113,948 pages (445 MiB) already swapped to zram0, and
the memcg OOM killer fired; `memory.oom.group` then killed the build. Swap was
available and THP swap-out worked (`thp_swpout` 1940), so the limit, not the
swap setup, ended the run. The build source is `744e5400` (7.3-rc); Chris's
kbench extracts his own `linux.tar.xz`, whose version is unknown here. A run on
his source version, or his answer about it, would change this finding.

## Limitations

Single guests; no noise estimate. The `build` workload has no passing run yet
under the kbench parameters.
