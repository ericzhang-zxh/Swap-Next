# xswap continuation: 2026-10-24

Status: complete. Three candidates screened out; none eligible for slow confirmation or promotion. All experiment processes have stopped.

[Visual review](explainer.html) | [Full report](REPORT.md) | [Machine-readable summary](summary.json) | [Evidence audit](evidence-audit.json)

| Round | Candidate | Result |
|---|---|---|
| 1 | VMA-only sequential admission | No physical prefetch; disk tail guards fail |
| 2 | Linearize split compressed inputs | Compressed sequential mean +24.4%; all compressed guards fail |
| 3 | Adjacency admission in both modes | Disk sequential mean -40.2%; random p99 +29.5%, guard fails |

These are two-pair fast observations. Source/counter evidence supports activation of round 3's physical prefetch path. Confidence in general performance attribution remains limited by between-run variation; independent profiling or confirmation could change it.

48 KVM guests completed with integration gates passing, including eight targeted correctness/debug guests. Six builds passed. Two candidates have exact-commit targeted KASAN/lockdep coverage; the last also passed a CONFIG_SWAP=n build. The independent audit checks 48 result/log hashes, candidate identities, all 24 paired metric ratios, the P123 baseline ancestry and the shared budget.

## Next

Investigate variance and demand-first speculative I/O before further optimization. Preserve the rejected patches and raw measurements. No candidate qualifies for the slow tier under the current policy.

## Limitations

The first sparse-image A/A failed its noise gate. Preallocation revision 2 passed, with the initial failure retained. Full promotion still requires missing policy gates and independent evidence; see REPORT.md. No code was promoted or published. The KASAN configurations retain the same pre-existing vma.c frame-size warning and config overrides as their baseline; no new build diagnostics were found.
