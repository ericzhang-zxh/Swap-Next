# Separate xswap pilot harness

This isolated harness is not the legacy swap metadata evaluator. It requires a
controller-reviewed Phase I/II xswap build in the main project's
benchmark/kernel/builds directory, with instrument_sha256 explicitly null.
No candidate source executes on the host through this runner.

Prepare the guest only with an explicitly selected trusted template:

    python3 prepare-rootfs.py --rootfs-template /absolute/trusted/template
    python3 run.py --build xswap-reference --backend disk
    python3 run.py --build xswap-reference --backend zswap

These commands are documentation, not evidence that packaging or runs occurred.
The runner refuses changed image/config hashes, missing required configuration,
legacy instrumentation, and stale initramfs/source provenance. It retains raw
serial logs, a private sparse disk, command and hashes, counters, gates, and
results. The copied parent-death preexec hook is identical to the reference.

Each guest has 4 GiB RAM, two vCPUs, an 8 GiB private virtio disk, no network,
no writable host mounts, and a 600-second timeout. Global system/state/STOP and
system/state/xswap-2026-10-21/STOP stop execution. A frozen UTC deadline and a shared attempt ledger bound the campaign to at most 48 guest launches. The runner never needs host root, host
swap, raw host devices, or host reboot.

Guest control paths were checked in Phase I/II mm/swapfile.c: sysfs
/sys/kernel/mm/xswap/{create,destroy}, debugfs /sys/kernel/debug/xswap/typeN.
Create uses priority 32767 after enabling the physical disk, and xswap.max=8G.
Exactly one debugfs type is required. Creation requires zswap enabled; the disk case disables it after creation and before counters/workload, and verifies disk IO with zero zswap activity.

The workload holds 64 MiB, pages it out, runs usemem -O 5G, forks 48 children,
checks one page per child with COW, and checks every parent word. Compared with
the old pilot, data now repeats eight page-distinct 64-bit values in each page:
this intentionally enables the same deterministic dataset for disk and zswap.
It remains fully checked, including after destroying xswap with live swapped
PTEs and after physical swapoff. Every timed swapped-PTE access must name the
selected xswap type. At least 1,000 timed accesses are mandatory.

Metrics report mapped cluster counts, never fabricated RAM byte estimates:
mapped_clusters_after_settle is primary, sampled_mapped_clusters_max is only
the maximum observed across six snapshots, not a true temporal peak.
swapped_first_access_p99_us, workload_wall_seconds and whole-guest wall_seconds
expose latency and elapsed cost. Raw grows/shrinks and usage remain evidence.
A lack of observed shrink is not fabricated into success or optimization.

Caveats: child reads can warm shared swap cache; a swapped parent PTE does not
prove a disk-major fault. Snapshots are not atomic across different phases,
and mapped clusters do not measure all allocator overhead. usemem runtime and
its allocation pattern depend on the explicitly supplied template. This is a
pilot, not full correctness acceptance, calibrated performance acceptance, or
permission to promote. Runtime behavior and sufficient samples still need
separate smoke verification.

Run parser tests with python3 -m unittest -v. Test fixtures are synthetic;
passing parser tests is not kernel runtime evidence.

Primary review limits each child integrity scan to one page; the parent verifies every target byte. This avoids warming the entire target before the timed readback. Swap-cache and readahead effects remain part of the measured first access.

## Frozen discovery loop

Run evolve/xswap/loop.py calibrate from the repository root with the pinned OpenEvolve Python environment before
evaluating a candidate. The evaluator requires that successful A/A report to
match the frozen suite hashes. evolve/xswap/loop.py evaluate --candidate NAME builds an
immutable controller candidate and collects fresh AB/BA guest pairs on both
backends. evolve/xswap/loop.py next selects references and returns feedback; the active
assistant proposes the next change. There is no unattended model worker or
automatic promotion. All patches still use the same imported seed.

The sorting score is settled-cluster ratio with a one-sided latency penalty.
It is not statistical acceptance. The initial A/A experiment exposed large,
bimodal mapped-cluster variation and substantial per-boot latency noise; its
aggregate score hides that variation. Inspect every run, shrink counters and
raw state. Do not interpret a high score alone as an optimization result.

After the dated deadline, a new controller-approved campaign and recalibration
are required. Do not edit a running campaign's protocol or suite.
