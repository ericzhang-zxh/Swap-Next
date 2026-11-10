# Independent review of original C1 report

**Disposition: PASS for the original closed C1 report's evidence, claims, and core patch excerpts. No blocking report-content finding was identified.**

Reviewed integration: `0f58fb20300425b900a3731d0f91a8f63257638a`. Scope is only `codex-compress-lib-2026-11-10`; active R2 and the eventual family outcome are excluded. Reviewer: `final_independent_review`, independent of implementation and report authoring.

## Verified claims

Confidence is high for the report's recorded outcome:

- The original budget retains three executed guest attempts and three charged builds.
- Archived-parser replay of all three raw serial logs reproduces their saved gates and metrics. `c1-b-common-001` retains the sole failed configuration-identity gate; `c1-b-common-002` and `c1-b-legacy-001` pass. Their result sidecars, serial hashes, archived harness hashes, and guest manifests match.
- Two baseline builds are verified. The candidate compiler exited successfully, its final configuration enables PAGE_COMPRESS, and its build log includes `CC mm/page_compress.o`.
- The candidate's final configuration retains SLUB_TINY and lacks KASAN. The closed ledger correctly records `BUILD_FAILED` for configured coverage, distinct from compiler success.
- No original-C1 candidate guest, KUnit execution, sanitizer run, calibration, or performance comparison exists. The report makes no speed, equivalence, independent-XSwap, or tier-migration claim.
- The extraction's `inconclusive` verdict and `performance_accepted=false` match the closed outcome.

The source-level description is proportionate: the exact base/head source preserves the zswap_entry structure and per-CPU context field layout, while the report exposes the additional pool-wrapper allocation and leaves allocator footprint, call overhead, and fault latency unmeasured. The failure and coverage limitations remain visible in the overview.

## Core patch verification

All three excerpts match the exact kernel base `5e84ca928deeacb4eee656806a003f27d1eca82f` and candidate `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`:

| Excerpt | Verified source spans |
|---|---|
| Caller-owned API contract | Added header lines 8–50 |
| Compress, allocate, then return handle | Added page_compress.c lines 257–306 |
| Frontend pool delegation | zswap.c hunks -152/+140, -309/+266, -343/+276 |

Each hunk's old/new line counts and content were checked against Git source. REPORT.md contains the exact excerpts; decoded HTML line spans reproduce all three exactly. Their takeaways are supported by the shown code and retain the caller's publication/accounting/lifetime responsibility.

The full patch SHA-256 is `69e085f0b3703ae2929c0cc8e863b6f606fce1b15e8a4d3ab3fd378ef785f704`. All ten pinned evidence sources and three additional reading references match source commit `e38880e9363ef3c026028a67d8755df34792ae86`.

## Generator and artifact verification

Fresh native `delivery.extract()` reproduces summary.json exactly. Native story validation passes. The generator's in-memory specification matches explainer.json after JSON normalization.

I executed the existing renderer and generator post-processing statements in memory, omitting their filesystem-write portion. The result reproduces the committed HTML byte-for-byte:

- Evidence SHA-256: `b38eac31fdd29ae0ef949df8ab0afff75ec51ce2e83bb0862609d9bfcbfc80c9`.
- HTML SHA-256: `4e5aa8ebe342dc1e1a404aa3d83a18b1db9933cc1441adf92616770af57ee258`.
- All five delivery artifact hashes and the story hash match their actual bytes.

The generator rejects changed evidence, a non-closed/non-inconclusive contract, and newly recorded calibration/evaluation measurements. Its overrides correctly distinguish candidate compilation from failed configured coverage. The HTML has three explanation levels, core diffs after Next, four tables inside closed disclosures, no initially open details, and no absolute host paths. Card metadata correctly reports one candidate, three guests, and three builds.

## Delivery boundary

The current receipt is `state=visually_checked`. I independently verified all five delivery artifact hashes, the story hash, the HTML-bound visual receipt, and all four screenshot hashes. The receipt records the coordinator's real Chrome review at desktop/mobile widths in light/dark themes; this is the coordinator's visual inspection, not an independent browser review by this reviewer. authoring-validation.json describes an earlier isolated authoring snapshot; its different earlier HTML hash is not the current visual receipt.

This review approves report content and reproducibility. The coordinator's separate visual receipt is internally consistent with the reviewed HTML. Live publication and the final R2/family review remain outstanding.

Primary artifacts are under `campaigns/codex-compress-lib-2026-11-10/report/`: story.json, REPORT.md, summary.json, generate_report.py, delivery.json, and `codex-compress-lib-2026-11-10-2026-11-10/explainer.{json,html}`.

## Limitations

No kernel build, guest launch, campaign mutation, test-suite execution, browser visual review, or publication was performed. Raw replay used each original archived parser rather than relabeling old observations with current R2 inputs. All inspection was over SSH; the only write was this review. No reviewer process remains running.
