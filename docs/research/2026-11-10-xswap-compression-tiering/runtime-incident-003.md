# Runtime incident 003: expected diagnostic and zero-skip framing

The corrected debug-v2 kernel built with the required KASAN configuration and completed the c1r2-c-debug-001 guest. The trusted parser rejected an expected diagnostic emitted by the deliberate invalid-codec test. A diagnostic-only in-memory replay then identified a second parser defect: the word skip in the standard KUnit zero-skip summary was treated as a skipped test. The original result remains failed and counted; no raw bytes or outcome were rewritten.

## Retained observations

- Candidate source remains 7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad, tree 8b085adc109e3b5467c3de998f11b04517f052a5.
- Configured build c1-7d5a3cfab2ab-debug-v2 is BUILD_VERIFIED. Final configuration SHA-256 is 8a3a8a5cc861fd0e4c4d5d5b2974d3b54e016e7d5593caeb0b949f07ae22d436 and includes CONFIG_KASAN=y.
- Guest exit code is zero, run_valid is true, wall time is 71.552 seconds, and the original integration_pass is false with parse_complete=false.
- Exact rejected line: zswap: compressor swap_next_invalid_codec_7d83 not available. It occurs during invalid_codec observations and is also retained in the complete kernel log.
- Six raw subcases report PASS with reset records: invalid_codec, library_unit, large_folio, memcg_balance, memcg_offline and memcg_limits. The three named page_compress KUnit cases report ok; their standard summaries contain pass:3 fail:0 skip:0 total:3.
- The serial log contains no KASAN, lockdep or other kernel diagnostic. These are retained raw observations; the full candidate correctness matrix is incomplete.
- Raw serial SHA-256: 87c7ebe30f51fd8ce45a14b188a7140bef043fc806cac95011f9b8793b788280.
- Raw result SHA-256: 2c8ac864d761e796c0d439f4f069502fed3d8f26e8031bd0da4d4651966b9d6e.

## Correction and accounting

H11 is a narrow trusted-parser correction. It admits only the exact expected invalid-codec diagnostic in its named observation state and recognizes the exact zero-skip summary framing. Unknown records, real SKIP/TODO directives, nonzero or contradictory summaries, missing cases and kernel diagnostics remain failures. Corrected replay is diagnostic evidence only; the saved failed result is not replaced.

R2 is closed with two probe guest attempts and one build. Including the original C1 contract, the same logical phase has spent five guest attempts and four builds. Any continuation has at most 27 probe guests, 88 fast guests and six new builds, and must end no later than the earlier enforced R2 deadline 1794404672.500093. The original contracts, raw attempts, build provenance and deadlines stay intact. A separately frozen corrected-parser contract must collect fresh counted correctness evidence on the same kernel source before calibration.

The complete pre-fix runtime is retained under the R2 runs/closeout-runtime archive, with 28 pinned files and archive SHA-256 3f841eec2857834246ddf1681010bba2cf1362c2677c3c92263cfac8623a5e1d. No performance measurement or code promotion occurred. C2 and C3 remain dependent on complete C1 correctness.

## Confidence and limitation

Confidence is high that the observed rejection is caused by these two parser rules: the exact raw lines reproduce both failures, and the corrected diagnostic replay validates all six subcases. Missing matrix rows and calibrated timing remain missing. A kernel diagnostic, a failed raw subcase, or an unexplained replay mismatch would change this classification and stop dependent execution.
