# Benchmark suites and settings

This directory owns isolated kernel builds, KVM runners, guest workloads,
parsers, evaluators, frozen discovery protocols, kernel configurations, and
evidence tests. [Evolve](../evolve/README.md) owns OpenEvolve loop adapters and
its dependency pin. [control](../evolve/control/README.md) owns candidate admission,
scope, campaign policy, and formal acceptance.

Start with [settings.json](settings.json), the auditable settings inventory,
then [setup](SETUP.md), [kernel protocol](kernel/protocol.json), and
[xswap details](xswap/README.md). Settings are **recorded constants**, not
runtime overrides: source files and protocol JSON remain authoritative.
The inventory hashes their complete contents so any drift requires review.
Run `python3 benchmark/validate_settings.py` after any suite change.
The manifest is never consumed by evaluators; it cannot silently override the
frozen suite or weaken attestation. Formal system policy budgets are separate
from discovery settings (for example its 16 GiB disk budget is not the pilot's
8 GiB disk size).

## What is measured

Both suites use a 64 MiB anonymous target, deterministic shuffled page order,
MADV_PAGEOUT, and a separately supplied usemem -O 5G pressure program.
They time first access to swapped parent PTEs; swap cache, readahead, child
accesses, scheduling, and timer cost remain included. These are not isolated
disk service times. Parent data is checked in full; xswap children check one
page each after COW. The xswap pattern repeats eight page-distinct words;
the kernel pattern differs per word. The workloads are not interchangeable.

Kernel metadata is selected requested allocation bytes, not total physical
RAM. Xswap reports mapped clusters, not RAM bytes; its six snapshots yield a
sampled maximum, not a continuous peak. Settled counts and A/A observations
can vary substantially between boots. Pressure behavior depends on the
trusted template's usemem executable and remains an external input.

| Coverage | Kernel discovery | Xswap discovery | Formal acceptance |
|---|---|---|---|
| Anonymous disk and zswap, roundtrip, fork/COW, live swapoff | Implemented pilot | Implemented pilot plus live xswap destruction | Broader contract still required |
| Metadata | Selected requested bytes | Mapped clusters and growth/shrink counters | Complete RAM accounting missing |
| AB/BA and A/A | Two pairs/backend; no A/A | AB/BA; A/A required before candidate evaluation | Ten pairs, calibration and uncertainty required |
| Fragmentation and multiple physical devices | Missing | Missing | Required future coverage |
| Mixed file and anonymous memory, oscillating pressure | Missing | Missing | Required future coverage |
| Memcg, large folios, allocation/I/O fault injection | Missing | Missing | Required gates |
| Lockdep, KASAN, KCSAN | Missing | Missing | Required gates |
| Independent confirmation and holdout | Missing | Missing | Required before promotion |

Discovery scores sort hypotheses only. A passing pilot is not correctness
certification or statistical acceptance. Formal acceptance remains disabled in
evolve/control/config/policy.json, with missing gates and thresholds fail-closed.
No promotion is automatic.

## Layout migration and evidence

| Previous tracked location | Active location |
|---|---|
| Evolve/kernel except loop.py | benchmark/kernel |
| Evolve/xswap except loop.py | benchmark/xswap |
| config kernel configurations | benchmark/config |
| Evolve/*/loop.py | evolve/*/loop.py |

New builds, rootfs, initrds, runs, and evaluations live beneath benchmark.
Search database, ledger, RNG and task briefs live under evolve/<suite>/state-layout-v1.
The xswap calibration report lives under benchmark/xswap/state-layout-v1;
the xswap attempt ledger uses state-runtime-layout-v1. The common build/run
lock is benchmark/kernel/.runtime.lock. Old ignored Evolve runtime remains
archived in place and is never automatically imported. Historical result
documents and hashes retain their original paths and meaning.

Relocated harness hashes differ, so historical calibration is not valid new
evidence. Prepare fresh baseline/initrd/calibration only under an explicitly
authorized campaign. The xswap deadline remains exactly frozen; no new budget
or deadline is granted by relocation. Historical raw logs may be read for
parser regression tests; that proves neither a fresh boot nor fresh calibration.

## Checks

```sh
python3 benchmark/validate_settings.py
python3 -m unittest discover -s benchmark/tests -v
python3 -m unittest discover -s benchmark/kernel -p 'test_*.py' -v
python3 -m unittest discover -s benchmark/xswap -p 'test_*.py' -v
python3 -m unittest discover -s evolve/control/tests -v
```

Kernel and xswap fixture tests require SWAP_NEXT_EVIDENCE_FIXTURE and
XSWAP_EVIDENCE_FIXTURE respectively, pointing to real retained disk results.
Missing fixtures are explicit skips. No build or guest run is implied by these checks.
