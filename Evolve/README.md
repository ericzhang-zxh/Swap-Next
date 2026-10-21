# OpenEvolve kernel pilot adapter

This directory connects controller-approved kernel patches to an isolated build,
KVM guest measurements, retained evidence, and OpenEvolve's program database.
It is a pilot, not a performance acceptance system. **The relocated public layout
has not yet been compiled or booted in a fresh KVM run.** No historical build
manifests, guest evidence, database, binaries, or runtime state are bundled.

The current conversation's assistant proposes changes. There is no automatic
model worker, background search service, or automatic merge. OpenEvolve stores
programs and feedback and selects references; it does not certify correctness.

## Layout and trust

All paths derive from this checkout, with no sibling private repositories:

- `../linux/`: upstream Linux submodule and Git objects used for snapshots.
- `../system/controller.py`: candidate scope/static checks.
- `../system/state/`: controller state, including the `STOP` sentinel.
- `../config/kernel.config`: shared baseline/candidate configuration.
- `kernel/`: trusted evaluator, workload, overlay, build and guest runners.

The frozen public baseline is upstream commit
`744e5400b36f84b4816e3ff8531ec2dff52b474c`. Candidate patches must be based on
that seed and admitted by the controller. The same immutable instrumentation
script is applied to baseline and candidate snapshots; evaluator provenance
checks bind source, image, config, instrumentation, rootfs, and raw evidence.
Do not edit the evaluator, workload, or thresholds to improve a candidate score.

Builds use Linux user/mount/PID/network namespaces, read-only toolchain/source
mounts, dropped capabilities, and bounded runtime/output. This shares the host
kernel and does not isolate a same-user proposer from the controller. Limits
include per-process address space and a monitored output budget, not aggregate
cgroup quotas. The namespace launcher currently expects a Debian/Ubuntu-style
x86-64 toolchain layout, including Python 3.12 paths. Guest execution requires
Linux KVM access and QEMU. Do not run these kernel tasks on a non-Linux controller.

## Prepare a fresh environment

Use a dedicated Linux environment with Git, Python, GCC/static libc development
files, kernel build dependencies, util-linux (`unshare`, `setpriv`, `prlimit`),
GNU core utilities, cpio, gzip, and `qemu-system-x86_64`.
`requirements.snapshot.txt` records pinned Python dependencies and the public
OpenEvolve Git revision; fresh installation of this snapshot is not verified here.

From the superproject root:

```sh
python3 -m venv Evolve/.venv
Evolve/.venv/bin/pip install -r Evolve/requirements.snapshot.txt
python3 Evolve/kernel/build.py \
  --commit 744e5400b36f84b4816e3ff8531ec2dff52b474c \
  --name baseline --config config/kernel.config
python3 Evolve/kernel/prepare-rootfs.py --rootfs-template /path/to/trusted-guest-template
```

A new baseline build and initrd are required before any evaluation. Existing
output names are not overwritten. Creating the initrd compiles the trusted
userspace workload; it does not build or boot a kernel.

The explicit rootfs template must be a **trusted guest-only directory** containing:

- `/bin/sh` and utilities `mount`, `cat`, `grep`, `uname`, `mkswap`, `swapon`,
  `wc`, `dmesg`, and `poweroff`, available under `/bin` (BusyBox applets work).
- `/bin/usemem` from vm-scalability, supporting `-O 5G`. The original pilot used
  upstream vm-scalability commit `b3c2ded99b52ff92cafc408e407a6e1b22c96487`.
- Any ELF interpreter/shared libraries required by those executables at their
  guest absolute paths, or statically linked binaries.

The preparer creates mountpoint directories and writes its own `/init` and
`/bin/kernel-workload`. It does not download or bundle third-party binaries.
Do not point it at a host root filesystem or a directory containing credentials.
Presence checks do not establish executable compatibility; a real guest run is
needed. Templates and generated binaries remain local artifacts.

## Run the bounded loop

After creating and committing a candidate through `system/controller.py` from the superproject root:

```sh
Evolve/.venv/bin/python Evolve/kernel/loop.py evaluate --candidate example-candidate
Evolve/.venv/bin/python Evolve/kernel/loop.py status
Evolve/.venv/bin/python Evolve/kernel/loop.py next
```

`next` writes a proposal brief; it does not start a model. Evaluation runs fresh
AB/BA boots for disk and zswap, preserves failures, verifies input identities,
and stores measured feedback. Candidate and run budgets remain in
`kernel/protocol.json`. `touch system/state/STOP` requests the existing stop
checks; an active runner monitors the sentinel. No process launches are implied
by merely reading or selecting references.

The score is a discovery sorting value derived from mean per-run p99 values,
not pooled p99, statistical significance, or permission to promote. The
first-access metric includes cache/readahead, scheduling, and timer overhead.
Metadata counts selected cluster/table requested bytes, not complete swap
metadata or physical RAM. Fork-exit timing includes child accesses and scheduling.
The protocol lists missing acceptance gates, calibration, confirmation, and
holdout work; successful smoke observations do not satisfy these requirements.

## Evidence checks

No historical private fixtures are shipped. Supply a real, completed **disk**
run from this environment, with its referenced `serial.log` still present:

```sh
SWAP_NEXT_EVIDENCE_FIXTURE=/path/to/disk-run/result.json \
  python3 -m unittest discover -s Evolve/kernel -p test_evidence.py -v
```

Without that variable the fixture-dependent test class explicitly skips. A skip
is not a pass, and neither static import checks nor copied code verify relocated
build/KVM behavior. Do not commit raw runtime artifacts without a separate
publication review; they can contain local paths and machine identifiers.
