# xswap suite

Boots the imported xswap reference (Phase I v4 + Phase II v1, `37de636c`) and
controller-checked candidates built on it, using the same config. No candidate
code runs on the host.

## Guest

- 4 GiB RAM, two vCPUs, a private 8 GiB virtio disk, no network, no host
  mounts, 600 s timeout.
- `guest-init` enables zswap and creates the xswap device through
  `/sys/kernel/mm/xswap/create` with priority 32767 and `xswap.max=8G`,
  then checks that exactly one `/sys/kernel/debug/xswap/typeN` exists.
  Creation requires zswap. The disk backend disables zswap after creation,
  before counters and workload start, and the run must then show disk I/O
  with zero zswap activity.

## Workload (`workload.c`)

1. Fill 64 MiB: eight page-distinct 64-bit values repeated per page, so zswap
   compresses it. Then `MADV_PAGEOUT`.
2. Run `usemem -O 5G` from the trusted rootfs template.
3. Fork 48 children. Each checks and COW-writes one page.
4. Time the first access to every parent PTE that is still swapped, in
   shuffled order. Every sampled PTE must carry the xswap type. At least
   1,000 samples are required; a run normally gets 16,384.
5. Verify every parent word. Page the data out again, destroy xswap with live
   PTEs, verify; swapoff the disk, verify.

The debugfs counters are snapshotted six times: before, after pressure,
fork shared, after children, after reads, and after a 2 s settle.

## Metrics

| Metric | Meaning |
|---|---|
| `mapped_clusters_after_settle` | mapped `cluster_info` clusters at the end; primary |
| `sampled_mapped_clusters_max` | maximum over the six snapshots; misses the peak during `usemem` |
| `swapped_first_access_p99_us` | p99 first access, including swap-cache and readahead hits |
| `workload_wall_seconds` | workload elapsed time |
| `grows_after_settle`, `shrinks_after_settle` | xswap grow/shrink counters |

The discovery score is the minimum across backends of baseline/candidate
settled clusters, multiplied by `min(1, worst-backend p99 ratio)`.
It only sorts candidates. In the 2026-10-21 campaign, the primary metric
was decided by whether one tail shrink succeeded during `usemem`; see
[DESIGN.md](../../DESIGN.md#what-the-first-campaign-showed).
Read the snapshots, not the score.

## Running

```sh
python3 prepare-rootfs.py --rootfs-template /absolute/trusted/template
python3 run.py --build xswap-reference --backend disk     # single smoke boot
evolve/.venv/bin/python evolve/loop.py xswap calibrate    # A/A, from repo root
evolve/.venv/bin/python evolve/loop.py xswap evaluate --candidate NAME
```

`evaluate` requires an A/A calibration report whose suite hashes match the
current files. It then runs AB/BA on both backends. The runner refuses to
start if the image, config, initramfs or source provenance has changed, and
it keeps the serial log, disk, command, hashes, counters and gates of every run.

The campaign is bounded by `protocol.json`: three candidates, at most 48
guest launches, and a fixed UTC deadline. `evolve/control/state/STOP` or
`evolve/control/state/<campaign>/STOP` halts it. The 2026-10-21 deadline
has passed; a new campaign needs its own protocol and fresh calibration.

Parser tests: `python3 -m unittest -v` in this directory. They use synthetic
fixtures, plus a real disk run when `XSWAP_EVIDENCE_FIXTURE` is set.
