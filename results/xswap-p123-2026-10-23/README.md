# xswap Phase I+II+III campaign — 2026-10-23 (preparation)

Status: PREPARED. No guest has been booted. No A/A or candidate evaluation exists.

## Decided

| Item | Value |
|---|---|
| Reference | Phase I v4 + II v1 + III (`b2beda7f`, tree `187cfe49`), see [patches/xswap-phase3](../../patches/xswap-phase3/README.md) |
| Baseline build | `xswap-p123-ref`, `swap-standard.config`, no instrumentation; image sha256 `9c01fbde…8005`, config sha256 `9652dbf3…006a` |
| Primary metric | swap-in latency (owner decision 2026-10-23) |
| Guardrail | metadata bytes/slot (1 TiB brd), usemem throughput/free latency, Valkey RPS |

## Noise finding carried over

In the [2026-10-22 fast A/A](../swap-standard-evolve-2026-10-22/README.md), usemem-disk
throughput across four runs was 1.64, 1.00, 1.28 and 0.83 GB/s, while pswpout stayed at
1.05–1.07 M pages. The guest did the same swap work; the spread comes from host I/O on the
backing file. Confidence: medium; a disk-backed A/A with matched throughput on a quiet
host page cache would change this. Swap-in and Valkey-zram were within 7–14%.

## Next steps

1. Owner decision pending: `benchmark/swap-standard/run.py` refuses `--mode xswap`
   because of the descriptor-lifetime finding. Options: measure with the finding
   blocking promotion only; fix the race as candidate 1; or measure with shrink disabled.
2. Protocol revision: score usemem on zswap (the xswap backend) instead of disk; keep
   disk as a guardrail with more pairs. New A/A for every protocol revision.
3. Write `evolve/control/campaigns/xswap-p123-2026-10-23/policy.json` (seed `b2beda7f`)
   and the protocol; then A/A calibration on the swap-in probe in xswap mode.
4. Phase III mechanisms worth a hypothesis: the charge-on-backend path and the
   cluster-lock retake removal (patch 05) sit on the fault and free paths.
