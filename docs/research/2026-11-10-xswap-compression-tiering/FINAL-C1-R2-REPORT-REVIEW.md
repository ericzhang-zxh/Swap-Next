# Independent review of the closed C1 R2 report

**Disposition: PASS for the R2 report's evidence, claims, core patch excerpts, and reproducibility. No blocking report-content finding was identified.**

Reviewed integration and pinned source: `6f3f59219a3e4c709097713794c18bac5ec2b452`. Reviewer: `final_independent_review`, independent of report authoring and implementation. Scope is the closed `codex-compress-lib-r2-2026-11-10` contract, including its cumulative cost through R2 closeout. Active R3 evidence and the eventual family outcome are excluded.

## Evidence and outcome

**Confidence: high.** The report preserves the decisive distinction: the corrected debug build and raw guest output exist, while the saved candidate integration result remains failed and the complete correctness matrix remains incomplete.

I verified `report/observations.json` against the actual retained result files, serial logs, configured build, archive, and budget files:

- R2 has two counted guests and one counted build. Original C1 retains three guests and three builds; their cumulative cost through R2 is five guests and four builds.
- Both raw result sidecars and serial hashes match. Their harness hashes and guest manifests match the archived pre-fix runtime. All **28/28** archived files match `runs/closeout-runtime/archive.json`.
- Archived-parser replay of `c1r2-b-common-001` reproduces every saved parser gate and metric. The original baseline result is successful.
- Archived-parser replay of `c1r2-c-debug-001` reproduces its exact saved invalid-codec parse error. The saved result retains `integration_pass=false` and `parse_complete=false`.
- The candidate raw log contains exactly the six reported PASS/reset subcases and the three named KUnit `ok` cases. Both standard summaries report `pass:3 fail:0 skip:0 total:3`. The archived diagnostic scan finds no kernel diagnostic.
- Feeding the exact retained KTAP body to the original validator reproduces `KUnit skip or TODO is incomplete coverage`. This independently supports the report's second parser-defect diagnosis without rewriting any outcome.
- Native configured-build validation passes the exact source, input/final configuration, kernel image, builder/toolchain, original protocol/ledger, and counted-cost checks. The final configuration contains `CONFIG_KASAN=y`; its hash and image hash match the candidate raw record.
- The closed ledger contains no calibration or performance comparison. Native extraction returns `inconclusive` and `performance_accepted=false`.

The overview, result tiles, raw-signal table, and Limitations preserve these boundaries. They make no speed, equivalence, independent-XSwap, completed-matrix, or tier-migration claim. Corrected replay is described as diagnosis, with fresh counted correctness required for continuation.

## Source and patch claims

The mechanism description matches the retained K2 source review and exact unchanged kernel source. ZSwap retains frontend publication, accounting, references, indexes, and release obligations; the shared library owns codec contexts and object storage. The report presents this as a source-level ownership boundary rather than measured performance.

All **three excerpts / five hunks** match exact base `5e84ca928deeacb4eee656806a003f27d1eca82f` and candidate `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`. Old/new hunk counts and source spans were checked. REPORT.md contains the exact excerpts, and decoded HTML line spans reproduce them exactly.

The retained R2 patch is byte-identical to original C1: SHA-256 `69e085f0b3703ae2929c0cc8e863b6f606fce1b15e8a4d3ab3fd378ef785f704`. All **10** native evidence sources and **5** additional reading references, including observations and incident 003, match the pinned report source commit.

## Generator and delivery

Fresh native `delivery.extract()` reproduces summary.json exactly. Native story validation and the generator's observation/closeout/hash/accounting checks pass. I executed the existing renderer and generator's transformation statements in memory, excluding their filesystem writes. The resulting specification, HTML, and REPORT.md reproduce the current artifacts exactly.

| Artifact | SHA-256 |
| --- | --- |
| Native evidence | `4b306f11804d960957b5f3367aef72963b4319aff787dc0256675bf53bb382ed` |
| Public observations | `dd37c813fcb6ca9236faadbd058bb8b3014270f3606d735b098afc237f03f7c5` |
| HTML | `3b7fdbc6280fb401047fa01ff4b50fcb53a69e3fd7a2b8198dbc346a7de90305` |

The HTML retains three explanation levels, Next before the core patches, and audit evidence after the patches. All eight tables are inside initially closed disclosures; no details are initially open. The page contains no absolute host paths. Card metadata correctly reports one candidate, two guests, and one build for R2, while cumulative cost is separately labeled in the report.

Delivery is `visually_checked`. I verified all five delivery artifact hashes, the story hash, and the coordinator's HTML-bound visual receipt plus all four screenshot hashes. The receipt covers desktop/mobile and light/dark views. Browser visual inspection belongs to the coordinator; this reviewer checked receipt integrity only. The earlier authoring-validation.json is explicitly an isolated authoring snapshot, not the current visual receipt.

## Limitations

This review approves the closed report's content and reproducibility. Live publication and final R3/family review remain separate. It does not repeat the full K1 source audit or grant runtime/performance acceptance. No kernel build, guest, campaign mutation, test-suite run, independent browser inspection, commit, push, or publication was performed. All checks ran over SSH; the only write was this review. No reviewer process remains running.
