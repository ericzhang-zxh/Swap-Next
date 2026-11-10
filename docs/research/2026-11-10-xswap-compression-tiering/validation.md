# Validation and campaign readiness

Research ticket R3. Inspected repository commit `5f0d57e3fe365db15878c5ca674cccc8558f36a5`; kernel reference `5e84ca928deeacb4eee656806a003f27d1eca82f`. Inspection ran only on the Linux worker. No build, guest, campaign mutation, profile edit or runtime experiment was performed. AGY was not used.

## Decision

The current executable profile can support a narrowly described preparatory refactor, but it cannot execute or prove the requested shared-library independence and generic pressure-driven migration. Prepare a separate, reviewable trusted harness/profile change before opening the architecture campaigns. Keep `swap-architecture` non-executable and preserve all existing frozen protocols.

A real first campaign should extract and exercise the shared mechanism, not spend calibration on a code path that the workloads disable. The proposed three campaigns have a common original anchor and cumulative implementations; a neutral extraction does not advance the performance baseline.

Confidence: high for the source-level capability gaps below. Actual runtime feasibility and new workload reliability remain unmeasured.

## Current capability matrix

All source line numbers below refer to repository commit `5f0d57e3`, except explicitly named kernel-reference anchors.

| Requirement | Verified current capability | Gap / acceptance consequence |
| --- | --- | --- |
| Immutable candidate build isolation | `benchmark/kernel/build.py:35-58` archives an exact Git commit and builds via unprivileged user/mount/net/PID namespaces. `build_namespace.sh:12-29` mounts toolchain/source read-only, excludes host home/network/credentials and drops capabilities. | Reuse this builder; no direct host execution of candidate scripts. A builder invocation is not a guest reservation. Preserve controller/session accounting. |
| Candidate source scope | `evolve/profiles/swap-core.json` permits eleven existing swap source/header files and additions only matching `tools/testing/selftests/mm/swap_next_*.c`. `controller.py:612-615` enforces policy subset of trusted profile. | No new compression source/header, `mm/Kconfig`, `mm/Makefile`, cpuhotplug or memcontrol edits are authorized by this profile. Existing in-file factoring is a precursor only. |
| XSwap without ZSwap | `run.py:203-223` unconditionally requires `CONFIG_ZSWAP=y`; `bench.sh:53-89` unconditionally accesses ZSwap parameters and enables it before XSwap creation. | `CONFIG_ZSWAP=n` cannot be admitted by the runner. Add a separately identified independent-XSwap storage setup and exact config proof. |
| Configuration matrix | `standard_workflow.py:458-480,724-731` builds and checks only `benchmark/config/swap-standard.config`; `correctness_proof.py:143-148` hardcodes the same input config. | A debug/no-ZSwap build cannot silently count as the standard-config proof. Add trusted config IDs and an explicit coverage manifest, preserving exact input/final config/image hashes per case. |
| Compression-path performance | Revisions 6/7 score `swapin-disk` and `swapin-zram-64k` (`validity.py:212-225`). Both disable ZSwap after XSwap creation (`bench.sh:79-89`). | These guards cannot establish that the extracted compressor runs. Retain them as regressions guards and add a compressed-resident swap-in case with observed object/decoder traffic. |
| Existing data/COW/fault coverage | `correctness.c:79-125` verifies XSwap PTEs, 48 child faults on 16 shared targets, COW and data roundtrip. | Useful regression coverage; it is not a controlled race with a migration transaction. |
| Existing swapoff coverage | `correctness.c:126-164` removes a physical backing device with live XSwap PTEs, destroys XSwap and validates data. | Device is hardcoded to `/dev/vda`. No SSD-A-to-B migration or destination removal during a controlled in-flight migration. |
| Nominal ZSwap correctness route | `run.py:235-237` accepts xswap + disk/zswap. However `bench.sh:67-70` configures ZSwap over `/dev/zram1`, while `correctness.c:126-141` requires and swaps off `/dev/vda`. | Treat compressed-backend correctness as unverified and source-mismatched until the device topology is explicit and tested. Do not count its nominal enum as working coverage. |
| Plain-mode compatibility | `correctness_proof.py:70-100` explicitly rejects plain-mode proofs; `correctness.c:29,65` requires XSwap type/debugfs. | Extracting a library used by legacy ZSwap needs a real plain/ZSwap compatibility test, not an XSwap-only certificate. |
| Large folios | `correctness.c:70-74` requests `MADV_NOHUGEPAGE`; swap-in does the same by suite contract (`README.md:36-40`). | Add an independent large-folio correctness case with observed allocation/order and split/partial-backend behavior. Merely configuring THP is insufficient. |
| Allocation/I/O failure and ENOSPC | Existing scored correctness gates are roundtrip/COW/concurrent fault/swapoff/warnings. No controlled injection in the inspected guest. | Add deterministic counted failure cases and verify authoritative-copy retention, charge rollback, slot reuse and termination. |
| Sanitizers | Debug/KASAN config files exist. Standard config disables KCSAN/fault injection and does not enable PROVE_LOCKING. Current proof pins the standard config. | Establish config-bound KASAN/lockdep/KCSAN runtime coverage for affected paths; historical debug builds do not certify a new candidate. |
| Memory pressure | Suite snapshots meminfo, vmstat, cgroup CPU/stat and supports memcg pressure (`bench.sh:13-37,110-115`); lifetime stress uses ZSwap-specific hooks (`:194-211`). | No trusted proof of new migration completion or net physical RAM release. Global pressure is an explicit separate gap (`README.md:145-148`). |
| General architecture profile | `swap-architecture.json` is non-executable and names full correctness, state-invariant/per-operation adapters and metadata/reclaim-CPU gaps. `research.py:164-227` checks real protocol/profile capabilities. | Keep it disabled. A new narrow profile becomes executable only after its named capabilities exist and the trusted changes are accepted. |

The standard configuration has `ZSWAP=y`, `XSWAP=y`, `THP_SWAP=y`; `swap-standard-noxswap.config` disables **XSWAP**, not ZSWAP. It is not the independence configuration.

## Proposed trusted contract

Prepare a distinct profile, tentatively `xswap-compression-tiering-v1`, and an explicit new protocol revision. The draft initially remains non-executable. Primary metric stays `swapin_seq.mean_ns` (or the predeclared random variant); functional capability gates cannot be replaced by a performance score.

### Kernel scope

Start from the existing swap-core files and enumerate additions required by R1/R2, rather than use a broad `mm/*` wildcard:

- Add `mm/page_compress.c`, `include/linux/page_compress.h` and narrowly named tests.
- Permit `mm/Kconfig`, `mm/Makefile` and `include/linux/cpuhotplug.h` for independent library lifecycle/build integration.
- Add `mm/memcontrol.c` / `include/linux/memcontrol.h` only if the final accounting design requires moving ZSwap-conditioned interfaces.
- Add `mm/vmscan.c` only if an existing shrinker integration cannot satisfy the agreed reclaim contract; a new direct reclaim hook is not presumed necessary.
- Freeze actual maximum file/line scope from the selected implementation plan, not from a target result.

Separate this kernel allowlist from the trusted harness worktree; candidate workers cannot edit their evaluator.

### Required configurations and evidence

1. Legacy ZSwap with XSwap absent: ordinary swap + compressed-cache behavior must still work.
2. Both frontends enabled: separate instances/accounting, no duplicate compression or interception.
3. XSwap enabled with `CONFIG_ZSWAP=n`: create XSwap, store nonzero compressible data, demonstrate actual compressed object creation and decompression with **no lower backing device**, roundtrip and teardown. A successful fault served by disk fallback cannot certify compression independence.
4. Incompressible data: explicit fallback/error behavior with no fabricated compression success.
5. Build-only disabled combinations: both frontends disabled; SWAP disabled where valid.
6. Shared-library lifecycle cases: guest CPU hotplug, compressor/pool switch while old objects remain live, initialization/codec/allocation failure, partial-folio store rollback and memcg offline/balance.
7. Debug variants bound to each affected runtime path: KASAN/lockdep, KCSAN and controlled failures. These are correctness evidence, not timing samples.

For independence, old anchor `5e84ca92` is a negative control: it cannot satisfy `XSWAP=y,ZSWAP=n`. Do not force that impossible baseline configuration to run or report it as candidate failure. Compare common observable behavior in a separately frozen matched baseline/candidate arm; the candidate-only capability test is distinct.

Use nonzero patterns. Kernel `mm/page_io.c:226-228` handles zero folios through zeromap before compression, as R2 verified; all-zero data could falsely pass an independence test without using the new library.

### Migration and pressure acceptance matrix

| Test | Required observations |
| --- | --- |
| RAM -> SSD normal demotion | Same logical entry before/after, compressed-source residency decreases, destination allocation and completed I/O increase, full data roundtrip. |
| Net RAM release | Actual allocated pool pages decrease after all staging/writeback folios drain; record metadata and staging overhead. Compressed payload length alone is not freed physical memory. |
| Concurrent fault / free / slot reuse | Controlled overlap with migration, valid generation/ownership revalidation, no stale mapping or data from a recycled slot. |
| Physical target swapoff / XSwap destruction | In-flight work drains or aborts safely; all references/charges/mappings converge and data remains readable. |
| Allocation failure / destination full / I/O error | Preserve a valid authoritative copy; unwind destination reservations/charges; no double free, silent loss, permanent busy state or unbounded retry. A protected full folio can be the authoritative copy after the compressed object is released. |
| memcg and NUMA | Charge owner remains correct, writeback-disabled group stays protected, target-node pressure does not free/charge unrelated ownership incorrectly; per-group isolation observed. |
| Reclaim-context progress | NOFS/NOIO constraints, bounded staging reserve, bounded batches, no recursive reclaim/deadlock and no allocation storm. |
| Large folios | Observed large-folio input; correct split/partial-failure semantics; preserve logical order and per-subpage data. |
| Promotion and SSD A -> B | Separate tests and explicit destination selection/commit/rollback. A RAM -> SSD pass does not establish these behaviors. |

The state-invariant evidence adapter must bind test phase, operation IDs, logical identity, source/target, actual completions, errors and config/commit to trusted raw output. Structural review remains an additional gate, not runtime proof.

## Minimal trusted harness changes for an isolated reviewable worktree

1. `benchmark/config/`: add named independent-XSwap and debug/injection configs or deterministic fragments; preserve existing config files.
2. `benchmark/swap-standard/run.py`, `bench.sh`, `guest-init`: an enumerated independent compressed backend and explicit guest device topology; conditional ZSwap setup; accept new configurations only through a trusted ID/hash map. Guest files/devices remain disposable and network-isolated.
3. `correctness.c` plus a separate narrowly named tiering workload: generalize identity/device discovery for plain/legacy/independent paths, add deterministic injection and migration phases, keep existing checks.
4. `prepare-image.py`, `tools.json`, `evidence.py` and their tests: include/harden the new workload, parse only complete phase-bound output; reject absent/contradictory traffic, config, faults or completion evidence.
5. `evolve/control/correctness_proof.py`: validate a manifest of counted raw proofs covering the whole frozen matrix, rather than silently selecting one successful standard-config guest.
6. `evolve/standard_workflow.py`, `calibration_cache.py`, `reference_cache.py`: config-specific immutable builds/identities and matrix fingerprints; cache keys include every new measured input. Keep count/reservation/STOP/ownership checks.
7. `validity.py`, new profile, and protocol tests: new explicit revision with retained disk/zram performance guards plus compressed-resident primary case, pressure/state invariants and budget arithmetic. Do not relabel revision 6/7 or weaken existing thresholds.
8. Framework tests: negative controls for wrong config, absent compressor traffic, unobserved migration, non-counted proof, failed/partial injection, stale image/hash, duplicate guest, unsupported backend, expired calibration and profile activation before capability completion.

The review bundle should contain the complete diff, exact new profile, example frozen protocol, named coverage cases and unit/evidence fixtures. Runtime stays gated until this work is accepted and the real capability path is validated.

## Three substantive campaigns

| Campaign | Hypothesis / implementation | Before timing | Decision boundary |
| --- | --- | --- | --- |
| C1: shared mechanism | Extract a real shared compression/object-management implementation while preserving legacy ZSwap behavior and ownership. | Legacy frontend compatibility, compressor/object-lifecycle tests, actual compression/decompression traffic, rollback and debug checks. | Build + structural extraction is a functional milestone; neutral timing alone cannot establish equivalence or justify a baseline advance. |
| C2: independent XSwap | Add XSwap compressed backend through swap_ops using C1's shared library, independent of ZSwap. | Strict no-ZSwap configuration, nonzero/incompressible patterns, old-anchor negative control, coexistence, accounting, COW/concurrency/swapoff. | Only label independence when runtime and config proof pass. Reject duplicate interception or changed charge semantics. |
| C3: pressure demotion | Move cold XSwap compressed data to SSD through the common migration transaction/reclaim interface. | Controlled normal/failure/race/pressure matrix and measured net physical RAM release after drain. | Report RAM -> SSD only until explicit other-direction tests pass. No speed win can override lost-data or progress failure. |

Keep `anchor_commit = baseline_commit = 5e84ca92` for all three. Implement later cumulative candidates from the frozen anchor using retained reviewed patches, following the controller's allowed-parent rule; do not adopt another contributor's campaign or advance the baseline on a neutral refactor. Record predecessor provenance separately. An optional parent-relative arm needs its own counted resources and does not replace common-anchor comparison.

The common old disk and zram-64k cases remain guards. A new compressed-resident case must demonstrate library use. For pressure work, require the candidate-specific mechanism before scheduling its timing screen.

## Budget and retained evidence

The current rev6/7 one-candidate minimum is 9 probe A/A + 40 fast A/A + 3 candidate probe + 16 fast AB/BA + at least 1 correctness = **69 guests**, without invalid attempts or the new architecture matrix. Three separately calibrated campaigns need at least **207 guests** even before adding relevant new cases.

With retained disk/zram guards **and** one new compressed primary, a comparable three-case latency design requires 60 A/A + 24 AB/BA guests. Four probe cases including metadata require 12 A/A + 4 candidate guests: **100 before correctness/retries**. Under a 120-guest campaign ceiling, the entire real correctness matrix and invalid-attempt allowance must fit in the remaining 20; otherwise stop and redesign the proposed allocation before launch, not mid-comparison. One substantive candidate per campaign is the realistic initial plan.

Recommend upper ceilings of 120 guests / 10 builds / 18 hours per campaign and a line lifetime ceiling no greater than 360 guests / 30 builds, subject to the primary's allocation. These are caps, not a promise that every branch or revision fits. Do not launch extra campaigns merely to reset failure budgets.

Current observations:

- As of 2026-11-10 18:37 UTC, `exp1-sync-zero-redundancy` and `exp3-async-zswap-prefetch-2026-11-06` have retained `CALIBRATED`, `PROBE_PASS` and `FAST_PASS` rows. This source audit did not revalidate every raw guest or accept their authored coverage claims.
- All 15 current calibration cache records are expired at that inspection time (latest expiry Unix `1794100124.4593444`). Historical November 3 metadata noise is not a blanket present failure, but fresh calibration must be budgeted.
- Cache identity includes exact source/build/config, guest image, harness hashes, machine, accelerator, shape and protocol; only enumerated cosmetic/allocation fields are ignored (`reference_cache.py:28-39,134-165`; `calibration_cache.py:23-47`). New harness/config/cases invalidate reuse. A new valid cache hit retains its original finish/expiry and is not an independent sample.
- Linux worker had no campaign claim and no observed QEMU/build/evolve process at the read-only check; global STOP was absent. Recheck immediately before any future launch.
- Foreign open campaign on grok-cloud remains untouched.

## Existing-scope precursor option

An in-file extraction in `mm/zswap.c` that makes codec/object ownership explicit can use the existing allowed paths, exact-tree structural review and existing regression tests. Because rev6/7 scored paths disable ZSwap, their fast result is only a regression guard for that refactor; it provides no evidence that the new internal helper reduced compression cost. Do not label this precursor a shared library, ZSwap-independent XSwap, or a tier-migration campaign. Prefer completing the new relevant test contract first rather than spending multiple full calibrations on preparatory-only work.

## Peer reconciliation

R1 supplied the concrete library/build-lifecycle file scope and confirmed that in-file factoring is not independence. R2 supplied the zeromap negative control, protected-staging-copy writeback semantics, logical/physical transaction requirements, source-residency vs net-RAM distinction, and the warning that runtime-disabled ZSwap's writeback policy shortcut cannot be inherited by independent XSwap. These requirements are incorporated above.

## Final integrated-plan peer review

Reviewed PLAN.md and profile-proposal.json. The proposal is correctly disabled and not installed. Budget arithmetic is correct; old guards and the fixed anchor are retained. Three refinements are required before any protocol freeze:

- **R3-P1 (PLAN.md:52-58,67-69):** The 100 + 12 + 8 = 120 guest arithmetic is correct, but at most 12 correctness guests and 10 builds is not yet demonstrated against an enumerated stage-specific boot/config manifest. Legacy, mixed, independent, baseline, sanitizer and injection variants can exceed either cap. Before freezing each campaign, enumerate exact builds and counted guest cases, required subcases per guest, reset/isolation evidence, expected-failure controls and recovery allocation. Do not call all three campaigns execution-ready until this manifest fits; keep later-stage gates out of C1.
- **R3-P2 (PLAN.md:20-21,54,65):** Observed nonzero compression/decompression traffic alone does not prove that the timed first-touch samples are compressed-resident; a mixture of swap-cache hits and fallback I/O can still dominate the endpoint. Freeze the timed-source validity rule for both arms. Prefer a no-lower-backing compressed-resident timing topology with demonstrated target residency and decoder hits, or equivalent per-sample/phase evidence excluding unplanned fallback. Keep fallback behavior in separate cases, and match codec, pool limits and workload across common-anchor arms.
- **R3-P3 (PLAN.md:22,58,65):** The retained 4-vCPU/4096-MiB TCG shape does not specify a multi-node NUMA topology. A normal single-node boot cannot establish the NUMA-aware reclaim claim. Add a counted correctness-only multi-node topology with explicit QEMU/config/node-discovery/placement evidence, or mark multi-node reclaim behavior unvalidated and stop short of that claim. Bind topology to the new protocol and proof; do not silently change timing-arm topology.
