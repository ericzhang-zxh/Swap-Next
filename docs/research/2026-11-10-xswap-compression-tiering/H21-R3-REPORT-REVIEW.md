# H21: Independent R3 report integrity review

Disposition: **PASS**. No blocking report-integrity finding remains for the reviewed bytes. Confidence: high. The report accurately presents a closed, infrastructure-incomplete contract: two complete per-run passes, a genuine failed NUMA warning gate, and an incomplete full correctness matrix.

Scope: the current central `campaigns/codex-compress-lib-r3-2026-11-10/report/` and its referenced frozen source, raw evidence, and delivery receipt. This is report integrity review, not final kernel-source acceptance or a performance verdict. Review work ran on the designated Linux worker through SSH; no kernel build, guest, source edit, campaign mutation, commit, push, or publication was performed.

## Reviewed identity

| Item | Exact identity |
| --- | --- |
| Report source pin | `687c19b361eed0ca50a95ea43648266fef329dc9` |
| Native evidence | `2bbb64da1f9c9146e03133fa18e6b3ca1015758a3ba59c39f6aec61033b70c63` |
| Current rendered HTML | `e994dcc84527f1826bb8a31e36a1f8350a27013d6c229752a6355e90cd9c2fe8` |
| Unchanged K1 kernel commit | `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad` |
| Unchanged K1 tree | `8b085adc109e3b5467c3de998f11b04517f052a5` |
| Kernel anchor | `5e84ca928deeacb4eee656806a003f27d1eca82f` |
| Retained full kernel patch SHA-256 | `69e085f0b3703ae2929c0cc8e863b6f606fce1b15e8a4d3ab3fd378ef785f704` |
| Archived runtime source commit | `6f3f59219a3e4c709097713794c18bac5ec2b452` |
| Runtime archive manifest SHA-256 | `a6a788c5146b06a64e339a4126e49f10219bae39ff7c66a8ea800ff9406d9867` |

Main advanced from `dd23123a98b667b95c07c483afe9dd56345b98c7` to `8ac954f57299cbc8396d545984db9c20b9d8970b` during this bounded review. The R3 report and source bindings above remained unchanged. Future R4 evidence is excluded from this disposition.

## Raw outcomes and archive integrity

| Run | Gates passed | Integration | Independent archived-parser reproduction |
| --- | --- | --- | --- |
| `c1r3-b-common-001` | 19 / 19 | true | Exact metrics, gates, and subcases |
| `c1r3-c-debug-001` | 20 / 20 | true | Exact metrics, gates, and six subcases |
| `c1r3-c-numa-001` | 15 / 17 | false | Exact metrics, gates, and three subcases |

For all three attempts, actual `result.json`, `serial.log`, `result.sha256`, `started.json`, and reservation bytes match [observations.json](../../../campaigns/codex-compress-lib-r3-2026-11-10/report/observations.json). The hash sidecars contain the actual result hashes. Every start-sidecar field is preserved in the result. Counted reservations bind the run identity, frozen protocol, configuration, and topology; the stop decision binds the same result, serial, and reservation hashes. All 24 retained per-run harness files also match their result fingerprints and the runtime archive.

All 28 files under `runs/closeout-runtime/benchmark/swap-standard/` were hashed from their actual bytes: **3,945,340,687 bytes**, including `bench.img` and `initramfs.cpio.gz`. Every hash matches `runs/closeout-runtime/archive.json`. Its 25 tracked source files additionally match the archived source commit; the three raw guest artifacts are bound by their archive and run-provenance hashes.

The archived `evidence.py` was imported without bytecode writes and called only as a parser on the retained serial logs, with each case from the frozen protocol. Recomputed metrics, gates, and complete subcase objects equal the raw result objects. The original QEMU-exit rule then reproduces each integration result. This is a read-only replay of existing evidence and adds no guest or independent measurement.

The NUMA serial log retains the cache-sibling message at line 540 and the `arch/x86/kernel/smpboot.c:329` / `topology_sane` warning at lines 541-543. Both `no_kernel_warnings` and `no_new_kernel_warnings` remain false. The `library_unit`, `guest_hotplug`, and `memcg_balance` subcases retain PASS, valid evidence, and reset records. Requested/actual placement pairs are 0/0 and 1/1, with zero mismatches. The report's topology arguments match the actual QEMU command. Its high-confidence diagnosis is evidence-supported and accompanied by the falsifier that a correctly mapped fresh topology reproduces the warning.

## Reused builds and resource accounting

Both reused builds pass the archived native `verify_build_binding`, final-configuration validator, and native reference-cache verification. Actual kernel-image and final-config bytes match the reported hashes, and source trees resolve to the recorded Git identities. Original counted build provenance is preserved:

| Build | Original contract / evaluation | Immutable cache record |
| --- | --- | --- |
| `c1-base-common-20261110` | Original C1 / `3868cc40b0944c8f9b13b3aa529b5005` | `9a00a15d17bc365a02d323942d84182defbeae7ae6b0843a205e42e4001aed52` |
| `c1-7d5a3cfab2ab-debug-v2` | R2 / `38f0482dac984d48a7d4e9cc7289f1b0` | `edb678e82b0923dd22d01a10f9346eeab51304f4c458299894721eb913daf61b` |

The R3 ledger contains three `BUILD_VERIFIED` coverage rows referencing these two existing builds; every row has `build_reused=true` and `build_reserved=false`. Their reuse creates no new build or independent sample.

| Contract | Counted guests | Counted builds |
| --- | --- | --- |
| Original C1 | 3 | 3 |
| R2 | 2 | 1 |
| R3 | 3 | 0 |
| Cumulative through R3 | **8** | **4** |

All three budget hashes match observations. All eight reservations remain counted as STARTED. The three closeouts bind the same K1 commit/tree, supporting the report's one-hypothesis account across separate frozen infrastructure contracts. R3's actual deadline is `1794404093.3209484`, earlier than the inherited maximum `1794404672.500093`. The remaining ceilings are 24 probe guests, 88 fast guests, and six builds; no resource reset appears in this report.

## Reproduction, source citations, and disclosure

`delivery.extract` reproduces the current summary object and native evidence hash exactly. All ten native source hashes and all four frozen closeout-input hashes match current retained bytes. Native story validation passes, and there are no native review blockers.

The unmodified report generator ran in a temporary output tree, using the central retained evidence and the native page builder. The five required artifacts reproduce byte for byte:

| Artifact | SHA-256 |
| --- | --- |
| `summary.json` | `eb365eca912d3ed1924b370f89e925e02293acfc3744ada9002b47b466d278bd` |
| `REPORT.md` | `cb8b6571af70344db69dd2ad38af250abe7a1e8ab198e31e6c280d7d35ae25c9` |
| Dated `explainer.json` | `3245053243af5c22ea59de4e99adacdebf81c725c8b8f57d967cee7a66837a06` |
| Dated `explainer.html` | `e994dcc84527f1826bb8a31e36a1f8350a27013d6c229752a6355e90cd9c2fe8` |
| `generate_report.py` | `7eb942dd7aabbd77b33d3d19cbc4da38d759ab140726595f4a65e3f697fa16bf` |

All ten central report files, including the visual receipt, remained byte-identical across that operation; temporary outputs were removed. The generator preserves the original failed NUMA outcome and derives exact counts from the bound observations and native summary.

The retained full patch equals `git diff` from the anchor to K1. All three displayed excerpts, comprising five hunks, match their declared old/new line ranges in the exact kernel sources and their retained full-patch bodies. The source-bound K2 review supports the stated frontend/library ownership boundary and remains explicitly source-level evidence.

All 15 pinned source and reading references exist at `story.source_commit` and match the current referenced bytes. The HTML links use that exact commit. Both earlier-contract links returned HTTP 200. Internal fragment links resolve. The dated explainer is unique, with no undated duplicate. The section order is context, whole system, subsystem, concrete change, results, next, core patches, and audit evidence after the verdict. All nine HTML tables are inside closed disclosure controls, all three diff blocks are present, and no absolute private host path or R4 outcome appears in the narrative. Failed warning gates and incomplete coverage are visible outside collapsed evidence.

## Visual receipt and limitations

[visual-verification.json](../../../campaigns/codex-compress-lib-r3-2026-11-10/report/visual-verification.json) equals the native delivery receipt's visual-check object and binds the reviewed HTML hash. All four distinct PNGs have the declared widths and matching SHA-256 hashes: desktop 1440 x 6545 and mobile 390 x 8393, each in light and dark themes. The native delivery status validates as `visually_checked`. The coordinator is the recorded visual reviewer; H21 verified receipt and screenshot integrity without independently inspecting rendered pixels. `authoring-validation.json` is an earlier isolated snapshot and is not the authority for current visual acceptance.

R3 remains closed and infrastructure-incomplete. The full configuration-bound correctness matrix, calibration, performance, and equivalence results are absent, as the report states. The three successful NUMA subcases do not replace its failing overall result. This review makes no new final source-acceptance, performance, promotion, or R3 live-publication claim. No tests, builds, guests, or review processes remain running from H21.

The disposition must be reopened if any reviewed report artifact, pinned source, raw result, runtime archive, or visual binding changes. Independent visual findings or evidence contradicting the stated topology diagnosis would also require a revised review.
