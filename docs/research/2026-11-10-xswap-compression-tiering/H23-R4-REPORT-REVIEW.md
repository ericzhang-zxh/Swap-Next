# H23: Independent R4 report integrity review

Disposition: **PASS** for the reviewed local report and evidence bytes. No blocking report-integrity finding remains. Confidence: high. The report preserves the decisive distinction: the NUMA run passed all 17 integration gates but remains invalid solely because of `clocksource_fallback`.

Scope: the closed R4 report, its referenced frozen/raw evidence and source, and the current visual receipt. This is report integrity review. Final kernel-source acceptance, full correctness, performance acceptance, and live publication remain separate. All review work ran on the designated Linux worker through SSH. Only this review was authored; no report/source/state mutation, test-suite execution, build, guest, commit, push, publication, or delegation occurred.

## Reviewed identity

| Item | Exact identity |
| --- | --- |
| Report source pin | `8ac954f57299cbc8396d545984db9c20b9d8970b` |
| Native evidence | `9bade8bc8cd476d69f04677bdcd0b3f8ee2719da348968bb67e82af3078aab84` |
| Current rendered HTML | `e73771b4fe2943d8f30923810102b454ddd266b502224ca55280bb87ece3013a` |
| Unchanged K1 kernel commit | `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad` |
| Unchanged K1 tree | `8b085adc109e3b5467c3de998f11b04517f052a5` |
| Kernel anchor | `5e84ca928deeacb4eee656806a003f27d1eca82f` |
| Retained full patch SHA-256 | `69e085f0b3703ae2929c0cc8e863b6f606fce1b15e8a4d3ab3fd378ef785f704` |
| Archived runtime source commit | `687c19b361eed0ca50a95ea43648266fef329dc9` |
| Runtime archive manifest SHA-256 | `a7e42aa5364874f86fc737dea3b3b3a0ac09d25461c684efe6c17296b22d818d` |

## Raw outcomes, validity, and reset scope

| Run | Integration gates | integration_pass | run_valid | Invalid reasons |
| --- | --- | --- | --- | --- |
| `c1r4-b-common-001` | 19 / 19 | true | true | none |
| `c1r4-c-numa-001` | 17 / 17 | true | false | `clocksource_fallback` |

The actual result, serial, result-hash sidecar, start sidecar, and counted reservation bytes for both attempts match [observations.json](../../../campaigns/codex-compress-lib-r4-2026-11-10/report/observations.json). Result sidecars contain the actual result hashes. Every start-sidecar field is preserved. The reservations bind the correct probe pool, frozen protocol, configuration, workload, and topology; the stop decision binds the same result, serial, and reservation hashes. The NUMA topology arguments match the recorded command, including `4,sockets=2,cores=2,threads=1` and the two CPU-to-memory-node mappings.

The archived native `evidence.py` independently reproduces each result's complete metrics, gates, and subcase objects from the retained serial logs and frozen case definition. The original QEMU-exit rule reproduces both integration passes. Independently replaying archived `validity.clocksource_invalid` reproduces false for baseline and true for NUMA, the exact invalid-reason lists, and both saved `run_valid` values. Both NUMA warning gates remain true. Parser replay is read-only and creates no new guest or independent observation.

The exact NUMA serial events match the public observations:

| Serial line | Actual event |
| --- | --- |
| 501 | `tsc: Marking TSC unstable due to TSCs unsynchronized` |
| 604 | `clocksource: Switched to clocksource hpet` |
| 710 | `smpboot: CPU 1 is now offline` |

These retained boot-log events support the report's ordering claim. H18's later causal diagnosis is absent from the story, written report, and rendered text. The pinned incident document names cause analysis as separate pending work.

All three candidate subcases (`library_unit`, `guest_hotplug`, `memcg_balance`) retain PASS, valid evidence, and reset=true. Library placement records requested/actual nodes 0/0 and 1/1 with zero mismatches. The raw library-unit record has no reset-counter object; the public empty projection is rendered explicitly as "No reset counters emitted; untouched=true." Hotplug and memcg reset counters equal the raw fields. Both raw results lack broader teardown/cleanup-complete fields. The report retains that absence and limits its cleanup statement to normal exit, named subcase resets, and their emitted fields; no broader lifecycle audit is claimed.

## Runtime archive and reused builds

All **28** actual runtime files under `runs/closeout-runtime/benchmark/swap-standard/` match the archive manifest, totaling **3,945,355,673 bytes**. This includes the guest image and initramfs. All 25 tracked source files also match the archived source commit; the three raw guest artifacts match the manifest and recorded guest provenance. Both attempts' 24 retained harness files match their result fingerprints and the archive. All ten native source hashes and four frozen closeout-input hashes match their retained bytes.

Both reused builds pass the archived native configured-build binding and final-config checks, plus native reference-cache verification. Actual kernel-image and final-config hashes, source commits/trees, and provenance agree with observations. Their original counted build identities remain:

| Build | Original contract / evaluation | R4-bound immutable cache record |
| --- | --- | --- |
| `c1-base-common-20261110` | Original C1 / `3868cc40b0944c8f9b13b3aa529b5005` | `00df1c2b1823b86771a7871352d49a27ebd4fd8ed5587a697e2c2f2089c118b0` |
| `c1-7d5a3cfab2ab-debug-v2` | R2 / `38f0482dac984d48a7d4e9cc7289f1b0` | `17b59585730346357c7584109db2764d8342a016ecc3172c7cff471ec3265519` |

R4's two ledger rows are reused `BUILD_VERIFIED` coverage with `build_reserved=false`. They create no new build or independent sample. The two guest directories and two reservations are exactly baseline common and candidate NUMA. No candidate debug or other matrix case, complete correctness proof, calibration artifact, or evaluate/calibrate ledger row exists.

| Contract | Counted guests | Counted builds |
| --- | --- | --- |
| Original C1 | 3 | 3 |
| R2 | 2 | 1 |
| R3 | 3 | 0 |
| R4 | 2 | 0 |
| Cumulative through R4 | **10** | **4** |

All four frozen budget hashes match the report's observations. The continuation and closeout retain the unchanged K1 identity and one scientific hypothesis across infrastructure contracts. R4's deadline is `1794403573.5792072`, earlier than the inherited `1794404093.3209484` cap. The remaining frozen split is 22 probe guests, 88 fast guests, and six builds. This report claims no reallocation or reset.

## Exact reproduction and source fidelity

Native `delivery.extract` reproduces the current summary and evidence hash exactly. Native story validation passes and the summary has no review blockers. The unmodified generator ran against retained central evidence in a temporary output tree using the native page builder. All five required artifacts reproduce byte for byte:

| Artifact | SHA-256 |
| --- | --- |
| `summary.json` | `65adfc73e8e45d3983f72192c4c3dc8e2f479a44ea48651a4789024cda5a18a9` |
| `REPORT.md` | `0febd2e7fccfebfa3bd024ecffd93488faeb893e07a52c59c0c1bbc4afa21e48` |
| Dated `explainer.json` | `b2d59423706320bf8724a09b5d0fa8b7801e8be058d2972313599215cdeea81f` |
| Dated `explainer.html` | `e73771b4fe2943d8f30923810102b454ddd266b502224ca55280bb87ece3013a` |
| `generate_report.py` | `a22273e1891c6d56f6b04abd20f6aca3302aae482a3d4143907ff3f93ed5458e` |

All ten central report files, including the visual receipt, remain byte-identical across reproduction; temporary outputs were removed. The retained full patch equals the exact anchor-to-K1 Git diff. Each of the three displayed excerpts, comprising five hunks, matches its declared old/new source ranges and the retained patch body.

All 16 pinned source and reading references match their bytes at `story.source_commit`. Their HTML links use that exact commit. Internal fragment links resolve. The page has one dated explainer and no undated duplicate; all three core diff blocks are present immediately after Next and before audit evidence. All ten HTML tables remain inside closed disclosure controls. The initial narrative visibly preserves the validity failure and incomplete matrix. No private absolute host path or later-contract outcome appears in the rendered narrative.

## Visual receipt, publication boundary, and limitations

[visual-verification.json](../../../campaigns/codex-compress-lib-r4-2026-11-10/report/visual-verification.json) equals the native delivery receipt's visual-check object and binds the reviewed HTML. All four distinct screenshots match their hashes and declared widths: desktop 1440 x 6414 and mobile 390 x 8285, each in light and dark themes. Native delivery status validates as `visually_checked`. H23 verified receipt and screenshot integrity; the coordinator remains the recorded visual reviewer. H23 did not independently inspect rendered pixels. The earlier isolated `authoring-validation.json` is not current visual authority.

The earlier Original C1 and R2 canonical links return HTTP 200. The related R3 link first returned 503 and then GitHub Pages 404 on a bounded no-cache recheck. The coordinator confirmed that R3 and R4 are intentionally awaiting joint publication after this review and neither is marked live. That link is therefore publication-pending. The publisher must verify it and the new R4 page after deployment before claiming live delivery; H23 supplies no live-publication acceptance.

The invalid NUMA run provides its named functional observations while the full valid correctness matrix, calibration, performance, and equivalence remain absent. No broader teardown conclusion or future environment outcome is supported. This review performs no new source acceptance or promotion. No test, build, guest, or review process remains running from H23.

Reopen this disposition if any reviewed artifact, pinned source, raw evidence, archived runtime file, or visual binding changes, or if an independent visual finding contradicts the coordinator's receipt. Evidence changing the saved integration/validity distinction, event ordering, or reset-field scope would also require a revised review.
