# xswap continuation: 2026-10-24

Status: preparing fresh A/A fast calibration on repaired xswap baseline `5e84ca92`.

The owner authorized several overnight xswap experiments. The controller keeps three candidates, 48 total guest attempts, 10 builds and six hours as hard ceilings. Slow confirmation and promotion remain disabled.

## First hypothesis

Use adjacent virtual fault addresses to admit physical readahead, while discontinuous accesses retain synchronous single-folio swap-in. This tests whether prior physical readahead throughput can survive random-tail guards.

## Limitations

Fast discovery only. Full promotion gates, independent confirmation and holdout remain required. Prior failed candidates and unrelated untracked confirmation work are preserved.
