# Residency-aware xswap swap-in — 2026-10-23

Status: IN PROGRESS. Recovered Claude Code's interrupted H1 and the owner's
explicit authorization to execute H1/H2 after the descriptor-lifetime repair.
No performance conclusion exists yet.

| Contract | Value |
|---|---|
| Fixed baseline | `5e84ca928deeacb4eee656806a003f27d1eca82f` |
| H1 | physical-residency filtered readahead, `e401f1314d81d3990de62af0ba37fc5df79193f6` |
| H2 | compressed-residency filtered ordinary-cache prefetch, pending |
| Primary | sequential first-touch mean latency on disk and zswap, separately |
| Guards | sequential p99; random mean and p99; data/COW/concurrency/live swapoff/no warnings |
| Budget | 160 guests, eight full kernel builds, ten hours; two architecture candidates |
| Acceptance | bounded discovery; no automatic promotion or publication |

The [resume contract](resume-contract.json) and
[protocol](../../benchmark/swap-standard/protocol-xswap-swapin-2026-10-23.json)
preserve the expired preparation contract. Both hypotheses remain independently
based on the repaired baseline.

## Prerequisite evidence

The [independent lifetime review](lifetime-review.md) found no supported
remaining blocking descriptor-lifetime defect (medium confidence). Seven
completed retained stress runs pass; an earlier two-round debug attempt failed
the workload-duration/data gate and remains retained. The unfixed baseline also
passes, so there is no runtime reproducer. Exact run hashes and counts are in
[lifetime-prerequisite.json](lifetime-prerequisite.json). A diagnostic-set sparse
comparison retained a tool error; it is not a successful full sparse run.

H1 has a [source review](h1-review.md) and passes the controller's scope,
diff-check and checkpatch gates. Runtime and performance evidence will be added
when measured.

## Limitations

The probe includes cache effects and uses 4 KiB pages. Large-folio behavior,
fault injection, KCSAN and broad application throughput are outside the bounded
comparison. H2 tests ordinary cache prefetch; no batched decompressor API is
claimed. Review artifacts and all rejected or incomplete attempts are retained.
