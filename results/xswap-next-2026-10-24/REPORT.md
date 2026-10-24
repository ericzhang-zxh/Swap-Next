# xswap-next-2026-10-24

Status: CLOSED. Fast discovery only; human promotion remains disabled.

[Visual review](explainer.html) · [Machine-readable summary](summary.json)

## Results

| Candidate | Commit | Evaluation | Correctness passes |
|---|---|---|---|
| xs-ra-sequential-v1 | `7322aadd18b6030c692265693b8dfd29afa3ee6f` | REGRESSION | 2 |
| xs-zswap-linear-v1 | `218750fed80a7ac099d46c5a3a26799a5d185d14` | REGRESSION | 3 |
| xs-ra-cluster-v1 | `25e1feb2b74f8ab30db0816e194294b7a6085a7f` | REGRESSION | 3 |

## Candidate decisions

xs-ra-sequential-v1: REGRESSION in fast report 49add9b084d04941a459281838bbf3f3: disk seq p99 and rand p99 fail. swap_ra=0 in both candidate disk runs; source VMA-only admission is inactive with the rotational guest backend. Keep failed evidence; no causal speed claim, slow run or promotion.

xs-zswap-linear-v1: REJECT_FAST: report 15ded9c2bdf44b5fae1b3e83f0f75daf fails all four compressed latency guards; zswap seq mean +24.39%. Both release correctness backends and targeted KASAN/lockdep correctness pass. Disk-path movement has no matching mechanism and is not credited. Retain evidence, no slow tier or promotion.

xs-ra-cluster-v1: REJECT_FAST: report 9ec21a04b74b4d46a7931c16112a6bdb records useful physical prefetch and disk seq mean -40.19%, but disk random p99 +29.46% and compressed random mean +7.96% fail guards. Targeted KASAN/lockdep, both release correctness backends and CONFIG_SWAP=n build pass. Retain the tradeoff; no slow confirmation or promotion. Two pairs leave causal attribution and between-run variation unresolved.


## Per-workload latency

| Candidate | Metric | Change % | Noise % | Guard |
|---|---|---:|---:|---|
| xs-ra-sequential-v1 | swapin-disk.swapin_seq.mean_ns | +4.54 | 8.09 | PASS |
| xs-ra-sequential-v1 | swapin-disk.swapin_seq.p99_ns | +7.90 | 6.07 | FAIL |
| xs-ra-sequential-v1 | swapin-disk.swapin_rand.mean_ns | -0.46 | 12.24 | PASS |
| xs-ra-sequential-v1 | swapin-disk.swapin_rand.p99_ns | +9.34 | 3.00 | FAIL |
| xs-ra-sequential-v1 | swapin-zswap.swapin_seq.mean_ns | +1.03 | 3.00 | PASS |
| xs-ra-sequential-v1 | swapin-zswap.swapin_seq.p99_ns | +9.49 | 14.46 | PASS |
| xs-ra-sequential-v1 | swapin-zswap.swapin_rand.mean_ns | +0.86 | 3.00 | PASS |
| xs-ra-sequential-v1 | swapin-zswap.swapin_rand.p99_ns | +12.92 | 16.20 | PASS |
| xs-zswap-linear-v1 | swapin-disk.swapin_seq.mean_ns | -7.51 | 8.09 | PASS |
| xs-zswap-linear-v1 | swapin-disk.swapin_seq.p99_ns | -8.96 | 6.07 | PASS |
| xs-zswap-linear-v1 | swapin-disk.swapin_rand.mean_ns | -5.90 | 12.24 | PASS |
| xs-zswap-linear-v1 | swapin-disk.swapin_rand.p99_ns | -3.51 | 3.00 | PASS |
| xs-zswap-linear-v1 | swapin-zswap.swapin_seq.mean_ns | +24.39 | 3.00 | FAIL |
| xs-zswap-linear-v1 | swapin-zswap.swapin_seq.p99_ns | +21.18 | 14.46 | FAIL |
| xs-zswap-linear-v1 | swapin-zswap.swapin_rand.mean_ns | +23.29 | 3.00 | FAIL |
| xs-zswap-linear-v1 | swapin-zswap.swapin_rand.p99_ns | +29.12 | 16.20 | FAIL |
| xs-ra-cluster-v1 | swapin-disk.swapin_seq.mean_ns | -40.19 | 8.09 | PASS |
| xs-ra-cluster-v1 | swapin-disk.swapin_seq.p99_ns | -11.64 | 6.07 | PASS |
| xs-ra-cluster-v1 | swapin-disk.swapin_rand.mean_ns | +5.88 | 12.24 | PASS |
| xs-ra-cluster-v1 | swapin-disk.swapin_rand.p99_ns | +29.46 | 3.00 | FAIL |
| xs-ra-cluster-v1 | swapin-zswap.swapin_seq.mean_ns | -0.23 | 3.00 | PASS |
| xs-ra-cluster-v1 | swapin-zswap.swapin_seq.p99_ns | +0.04 | 14.46 | PASS |
| xs-ra-cluster-v1 | swapin-zswap.swapin_rand.mean_ns | +7.96 | 3.00 | FAIL |
| xs-ra-cluster-v1 | swapin-zswap.swapin_rand.p99_ns | +11.41 | 16.20 | PASS |

## Retained attempts

Reserved guests: 48/48; builds: 6/10. Completed guest results: 48. Running evaluations: 0.

| Action | Candidate | Status | Evidence |
|---|---|---|---|
| calibrate  | baseline | CALIBRATION_NOISY | benchmark/swap-standard/evaluations/7ef0bcb1918d4209954fc4929c7fe379/report.json |
| auxiliary build | xs-ra-sequential-v1 | PASS | benchmark/swap-standard/evaluations/aux-23d5cee4b41548e5b523b6abc2073cd5/report.json |
| auxiliary guest | xs-ra-sequential-v1 | PASS | benchmark/swap-standard/evaluations/aux-1fbd7677659347d1bc96b4668c2237b8/report.json |
| auxiliary guest | xs-ra-sequential-v1 | PASS | benchmark/swap-standard/evaluations/aux-e815bbd1237a45578e743c1c6bcc61b8/report.json |
| calibrate  | baseline | CALIBRATED | benchmark/swap-standard/evaluations/7ac434b0aad649298d7c0282b29a10c1/report.json |
| evaluate  | xs-ra-sequential-v1 | REGRESSION | benchmark/swap-standard/evaluations/49add9b084d04941a459281838bbf3f3/report.json |
| auxiliary build | xs-zswap-linear-v1 | PASS | benchmark/swap-standard/evaluations/aux-435d46c5189d48a3abf342ddf0de4eb9/report.json |
| auxiliary guest | xs-zswap-linear-v1 | PASS | benchmark/swap-standard/evaluations/aux-1c1fcaf0fdf64a09b95d3963eaf7f5f0/report.json |
| auxiliary guest | xs-zswap-linear-v1 | PASS | benchmark/swap-standard/evaluations/aux-e8cdc9dc2daa431092f35c9a1b389772/report.json |
| auxiliary build | xs-zswap-linear-v1 | PASS | benchmark/swap-standard/evaluations/aux-26fdaae6ba9943759dd5c66f6f882089/report.json |
| auxiliary guest | xs-zswap-linear-v1 | PASS | benchmark/swap-standard/evaluations/aux-c6e3aad7af8a4cd7b38edad7b2772b34/report.json |
| evaluate  | xs-zswap-linear-v1 | REGRESSION | benchmark/swap-standard/evaluations/15ded9c2bdf44b5fae1b3e83f0f75daf/report.json |
| auxiliary build | xs-ra-cluster-v1 | PASS | benchmark/swap-standard/evaluations/aux-62524f884b784170b7640a05e264d55a/report.json |
| auxiliary guest | xs-ra-cluster-v1 | PASS | benchmark/swap-standard/evaluations/aux-4e8ff1ac9157410880e59e484b77a80c/report.json |
| auxiliary guest | xs-ra-cluster-v1 | PASS | benchmark/swap-standard/evaluations/aux-8a86fe4e2e2d47b4bb4e4b357598b079/report.json |
| auxiliary build | xs-ra-cluster-v1 | PASS | benchmark/swap-standard/evaluations/aux-922ec26f42894464ad56f0945a625709/report.json |
| auxiliary guest | xs-ra-cluster-v1 | PASS | benchmark/swap-standard/evaluations/aux-a6329e199d1f4657b85b1b5f2b199b37/report.json |
| auxiliary build | xs-ra-cluster-v1 | PASS | benchmark/swap-standard/evaluations/aux-050766084c70401f93d15beab339bcc4/report.json |
| evaluate  | xs-ra-cluster-v1 | REGRESSION | benchmark/swap-standard/evaluations/9ec21a04b74b4d46a7931c16112a6bdb/report.json |

## Confidence and falsifiers

| Finding | Confidence | Observation that changes it |
|---|---|---|
| Reported pass/fail and per-run values match retained evidence | High | Hash mismatch, parser defect or missing result |
| Two-pair effects describe this fast screen | High for these samples; low for generalization | Independent confirmation under the same frozen protocol |
| Source mechanisms explain an observed latency effect | Medium pending profiling | Path counters or targeted profiles contradict the proposed cause |

## Mechanism counters

| Run | Candidate | Backend | swap_ra | swap_ra_hit | pswpin | zswpin |
|---|---|---|---:|---:|---:|---:|
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-disk-a | baseline | disk | 0 | 1 | 262159 | 0 |
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-disk-b | baseline | disk | 0 | 0 | 262163 | 0 |
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-zswap-a | baseline | zswap | 0 | 0 | 0 | 262169 |
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-zswap-b | baseline | zswap | 0 | 0 | 0 | 262160 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-disk-b | baseline | disk | 0 | 1 | 262132 | 0 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-disk-a | baseline | disk | 0 | 0 | 262161 | 0 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-zswap-b | baseline | zswap | 0 | 0 | 0 | 262166 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-zswap-a | baseline | zswap | 0 | 0 | 0 | 262169 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-disk-a | baseline | disk | 0 | 2 | 262152 | 0 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-disk-b | baseline | disk | 0 | 0 | 262152 | 0 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-zswap-a | baseline | zswap | 0 | 0 | 0 | 262160 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-zswap-b | baseline | zswap | 0 | 0 | 0 | 262160 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-disk-b | baseline | disk | 0 | 0 | 262164 | 0 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-disk-a | baseline | disk | 0 | 1 | 262135 | 0 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-zswap-b | baseline | zswap | 0 | 0 | 0 | 262160 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-zswap-a | baseline | zswap | 0 | 0 | 0 | 262160 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-disk-a | xs-ra-sequential-v1 | disk | 0 | 1 | 262159 | 0 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-disk-b | xs-ra-sequential-v1 | disk | 0 | 1 | 262137 | 0 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-zswap-a | xs-ra-sequential-v1 | zswap | 0 | 0 | 0 | 262165 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-zswap-b | xs-ra-sequential-v1 | zswap | 0 | 0 | 0 | 262166 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-disk-b | xs-ra-sequential-v1 | disk | 0 | 0 | 262159 | 0 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-disk-a | xs-ra-sequential-v1 | disk | 0 | 0 | 262177 | 0 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-zswap-b | xs-ra-sequential-v1 | zswap | 0 | 0 | 0 | 262160 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-zswap-a | xs-ra-sequential-v1 | zswap | 0 | 0 | 0 | 262147 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-disk-a | xs-zswap-linear-v1 | disk | 0 | 1 | 262137 | 0 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-disk-b | xs-zswap-linear-v1 | disk | 0 | 0 | 262162 | 0 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-zswap-a | xs-zswap-linear-v1 | zswap | 0 | 0 | 0 | 262160 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-zswap-b | xs-zswap-linear-v1 | zswap | 0 | 0 | 0 | 262161 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-disk-b | xs-zswap-linear-v1 | disk | 0 | 0 | 262137 | 0 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-disk-a | xs-zswap-linear-v1 | disk | 0 | 3 | 262133 | 0 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-zswap-b | xs-zswap-linear-v1 | zswap | 0 | 0 | 0 | 262165 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-zswap-a | xs-zswap-linear-v1 | zswap | 0 | 0 | 0 | 262166 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-disk-a | xs-ra-cluster-v1 | disk | 0 | 0 | 262155 | 0 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-disk-b | xs-ra-cluster-v1 | disk | 32783 | 32778 | 262164 | 0 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-zswap-a | xs-ra-cluster-v1 | zswap | 0 | 0 | 0 | 262159 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-zswap-b | xs-ra-cluster-v1 | zswap | 0 | 0 | 0 | 262160 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-disk-b | xs-ra-cluster-v1 | disk | 65548 | 65544 | 262166 | 0 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-disk-a | xs-ra-cluster-v1 | disk | 0 | 0 | 262164 | 0 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-zswap-b | xs-ra-cluster-v1 | zswap | 0 | 0 | 0 | 262160 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-zswap-a | xs-ra-cluster-v1 | zswap | 0 | 0 | 0 | 262139 |

## Descriptive cost readback

Extracted after scoring from retained raw logs; these values were not admission metrics. CPU spans fill, page-out, faults and verification. The page rate is derived from the timed first-touch phase.

| Run | Candidate | Arm | Backend | System CPU ms | Peak MiB | Seq pages/s | Rand pages/s |
|---|---|---|---|---:|---:|---:|---:|
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-disk-a | A/A | A | disk | 6686.92 | 1031.01 | 6003.81 | 5287.41 |
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-disk-b | A/A | A | disk | 5865.97 | 1031.62 | 6448.49 | 4271.86 |
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-zswap-a | A/A | A | zswap | 10340.95 | 1030.99 | 85648.55 | 73216.66 |
| 7ef0bcb1918d4209954fc4929c7fe379-0-swapin-zswap-b | A/A | A | zswap | 10426.94 | 1031.15 | 84414.07 | 71838.50 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-disk-b | A/A | A | disk | 6350.61 | 1031.37 | 6714.95 | 4447.17 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-disk-a | A/A | A | disk | 6563.04 | 1031.27 | 6892.20 | 4352.06 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-zswap-b | A/A | A | zswap | 10404.68 | 1031.18 | 85050.77 | 73134.21 |
| 7ef0bcb1918d4209954fc4929c7fe379-1-swapin-zswap-a | A/A | A | zswap | 10446.11 | 1031.00 | 84403.14 | 72259.02 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-disk-a | A/A | A | disk | 6412.52 | 1031.30 | 6068.35 | 4969.55 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-disk-b | A/A | A | disk | 5531.17 | 1031.30 | 6398.81 | 4427.74 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-zswap-a | A/A | A | zswap | 10445.03 | 1031.03 | 85214.89 | 73144.08 |
| 7ac434b0aad649298d7c0282b29a10c1-0-swapin-zswap-b | A/A | A | zswap | 10558.05 | 1030.78 | 84124.64 | 72233.67 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-disk-b | A/A | A | disk | 6665.75 | 1031.23 | 7225.32 | 4767.26 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-disk-a | A/A | A | disk | 5754.03 | 1031.04 | 6684.34 | 4765.45 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-zswap-b | A/A | A | zswap | 10481.47 | 1031.02 | 85328.44 | 73548.56 |
| 7ac434b0aad649298d7c0282b29a10c1-1-swapin-zswap-a | A/A | A | zswap | 10539.93 | 1031.03 | 85079.48 | 72183.24 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-disk-a | xs-ra-sequential-v1 | A | disk | 5663.36 | 1031.02 | 6430.76 | 4507.18 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-disk-b | xs-ra-sequential-v1 | B | disk | 6025.76 | 1031.21 | 6085.33 | 4753.35 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-zswap-a | xs-ra-sequential-v1 | A | zswap | 10484.35 | 1031.17 | 84274.80 | 72759.27 |
| 49add9b084d04941a459281838bbf3f3-0-swapin-zswap-b | xs-ra-sequential-v1 | B | zswap | 10436.45 | 1031.14 | 84549.76 | 72754.25 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-disk-b | xs-ra-sequential-v1 | B | disk | 5550.09 | 1031.14 | 6274.32 | 4443.01 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-disk-a | xs-ra-sequential-v1 | A | disk | 5395.28 | 1031.02 | 6488.78 | 4643.06 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-zswap-b | xs-ra-sequential-v1 | B | zswap | 10566.30 | 1030.96 | 83367.41 | 71789.28 |
| 49add9b084d04941a459281838bbf3f3-1-swapin-zswap-a | xs-ra-sequential-v1 | A | zswap | 10434.00 | 1031.17 | 85366.57 | 73017.95 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-disk-a | xs-zswap-linear-v1 | A | disk | 7514.60 | 1030.84 | 6470.70 | 4692.21 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-disk-b | xs-zswap-linear-v1 | B | disk | 7301.30 | 1031.48 | 7129.93 | 5295.47 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-zswap-a | xs-zswap-linear-v1 | A | zswap | 11003.78 | 1031.02 | 85068.27 | 73125.48 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-0-swapin-zswap-b | xs-zswap-linear-v1 | B | zswap | 12055.45 | 1031.02 | 68558.97 | 59311.17 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-disk-b | xs-zswap-linear-v1 | B | disk | 7614.95 | 1030.97 | 7156.94 | 5431.41 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-disk-a | xs-zswap-linear-v1 | A | disk | 7715.65 | 1031.00 | 6746.60 | 5427.66 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-zswap-b | xs-zswap-linear-v1 | B | zswap | 13566.39 | 1031.15 | 68253.58 | 59198.93 |
| 15ded9c2bdf44b5fae1b3e83f0f75daf-1-swapin-zswap-a | xs-zswap-linear-v1 | A | zswap | 10430.93 | 1031.12 | 85111.41 | 72987.11 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-disk-a | xs-ra-cluster-v1 | A | disk | 9024.87 | 1031.26 | 6850.61 | 4627.36 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-disk-b | xs-ra-cluster-v1 | B | disk | 7167.84 | 1031.27 | 8447.46 | 4626.23 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-zswap-a | xs-ra-cluster-v1 | A | zswap | 11676.86 | 1031.13 | 84617.55 | 47685.88 |
| 9ec21a04b74b4d46a7931c16112a6bdb-0-swapin-zswap-b | xs-ra-cluster-v1 | B | zswap | 11395.97 | 1030.77 | 84470.75 | 50426.41 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-disk-b | xs-ra-cluster-v1 | B | disk | 6468.79 | 1031.30 | 12949.55 | 4458.47 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-disk-a | xs-ra-cluster-v1 | A | disk | 7138.55 | 1031.37 | 5711.92 | 4997.44 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-zswap-b | xs-ra-cluster-v1 | B | zswap | 11985.44 | 1031.01 | 83462.12 | 44263.78 |
| 9ec21a04b74b4d46a7931c16112a6bdb-1-swapin-zswap-a | xs-ra-cluster-v1 | A | zswap | 11292.29 | 1030.98 | 82947.56 | 54554.61 |

## Required policy gates

Observed applies only to the tested configuration and workload; full promotion remains disabled.

| Candidate | Gate | Evidence state |
|---|---|---|
| xs-ra-sequential-v1 | gcc_swap_on | observed |
| xs-ra-sequential-v1 | gcc_swap_off | missing |
| xs-ra-sequential-v1 | gcc_zswap_on | observed |
| xs-ra-sequential-v1 | sparse_no_new_diagnostics | missing |
| xs-ra-sequential-v1 | checkpatch | observed |
| xs-ra-sequential-v1 | guest_boot_identity | observed |
| xs-ra-sequential-v1 | data_roundtrip | observed |
| xs-ra-sequential-v1 | fork_cow | observed |
| xs-ra-sequential-v1 | concurrent_fault | observed |
| xs-ra-sequential-v1 | swapoff_live_pages | observed |
| xs-ra-sequential-v1 | allocation_failure | missing |
| xs-ra-sequential-v1 | io_failure | missing |
| xs-ra-sequential-v1 | memcg_limits | missing |
| xs-ra-sequential-v1 | large_folio | missing |
| xs-ra-sequential-v1 | lockdep | missing |
| xs-ra-sequential-v1 | kasan | missing |
| xs-ra-sequential-v1 | kcsan | missing |
| xs-ra-sequential-v1 | no_new_kernel_warnings | observed |
| xs-zswap-linear-v1 | gcc_swap_on | observed |
| xs-zswap-linear-v1 | gcc_swap_off | missing |
| xs-zswap-linear-v1 | gcc_zswap_on | observed |
| xs-zswap-linear-v1 | sparse_no_new_diagnostics | missing |
| xs-zswap-linear-v1 | checkpatch | observed |
| xs-zswap-linear-v1 | guest_boot_identity | observed |
| xs-zswap-linear-v1 | data_roundtrip | observed |
| xs-zswap-linear-v1 | fork_cow | observed |
| xs-zswap-linear-v1 | concurrent_fault | observed |
| xs-zswap-linear-v1 | swapoff_live_pages | observed |
| xs-zswap-linear-v1 | allocation_failure | missing |
| xs-zswap-linear-v1 | io_failure | missing |
| xs-zswap-linear-v1 | memcg_limits | missing |
| xs-zswap-linear-v1 | large_folio | missing |
| xs-zswap-linear-v1 | lockdep | observed |
| xs-zswap-linear-v1 | kasan | observed |
| xs-zswap-linear-v1 | kcsan | missing |
| xs-zswap-linear-v1 | no_new_kernel_warnings | observed |
| xs-ra-cluster-v1 | gcc_swap_on | observed |
| xs-ra-cluster-v1 | gcc_swap_off | observed |
| xs-ra-cluster-v1 | gcc_zswap_on | observed |
| xs-ra-cluster-v1 | sparse_no_new_diagnostics | missing |
| xs-ra-cluster-v1 | checkpatch | observed |
| xs-ra-cluster-v1 | guest_boot_identity | observed |
| xs-ra-cluster-v1 | data_roundtrip | observed |
| xs-ra-cluster-v1 | fork_cow | observed |
| xs-ra-cluster-v1 | concurrent_fault | observed |
| xs-ra-cluster-v1 | swapoff_live_pages | observed |
| xs-ra-cluster-v1 | allocation_failure | missing |
| xs-ra-cluster-v1 | io_failure | missing |
| xs-ra-cluster-v1 | memcg_limits | missing |
| xs-ra-cluster-v1 | large_folio | missing |
| xs-ra-cluster-v1 | lockdep | observed |
| xs-ra-cluster-v1 | kasan | observed |
| xs-ra-cluster-v1 | kcsan | missing |
| xs-ra-cluster-v1 | no_new_kernel_warnings | observed |

## Judgment and next steps

A fast pass is a screening result. Retain useful mechanisms for owner review; do not launch a slow tier without explicit approval. A noisy A/A blocks its matching performance comparison. Confidence in correctness is limited to the actual configurations and guests recorded. A correctness failure or failed latency guard changes candidate disposition.

## Limitations

The first sparse-image A/A failed with 23.8% disk-random mean variation. Revision 2 preallocates private guest images; allocation is a plausible confounder rather than an established root cause. Every attempt counts against the same budget. Four-KiB application first-touch latency includes cache, timer, scheduling and readahead costs. Full promotion still needs allocation/I/O failure injection, memcg/large-folio/KCSAN coverage, confirmation and holdout. No candidate code is merged or published.
