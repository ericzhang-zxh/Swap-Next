# Benchmark suites

This directory owns isolated kernel builds, the KVM runner, guest workloads,
parsers, evaluators and frozen protocols. [evolve](../evolve/README.md) owns
the search adapter, and [control](../evolve/control/README.md) owns candidate
scope and acceptance policy.

Read [SETUP.md](SETUP.md) to prepare a worker. Each suite's `protocol.json`
holds its baseline, backends, run order, budget and the gates it does not yet
implement. The evaluator hashes every suite file and refuses to run if any
of them change during a campaign.

| Suite | Baseline | Primary metric | Calibration |
|---|---|---|---|
| [kernel](kernel/protocol.json) | upstream `744e5400` | requested metadata bytes, first-access p99 | none |
| [xswap](xswap/README.md) | xswap Phase I/II reference `37de636c` | retained mapped clusters, first-access p99 | A/A required |

## Workload

Both suites:

- fill a 64 MiB anonymous target and page it out with `MADV_PAGEOUT`;
- apply pressure with `usemem -O 5G` in a 4 GiB, two-vCPU guest;
- fork 48 children to exercise COW;
- time the first access to every still-swapped parent PTE in shuffled order;
- verify every parent word, including after swapoff (and, for xswap, after live
  destroy).

The data patterns differ:

- kernel: a unique value per word;
- xswap: eight page-distinct words repeated, so that zswap compresses it.

Because of this, numbers from the two suites cannot be compared.

## Checks

```sh
python3 -m unittest discover -s benchmark/tests -v
python3 -m unittest discover -s benchmark/kernel -p 'test_*.py' -v
python3 -m unittest discover -s benchmark/xswap -p 'test_*.py' -v
```

The fixture-based tests need `SWAP_NEXT_EVIDENCE_FIXTURE` (kernel) or
`XSWAP_EVIDENCE_FIXTURE` (xswap) pointing at a retained disk run, and skip
without it. These checks exercise parsers and layout only. They do not boot
a kernel.

## Limitations

See [DESIGN.md § Limitations](../DESIGN.md#limitations).
