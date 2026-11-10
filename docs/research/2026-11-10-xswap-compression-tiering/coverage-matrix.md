# Proposed build and guest coverage matrix

Status: planning inventory, not frozen protocol or execution evidence. Every subcase must be implemented, independently reviewed and validated before it is claimed. Failure to fit the complete required matrix blocks that phase; it does not remove a gate.

## Shared identities

- B-common: original anchor, unchanged standard mixed-frontend config.
- B-legacy: original anchor, ZSwap enabled and XSwap disabled.
- C-common, C-legacy: candidate versions of those configs.
- C-independent: candidate XSwap enabled, ZSwap compiled out.
- C-debug-common / C-debug-independent: corresponding configurations with KASAN, lockdep and selected deterministic fault-injection capabilities.
- C-race-common / C-race-independent: corresponding KCSAN configurations, never timing samples.
- C-noswap and C-no-frontends: build-only disabled configurations.

Read final .config, kernel identity and input-config hash for each. A requested fragment is insufficient. Old anchor's impossible XSWAP=y/ZSWAP=n combination is a config negative control, not a timing treatment.

## Proposed correctness boots

| Boot | C1 shared library | C2 independence | C3 demotion |
| --- | --- | --- | --- |
| 1 | B-common existing data/COW/fault/swapoff regression | Same, revalidated against current image/harness | Same |
| 2 | B-legacy nonzero compressed-resident compatibility | Same | Same |
| 3 | C-common existing XSwap regression | Same | Same |
| 4 | C-legacy compression, codec replacement, object/pool teardown and accounting | C-legacy compatibility | C-legacy compatibility |
| 5 | C-common no-backing compressed-resident path, nonzero data and real decoder activity | C-independent strict no-backing compressed roundtrip/teardown | C-independent no-backing independence plus bounded no-target failure |
| 6 | C-debug-common init/codec/allocation errors, multi-page rollback, memcg balance and observed large-folio input | C-common coexistence, separate pools/accounting and no duplicate interception | C-independent deterministic selected-target demotion, roundtrip and physical swapoff |
| 7 | C-race-common concurrent load/free, codec/pool replacement and teardown | C-independent incompressible data, bounded pool admission and explicit physical fallback | C-independent pressure demotion, completed I/O and actual net RAM release after staging drains |
| 8 | C-debug-common two-node locality, per-CPU context hotplug and memcg ownership | C-debug-common shared lifecycle, fault cleanup, large-folio and memcg/offline cases | C-debug-common coexistence, writeback permission, memcg/offline and large-folio cases |
| 9 | unused reserved capacity | C-debug-independent allocation/fallback errors, slot reuse and teardown races | C-debug-independent allocation/decode/ENOSPC/I/O failures, authoritative-copy recovery and target teardown |
| 10 | unused reserved capacity | C-debug-independent two-node allocation/charge isolation and guest CPU hotplug | C-debug-independent two-node targeted pressure/reclaim, charge and node isolation |
| 11 | unused reserved capacity | C-race-common coexistence and lifecycle races | C-race-common coexistence and pressure races |
| 12 | unused reserved capacity | C-race-independent faults/invalidation/slot reuse/destroy | C-race-independent controlled migration/fault/free/target-swapoff/destroy overlap |

A row can contain several deterministic subcases only after the trusted workload supplies independent start/end markers, data verification, and state reset for each. Reset means: drain in-flight I/O/work; free all test mappings/objects; verify references, charges and counters return to the defined starting state; remove prior test cgroups; restore injection controls; recreate device/pool topology where needed. A reset failure invalidates the boot and stops following subcases.

An injected-failure pass requires evidence that the intended failure actually occurred and that cleanup/data checks passed afterward. A sanitizer-enabled build without executed affected paths is not coverage. Large-folio coverage requires observing a real large-folio input; THP config alone is insufficient.

Do not claim arbitrary interleaving coverage from uncontrolled stress. Controlled race barriers/observations and source-lifetime review are required for the named races.

## NUMA and device topology

Timing retains the approved single-topology 4-vCPU, 4096-MiB, 16-GiB scratch configuration and its own identity. Correctness boots 8 in C1 and 10 in C2/C3 use an explicit two-node auxiliary topology: two vCPUs and 2048 MiB per node, same total resources. Record the complete QEMU arguments, online nodes, memory policy and exercised source/destination node. This is a new correctness configuration, never silently mixed into timing samples. If guest NUMA/locality controls are unavailable or not observed, that gate remains incomplete.

Compressed-resident timing and strict independence use no lower swap backing. Prove target pages are swapped into compressed storage, then observe demand decode hits while validating page contents; nonzero total traffic alone does not prove every timed sample's origin. Unexpected cache-only residency or physical fallback invalidates the relevant sample. Zero-filled pages are tested separately because zeromap can bypass compression.

Fallback/failure/demotion use an explicitly recorded disposable target topology. Normal timing keeps its original target. Correctness may use a bounded device-mapper target for deterministic ENOSPC/I/O errors, only inside the guest and with a pinned setup. Every extra block device or mapper configuration must be frozen in the coverage identity before execution. SSD-A-to-B replacement is not part of the first demotion claim.

## Build slots and reuse preconditions

C1 requires up to eight distinct build identities: B-common, B-legacy, C-common, C-legacy, C-debug-common, C-race-common, C-noswap, C-no-frontends. No reuse is assumed in that ceiling.

C2/C3 require nine candidate identities: C-common, C-legacy, C-independent, two debug variants, two race variants, C-noswap, C-no-frontends. B-common and B-legacy are unchanged control identities from C1. To fit the ten-build campaign ceiling, at least one control build must be admitted through exact native build-cache verification; both are expected to be reusable only if source/config/toolchain/builder identity and artifacts remain valid. No stale performance samples are reused by this build reuse.

Check build-cache admissibility before opening C2/C3. If neither control is valid, the complete eleven-build matrix does not fit the ceiling: stop and revise the allocation through the project process before running, not during a comparison. Build attempts that fail remain spent. Additional compile revisions or coverage configurations consume remaining build slots and can prevent a campaign from reaching timing.

## Guest accounting

The proposed four-case probe and three-case fast matrix consumes 100 guests per campaign. Correctness adds 8 for C1 or 12 for C2/C3, leaving 12 or 8 attempts within the 120 cap for invalid attempts/recovery. These counts include baseline correctness; debug boots are counted and never used as performance samples.

This matrix is a feasibility proposal. Runtime duration, subcase reset reliability and failure-injection observability remain unmeasured. Implemented manifest validation must reject an unavailable or uncounted row and must stop before timing if required coverage has not passed.
