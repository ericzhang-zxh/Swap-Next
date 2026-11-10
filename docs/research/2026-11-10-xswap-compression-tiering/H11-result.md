# H11: Strict compression framing repair

Status: implemented and committed for coordinator integration.
Commit: 26a59a1af152fd0b4d0582da7188c9007c0c6f80.
Branch: infra/c1-parser-framing-01a1c6b6.
Worktree: worktrees/framework-c1-parser-framing-01a1c6b6.
Base: 0f58fb20300425b900a3731d0f91a8f63257638a.

## Result

The parser accepts the exact line below only once while invalid_codec is in its observation state:

    zswap: compressor swap_next_invalid_codec_7d83 not available

It retains the line in that subcase's expected_diagnostics as kind invalid_codec_rejected. Different codec names, extra text, duplicates, placement in another subcase or after reset, unknown compression records and kernel warnings remain failures. The semantic errno, unchanged codec, data, storage, charging and reset observations remain mandatory.

KUnit parsing now accepts either the original strict fixture without summaries or this exact ordered pair immediately before the suite success:

    # page_compress: pass:3 fail:0 skip:0 total:3
    # Totals: pass:3 fail:0 skip:0 total:3

Nonzero or contradictory counts, malformed, partial, duplicated or reordered summaries, real SKIP/TODO directives, and missing, duplicated or reordered test cases remain failures. The three expected successful cases and NUMA observations remain mandatory.

Confidence: high for the bounded parser correction. A future correctly bound counted run is the observation required for new campaign coverage.

## Retained-run diagnostic replay

The unchanged serial from c1r2-c-debug-001 was parsed in memory using the corrected parser. All 19 parser gates were true. Its six subcases were PASS, reset and evidence_valid; no kernel diagnostics or further gate failures appeared. The observed expected printk was retained as a typed diagnostic. The original result still records its parse_error and remains a failed counted attempt.

| Artifact | SHA-256 |
| --- | --- |
| Retained serial.log | 87c7ebe30f51fd8ce45a14b188a7140bef043fc806cac95011f9b8793b788280 |
| Retained result.json | 2c8ac864d761e796c0d439f4f069502fed3d8f26e8031bd0da4d4651966b9d6e |
| Corrected evidence.py | 748ad9a8ab7463d0845925d51cfda21775e5d0fc5f23159477bff4abf4966d83 |

Both retained hashes were identical before and after the replay. Evidence location: campaigns/codex-compress-lib-r2-2026-11-10/runs/guests/c1r2-c-debug-001/.

## Verification and handoff

The focused selection ran 61 tests: 60 passed and one expected test was skipped because the isolated framework worktree has no linux checkout. Seven added tests cover actual observed framing and summary text, narrow diagnostic placement, retained semantic checks, warnings, exact optional summary pairs, malformed counts and test-case ordering.

    PYTHONPATH=benchmark/swap-standard:. python3 -m unittest \
      test_compression_evidence.CompressionFramingTests \
      test_compression_evidence.CompressionEvidenceTests \
      test_compression_evidence.DebugConfigurationV2Tests \
      test_compression_evidence.Revision8ProtocolTests test_runner

The git diff --check check passed. Only evidence.py and test_compression_evidence.py changed; the isolated worktree is clean.

The coordinator owns R2 closeout and the new frozen continuation within the remaining phase resources. Preserve the old result, reservation and budget charge. Future results must bind the corrected host parser hash. H11 changes no guest/image source or measurement parameter.

## Limitations

This replay is a parser diagnosis, not a replacement guest or a reassignment of the original outcome. H11 ran no build, guest, image preparation, live campaign operation, protocol/budget change, raw-evidence mutation, delegation or publication. No H11 process remains running.
