# H8: Versioned debug configuration for KASAN

Status: implemented, guest-free verified, and committed for coordinator integration.
Commit: 8f767e5c0ca346ad8a87c660c24b4bbe466b59a2.
Branch: infra/c1-debug-config-v2-01a1c6b6.
Worktree: worktrees/framework-c1-debug-config-v2-01a1c6b6.
Base: 13c3195eebd96698002237f2b6d8560b031029fc.

## Diagnosis and result

The exact K1 source 7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad declares KASAN at lib/Kconfig.kasan:46 and requires SYSFS && !SLUB_TINY at line 52. The retained c1-7d5a3cfab2ab-debug build has SLUB_TINY=y, SYSFS=y and all architecture/compiler prerequisites for generic KASAN enabled, but final KASAN is absent. Its other 23 required debug settings and the KCSAN exclusion match the trusted catalog. The final-config rejection correctly preserved the missing correctness capability.

H8 adds benchmark/config/compression-debug-v2.config. It is byte-identical to the frozen debug input except that the single CONFIG_SLUB_TINY=y line is replaced with an explicit disabled setting. The c1-debug-v2 catalog entry retains every original debug requirement and additionally forbids SLUB_TINY. The original c1-debug entry, path, input bytes and validation remain unchanged.

Only the existing debug-failures and numa-lifecycle groups accept c1-debug-v2 as an explicit alternative. Their original default remains c1-debug. The parser obtains the same exact group/configuration rule from the trusted catalog. Both v2 topologies require observed numeric nodes: 0 for single and 0-1 for numa2. Missing, blank, flat, malformed, contradictory and duplicated node observations fail identity validation.

Confidence: high for the source diagnosis and bounded input/catalog/parser repair. A new counted build's final .config and subsequent fully identified correctness guests are the observations required to validate the repaired capability.

## Frozen identities

| Input | SHA-256 |
| --- | --- |
| Retained compression-debug.config | c58461570b79210f9d99c7eb2e3a6e492601960ea73394bb4e4c78b147cd0ba4 |
| New compression-debug-v2.config | df562dced5dce4462aa061ea25698ba3a2400e9bfcc078961a2e35a89c2905ee |

The diff against base 13c3195 is empty for every original common, legacy, debug, KCSAN, disabled-build and timing input. No real protocol, profile, campaign evidence or candidate source was edited.

## Verification

The focused selection ran 97 tests in 10.087 seconds: 96 passed and one expected test was skipped because this isolated framework worktree has no linux checkout.

    PYTHONPATH=benchmark/swap-standard:. python3 -m unittest \
      test_compression_evidence.DebugConfigurationV2Tests \
      test_compression_evidence.CompressionEvidenceTests \
      test_compression_evidence.Revision8ProtocolTests \
      test_runner evolve.test_compression_coverage

Eight added tests cover frozen old bytes, the exact one-line input correction, unchanged debug requirements, forbidden tiny allocation, required KASAN and NUMA, exact permitted groups, both real numeric topologies, malformed/missing node observations, old-versus-v2 runtime identity, and separate exact frozen input pins. The existing synthetic coverage fixture now pins only configurations actually used by its matrix, so an additive catalog entry leaves its legacy contract unchanged.

The git diff --check check passed. The isolated worktree is clean. Eric Zhang authored the scoped commit without a DCO trailer.

## Integration requirements

1. Preserve the original failed debug build, its spent build count and original frozen contract.
2. Integrate the H8 commit only after the coordinator has archived the original C1 execution state.
3. In the replacement contract, explicitly select c1-debug-v2 for debug-failures and numa-lifecycle and pin its new input SHA-256. Keep the old protocol bytes and all other configuration/gate/timing parameters unchanged. Remove the old c1-debug pin from the new contract only if no new matrix row uses it.
4. Use a new counted configured build. Require final KASAN=y, all existing debug flags and SLUB_TINY=n before any corresponding guest.
5. Bind future results to the current host catalog/parser hashes. H8 changed no guest image source; the current image manifest's source set has no intersection with the changed host parser/catalog/test files.

The coordinator owns the replacement campaign and carrying the already spent work within the original 120-guest, 10-build and 18-hour phase envelope. H8 provides no extra experimental budget.

## Limitations

H8 performed no kernel build, Kconfig regeneration, guest execution, image preparation, live campaign mutation, AGY delegation, push, host change or candidate modification. Synthetic final-config checks are host validation tests. Actual compiled capability and guest correctness remain pending. No H8 process remains running.
