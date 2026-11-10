# H5: Explicit flat-memory topology observation

Status: implemented, guest-free verified, and committed for coordinator integration.
Commit: `bfd6d400a4a81a44750c60731c322d02da54d59e`.
Branch: `infra/c1-flat-observer-01a1c6b6`; base: `b1a7ee8`.
Worktree: `worktrees/framework-c1-flat-observer-01a1c6b6`.

## Result

The revision 8 guest now emits `ONLINE_NODES flat` when the node sysfs directory is absent and the requested topology is `single`. An existing node directory must supply a readable, nonempty `online` file. A missing node directory under `numa2` fails explicitly. Numeric node IDs remain actual observations.

The parser accepts `flat` only for `c1-common`, `c1-legacy`, and `c1-kcsan` with single topology. Their final-config catalog now requires explicit `CONFIG_NUMA=n`. Debug single-node and two-node cases retain their numeric `0` and `0-1` requirements. Missing, blank, duplicated, conflicting, and malformed topology markers fail. All existing input configuration bytes remain unchanged.

Confidence: high for the source diagnosis and bounded correction. A counted non-NUMA retry that still lacks configuration identity would reopen it.

## Verification

The following guest-free selection ran 45 tests: 44 passed and one expected test was skipped because the isolated framework worktree has no `linux/` checkout.

    PYTHONPATH=benchmark/swap-standard:. python3 -m unittest test_compression_evidence.CompressionEvidenceTests test_compression_evidence.Revision8ProtocolTests test_runner

Five new tests cover all three permitted flat configurations and timing, rejection for both debug topologies, explicit marker uniqueness, required disabled NUMA in final configs, and the real guest shell observer against temporary sysfs fixtures. `sh -n benchmark/swap-standard/guest-init` and `git diff --check` passed. The input-config diff against `b1a7ee8` is empty.

Read-only diagnosis of the retained `c1-b-common-001` log reproduces exactly one false parser gate: `configuration_identity`. Replacing its empty `ONLINE_NODES` line with `ONLINE_NODES flat` in memory makes all parser gates true. This diagnostic produced no replacement evidence or pass record. Raw bytes retained these SHA-256 values:

- `serial.log`: `13d0051f8d9c9a6a853efa4ad78cf4abe4f21df2ac571922be28adb244ba9a46`
- `result.json`: `5076e03403000c191c77338785c38d60e7bf98b1941162059ad39d42acfedb0d`

## Integration and limitations

The coordinator owns integration, preservation of the old image and counted incomplete attempt, new image preparation, and an explicitly reconciled counted retry. H3 owns infrastructure-attempt reconciliation separately. The old blank observation still fails the new parser.

H5 ran no kernel build, image build, guest, campaign action, protocol/profile change, push, delegation, or host mutation. Actual corrected guest output and complete correctness coverage remain unmeasured. No H5 process remains running.
