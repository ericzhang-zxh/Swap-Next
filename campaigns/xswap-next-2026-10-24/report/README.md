# xswap continuation: 2026-10-24

Status: complete. Three candidates screened out; none eligible for slow confirmation or promotion. All experiment processes have stopped.

[Live review](https://ericzhang-zxh.github.io/Swap-Next/xswap-next-2026-10-24/) | [Full report](REPORT.md) | [Machine-readable summary](summary.json) | [Evidence audit](evidence-audit.json)

| Round | Candidate | Result |
|---|---|---|
| 1 | VMA-only sequential admission | No physical prefetch; disk tail guards fail |
| 2 | Linearize split compressed inputs | Compressed sequential mean +24.4%; all compressed guards fail |
| 3 | Adjacency admission in both modes | Disk sequential mean -40.2%; random p99 +29.5%, guard fails |

These are two-pair fast observations. Source/counter evidence supports activation of round 3's physical prefetch path. Confidence in general performance attribution remains limited by between-run variation; independent profiling or confirmation could change it.

48 KVM guests completed with integration gates passing, including eight targeted correctness/debug guests. Six builds passed. Two candidates have passed KASAN and PROVE_LOCKING builds recorded in `summary.json`; the auxiliary-guest reports do not name the kernel build they booted, so a KASAN/lockdep guest pass is not re-derived here. The last candidate also has a passed CONFIG_SWAP=n build, `xs-ra-cluster-v1-noswap`. The independent audit recorded 48 result/log hash pairs (96 hashes), candidate identities, all 24 paired metric ratios, the P123 baseline ancestry and the shared budget. `evidence-manifest.json` has 128 entries. All 128 paths are worker-local, and none of those files are in this tree.

## Next

Investigate variance and demand-first speculative I/O before further optimization. Preserve the rejected patches and raw measurements. No candidate qualifies for the slow tier under the current policy.

## Limitations

The first sparse-image A/A failed its noise gate. Preallocation revision 2 passed, with the initial failure retained. Full promotion still requires missing policy gates and independent evidence; see REPORT.md. Candidate code has not been promoted. This report is published independently on main and Pages. The KASAN configurations retain the same pre-existing vma.c frame-size warning and config overrides as their baseline; no new build diagnostics were found.

## Source and publication

Scientific results are pinned to [experiment snapshot `15bf186`](https://github.com/ericzhang-zxh/Swap-Next/tree/15bf186f665368ce19868e5268c422a240ba6699/results/xswap-next-2026-10-24). The full runtime logs remain on the Linux worker; the public manifest preserves their identities and hashes.

These files were copied from that snapshot so the report can be read without the experiment branch: `generate-report.py`, `verify-evidence.py`, `run-aux.py`, `protocol-revision1.json`, and `contract.json` (publication wording updated; see `publication_field_history`). `protocol-revision2.json` is a byte copy of `benchmark/swap-standard/protocol-xswap-next-2026-10-24.json` at the same snapshot. The campaign policy with the publication wording updated is [policy.json](../policy.json). The manifest hash matches [policy-snapshot-15bf186.json](policy-snapshot-15bf186.json), the unmodified snapshot bytes. The generator imports `standard_workflow.select_protocol` from the snapshot and reads worker-local evidence, so it does not rerun on this tree. `explainer-edits.json` records the hand edit of `explainer.json` after `15bf186`. The frozen protocol limitation text still says "no publication"; [AGENTS.md](../../../AGENTS.md#report-publication) is the delivery rule.
