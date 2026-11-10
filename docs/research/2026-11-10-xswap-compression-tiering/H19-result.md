# H19: versioned Intel NUMA correctness topology

Status: implementation and guest-free verification complete; independent H22 review and coordinator integration/runtime remain separate.

Implementation commit: 92b221bcb32b9fad1182547736a97c20d1d560cd.
Base: dd23123a98b667b95c07c483afe9dd56345b98c7.
Branch: infra/c1-numa-intel-01a1c6b6.
Author: Eric Zhang <zxh@xh-zhang.com>. No Signed-off-by was added.

Authoritative scope: [tickets/H19.json](tickets/H19.json). CPU rationale and preserved R4 outcome: [H18-clocksource-validity-review.md](H18-clocksource-validity-review.md).

## Result

The new numa2-nehalem-v3 topology resolves only for c1-debug-v2 / numa-lifecycle compression correctness. It derives one effective CPU option, Nehalem-v1,vme=off,enforce=on, while retaining four vCPUs, 4096 MiB, 4,sockets=2,cores=2,threads=1, two 2048-MiB objects and the existing CPU0-1/node0 and CPU2-3/node1 mappings. The runner uses the effective accelerator vector in both the QEMU command and qemu_accel record. The base protocol's max CPU and every older topology command retain their existing behavior.

The catalog binds the new command to the complete CPU string, SMP, memory objects, node assignments, machine and accelerator. It rejects duplicate/alternate option spellings, conflicting records, machine aliases and alternate CPU/device configuration channels. Native correctness_proof already calls this catalog validation; no workflow or proof implementation change was needed.

For the new topology only, configuration_identity requires one actual Intel CPU0 family 6/model 26/stepping 3 observation inside one retained kernel-log block. The parser matches the numeric fields and Intel vendor prefix, not a model-brand sentence. It still requires both observed online nodes, both actual library allocation nodes, hotplug and reset. Existing warnings, sanitizer diagnostics and clocksource fallback remain blocking.

## Verification

All checks ran on the Linux worker in the isolated worktree. No compiler, kernel build or QEMU guest was launched.

| Check | Result |
| --- | --- |
| python3 -m unittest discover -s benchmark/swap-standard -q | 171 tests passed, 1 existing missing-linux-checkout skip |
| evolve/.venv/bin/python -m unittest evolve.test_compression_coverage -q | 49 tests passed |
| git diff --check | Passed |
| Worktree after commit | Clean |
| Files changed | Six authorized files; no conditional-scope implementation files |

The standard suite includes:
- Canonical new and retained commands; exact config/group/resource scope and timing rejection.
- A mocked pre-launch runner execution that captures started.json and the command supplied to Popen, checks the same effective accelerator in both, and stops before QEMU.
- Wrong/missing CPU model, missing flags, duplicate or aliased CPU/SMP/memory/machine/node/accelerator options, and mismatched recorded accelerator.
- Missing, wrong-vendor, wrong-number, malformed, duplicate and outside-kernel-log CPU0 observations; alternate Intel brand prose remains valid.
- Real-node placement, hotplug/reset, warning, KASAN/KCSAN and clocksource-marker rejection. Existing guest-init accepts the new topology's actual node observation without image changes.

The native coverage fixture proves that a complete eight-row/two-disabled-build matrix reaches the real catalog validator and that command/record/group mutations fail there. Its runtime observations are synthetic; separate parser fixtures verify the CPU-log behavior. These tests establish harness admission and rejection, not a successful real guest.

Exact changed files:
- benchmark/swap-standard/configurations.py
- benchmark/swap-standard/run.py
- benchmark/swap-standard/evidence.py
- benchmark/swap-standard/test_compression_evidence.py
- benchmark/swap-standard/test_runner.py
- evolve/test_compression_coverage.py

## Limitations and handoff

Confidence is high in the tested command identity and native proof path. The selected CPU has not booted under this harness; the first fresh counted NUMA guest must still establish actual CPU identity, both NUMA placements, hotplug, unchanged warning/clocksource/sanitizer gates and complete reset.

No Linux source, configuration input, guest image, validity.py, frozen protocol, budget, raw result or campaign state was changed. Nothing remains running from H19. H22 and the coordinator were notified of the exact implementation commit.
