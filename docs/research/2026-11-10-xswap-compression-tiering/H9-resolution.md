# H9 independent resolution review

**Disposition: PRELIM-C1-001 is resolved at `2ace421b26361c4f80d149e0a93519eacc30348b`. H8's configuration/catalog change is suitable for the separately frozen replacement contract. Actual replacement-budget enforcement and runtime coverage remain separate review steps.**

Reviewer: `final_independent_review`, independent of implementation. Native replay snapshot: 2026-11-10 20:54:12 UTC. The inspected trusted files are byte-identical to HEAD; there were no uncommitted changes to them.

## Exact revisions and finding resolution

| Change | Inspected revision |
|---|---|
| Versioned debug input and parser/catalog support | `84f9c9c829523ec95510c6e0fa5335efe1d50e01` |
| Required configured-build failure guard | `2ace421b26361c4f80d149e0a93519eacc30348b` |

[PRELIM-C1-001](FINAL-REVIEW-PRELIMINARY.md) identified that required guest-configuration build failures were omitted from matrix progress, leaving the failed C1 contract pending.

**Resolution confidence: high.** `evolve/control/correctness_proof.py:493` now builds the required exact source/configuration set from both guest cases and disabled build-only cases. Any matching `build-coverage` outcome other than `BUILD_VERIFIED` raises an infrastructure/provenance error. Both partial progress (line 623) and final matrix validation (line 521) call this check. A failed build for a different source does not match the set.

I independently replayed the native `matrix_progress()` against the original frozen protocol, actual retained ledger, and exact K1 commit. It returned:

```json
{
  "attempted": true,
  "failed": false,
  "passed": false,
  "pending": false,
  "reason": "required configured build failed or incomplete: c-debug (BUILD_FAILED)"
}
```

The original counted failure now stops progression. It remains an infrastructure coverage failure, without attributing a runtime correctness defect to the unbooted candidate. The added fixture cases cover failed/running/blocked guest-config builds, a failed required build hidden alongside a complete matrix, and exclusion of a different source's failed build. A future native replay that returns pending or pass for this retained failure would reopen PRELIM-C1-001.

## H8 scope and strictness

**Configuration-change confidence: high.** The new `benchmark/config/compression-debug-v2.config` is exactly the old input with the single line `CONFIG_SLUB_TINY=y` replaced by `# CONFIG_SLUB_TINY is not set`. Its SHA-256 is:

`df562dced5dce4462aa061ea25698ba3a2400e9bfcc078961a2e35a89c2905ee`

The old input still hashes to `c58461570b79210f9d99c7eb2e3a6e492601960ea73394bb4e4c78b147cd0ba4`.

`benchmark/swap-standard/configurations.py:54–56` copies every old debug requirement, keeps the purpose correctness-only, and additionally forbids SLUB_TINY. KASAN, lockdep, fault injection, NUMA/hotplug, KUnit, and tracing requirements remain intact.

The exact variant resolver at `configurations.py:181` permits `c1-debug-v2` only for `debug-failures` and `numa-lifecycle`. Read-only native calls confirmed acceptance for these two groups and rejection for the other five groups. An in-memory protocol using the new exact pin validated the same eight-case matrix. This was catalog validation, not a frozen new protocol or executed coverage.

`benchmark/swap-standard/evidence.py:548` uses the same resolver and still compares the expected case, executed configuration ID, backend, mode, workload, and topology. Its numeric topology requirement remains unchanged: debug-v2 cannot use the non-NUMA `flat` observation.

No guest image source changed in these commits. I compared `guest-init`, `bench.sh`, `compression.c`, and `swapin.c` with `13c3195`; their bytes are unchanged. Host parser/catalog identities changed, so older raw runtime evidence retains its original archive and identity rather than being relabeled as new evidence.

## Retention and closeout checks

- Original policy and protocol still match `7abfe80`; all six original input configurations match their frozen hashes.
- All three raw guest result hashes match the preliminary review.
- Original budget remains `created=1794340417.3836553`, `probe_guests=3`, `guests=0`, `builds=3`.
- Original campaign and candidate are closed. `ledger/session-closeout.json` records completed `close-candidate` and `close-campaign` commands with exit code 0 and the infrastructure-incomplete rationale.
- The machine claim file is absent at the read-only check.
- K1 remains commit `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, tree `8b085adc109e3b5467c3de998f11b04517f052a5`.

The [replacement budget contract](C1-replacement-contract.json) remains capped at 29 probe guests, 88 fast guests, and seven new builds, with absolute deadline `1794405217.3836553` (2026-11-11 13:53:37.383655 UTC). The actual new campaign's frozen inputs, initialized budget, native admission, and unchanged baseline-build reuse must be checked before its first counted execution.

## Limitations

This resolves the named planner finding and reviews H8's input/catalog/parser changes. The coordinator reported 105 passing merged parser/coverage/session tests; I inspected the relevant additions and independently replayed the actual original failure, but did not execute the test suite. No corrected kernel has been built or booted by this reviewer, and no runtime, performance, or final candidate acceptance is granted. All work was read-only over SSH except writing this review. No reviewer process remains running.
