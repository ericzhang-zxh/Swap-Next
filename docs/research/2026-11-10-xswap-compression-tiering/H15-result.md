# H15 result: socket-aligned auxiliary NUMA topology

Disposition: ready for independent review and coordinator integration. The patch adds a separately identified correctness topology; runtime validation remains pending.

Implementation commit: `4510de0ef81ab307d62740650bfe6e457a6089a3` on `infra/c1-numa-sockets-01a1c6b6`, based on `6f3f59219a3e4c709097713794c18bac5ec2b452`. The isolated worktree is `worktrees/framework-c1-numa-sockets-01a1c6b6`. Exactly the five assigned files changed: `benchmark/swap-standard/{configurations.py,run.py,evidence.py,test_compression_evidence.py,test_runner.py}`. No candidate source changed.

## Contract

- New ID: `numa2-sockets-v2`. It resolves only for `numa-lifecycle` with `c1-debug-v2`, under the existing four-vCPU / 4096-MiB correctness resource bound.
- The runner emits exactly one `-smp 4,sockets=2,cores=2,threads=1`. The two existing 2048-MiB memory objects and node CPU assignments remain exact: node 0 gets CPUs 0-1; node 1 gets CPUs 2-3.
- Native topology proof binds the new ID/config/group, full SMP value, memory size, exact object/NUMA options, and frozen CPU/machine arguments. Missing, duplicate, conflicting, inline/alias and fake CPU-topology arguments fail. Timing and other correctness groups reject the new ID.
- Evidence requires `ONLINE_NODES 0-1` and real KUnit placements on both nodes `{0, 1}`. One-node fallback, flat observations, mismatched placement and the original kernel warning remain failures.
- Legacy `single` and `numa2` arguments and catalog defaults are preserved. No frozen protocol, budget, reservation, raw result or prior failed outcome was edited.

## Source rationale

Confidence is high for the CPU-to-node construction. The installed binary reports QEMU 8.2.2. Official [QEMU invocation documentation](https://www.qemu.org/docs/master/system/invocation.html) defines sockets/cores/threads and explains that bare SMP counts prefer cores over sockets since 6.2. It also defines NUMA `cpus` as contiguous CPU indexes. With two cores per socket and one thread per core, [QEMU v8.2.2 topology code](https://github.com/qemu/qemu/blob/v8.2.2/include/hw/i386/topology.h#L116-L126) maps indexes 0-1 to package 0 and 2-3 to package 1.

At pinned kernel `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`, `arch/x86/kernel/smpboot.c:324-332` warns when sibling CPUs occupy different NUMA nodes; `match_llc()` calls that check after matching LLC IDs. These sources support the explicit socket correction. A fresh counted boot with the unchanged warning gate is the observation that will confirm or reject its runtime effectiveness.

The existing `guest-init` passes through the topology ID and requires actual node sysfs for every non-single ID. Its shell-function test accepts the new ID with `0-1` and rejects missing node sysfs. No guest-image change is needed: the modified files are outside `prepare-image.py`'s guest-source list. Preserved guest-init SHA-256: `feabf7576c5c49c5b2a917569577f115f81d2d77b39b9404c7ef76ebdb5ff168`.

## Verification

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s benchmark/swap-standard -p test_compression_evidence.py -v` | 41 passed |
| `python3 -m unittest discover -s benchmark/swap-standard -p test_runner.py -v` | 28 passed; one pre-existing test skipped because this isolated framework worktree has no Linux checkout |
| `python3 -m unittest evolve.test_compression_coverage -v` | 47 passed |
| `git diff --check` | Passed |
| Changed-path check | Exactly the five authorized implementation/test files |

The fixtures cover valid new and unchanged legacy layouts; exact group/config/resource scope; frozen protocol mismatch; full SMP binding; duplicate and noncanonical CPU/NUMA options; fake CPU properties; one-node placement; actual guest node-marker handling; reservation identity; and warning-gate retention. All checks ran on the designated Linux worker. No kernel build or VM was launched.

## Preserved work and handoff

R3's frozen protocol remains SHA-256 `d454195000ec05241c2c3a325060abed3960360723163b8ed2ed0038f9b77edf`. The existing H13 draft `C2-validation-contract.md` remains SHA-256 `2f0494cd12ea2bb78f62661849e92da805e088acb7dd340c9898bf96b34248f1` and is on hold.

The coordinator owns H16 review, integration, a separately frozen continuation using the remaining original-phase resources/deadline, and any counted runtime attempt. This patch does not reopen R3 or rescore its failed run. No worker process remains running.
