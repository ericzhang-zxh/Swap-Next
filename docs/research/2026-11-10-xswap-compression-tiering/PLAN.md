# XSwap shared compression and tiering: integrated campaign plan

Status: owner approved execution; C1 trusted capability is integrated and its frozen campaign is running. Later phases remain dependent on C1 correctness.
Contributor: codex-tiering-01a1c6b6.
Owner objective: run several evolve campaigns on the shared-compression, independent-XSwap and generic-tiering direction.
Coordination: three built-in agents, shared file board, per-ticket ownership and direct peer messages. No AGY.

## Decision

Run three substantive, dependent campaigns after preparing the required trusted test capability. Start with the existing crypto-acomp/zsmalloc implementation, preserve frontend-owned policy and lifetime, then give XSwap its own compressed operations, then implement bounded RAM-to-SSD demotion and pressure integration.

Keep the existing broad swap-architecture profile disabled. Add a narrowly reviewed profile and a new frozen protocol revision for this objective. Do not spend three campaigns on in-file refactoring or disk-only timing and label them architecture validation.

All three retain kernel anchor and common comparison baseline 5e84ca928deeacb4eee656806a003f27d1eca82f. Earlier unrelated optimization candidates remain read-only references. Later cumulative implementations preserve predecessor patch provenance and follow the controller's allowed-parent rule. Neutral refactoring does not advance the baseline.

## Campaigns

| Campaign | Candidate intent | Required capability result | Timing and resource result | Stop condition |
| --- | --- | --- | --- | --- |
| C1 shared store | Extract page compression/object storage into mm/page_compress.c and include/linux/page_compress.h; adapt ZSwap with its behavior preserved. | Real nonzero compressed storage/load, legacy ZSwap compatibility, pool/codec/CPU-hotplug lifetime, error cleanup and config identity. | A compressed-resident primary case plus retained disk/zram guards; record metadata and CPU-context footprint. | Ownership/charge drift, missing exercised compression path, lifecycle failure, or unacceptable regression. |
| C2 independent XSwap | Implement XSwap compressed frontend/ops using C1; remove actual ZSwap initialization, registry and accounting dependencies. | CONFIG_ZSWAP=n and XSWAP=y, no physical backing, nonzero compressible data, actual compressed objects and decoder traffic, roundtrip/teardown; coexistence and fallback separately. | Matched common-config comparison to original anchor; independent-config capability is reported separately. | Disk/zeromap false positive, no-op memcg accounting, duplicate compression, stale-slot or teardown race. |
| C3 pressure demotion | Establish deterministic selected-target RAM-to-SSD demotion, then register a bounded memcg/NUMA-aware shrinker. | Stable logical entry, target write completion, recoverable failures, charge balance, real pool-memory reduction after staging drains, controlled races. | Swap-in guards plus source/target residency, staging peak and actual net RAM released. | Lost data, deadlock, unbounded retry, forbidden target/writeback, or no net RAM reclaimed. |

SSD A-to-B replacement and SSD-to-compressed-RAM promotion remain explicit dependent hypotheses. The initial three campaigns establish the shared foundation and pressure-driven demotion. They cannot establish unimplemented directions. Do not introduce a compressed-on-disk format in this phase.

## Frozen architecture choices

- The common library owns codec contexts, CPU lifecycle, compressed pool storage and store/load/free/backing-pages operations.
- Frontends own logical indexes, pool/entry lifetime pins, memcg ownership, admission, LRU and placement. A load is non-consuming; successful store transfers one handle and length. Avoid a per-object heap wrapper/refcount added solely for abstraction.
- Keep separate frontend pools/state. Shared code does not force global policy or shared residency.
- Device-selected XSwap operations run before legacy ZSwap interception. Define handled/retry/error and folio-lock/completion ownership explicitly.
- Initially retain XSwap's compressed index plus xs_table physical mapping. Reuse the stable logical entry instead of editing every PTE.
- RAM-to-SSD can retain protected swap-cache staging. A valid authoritative copy must survive failure; I/O submission is not completion or net reclamation.
- General physical replacement later needs reserve/commit/abort, destination-swapoff-visible reservations and actual completion status.
- Use the existing shrinker integration first. No new vmscan hook is planned.
- Preserve ZSwap's existing external controls. Make XSwap accounting and permission semantics explicit in the experimental frontend; never rely on !ZSWAP no-op helpers or PF_MEMALLOC-only forced charging from a normal worker.
- XSwap promotion and new public cgroup ABI are outside the first implementation. Resolve any unavoidable ABI issue before widening that scope.

## Kernel source scope

C1 permits mm/zswap.c, mm/Kconfig, mm/Makefile and include/linux/cpuhotplug.h; adds mm/page_compress.c and include/linux/page_compress.h. Focused tests may add mm/page_compress_test.c and tools/testing/selftests/mm/swap_next_compression.c with their necessary build entries.

C2 additionally permits mm/swapfile.c, mm/page_io.c, mm/swap_state.c, mm/swap.h, include/linux/swap.h, include/linux/swap_ops.h, include/linux/zswap.h, mm/memcontrol.c and include/linux/memcontrol.h; adds mm/xswap.c and private mm/xswap.h. Any use of mm/swap_state.c must be justified by exact integration callers, not unrelated swap-in tuning.

C3 uses the same enumerated scope for migration/reclaim plus a narrowly named tiering selftest. Changes to crypto algorithms, zsmalloc internals, vmscan, new storage formats and unrelated readahead remain excluded.

Draft maximums: C1 10 files/2500 changed lines; C2 20/6000; C3 22/8000 cumulative against the common anchor. These are preparation estimates for review, not target patch sizes. Freeze the actual policy before its campaign.

## Staged capability preparation

1. Prepare a separate trusted-code worktree. Candidate worktrees cannot edit profiles, evaluator, parsers or guest images.
2. Add named, hash-bound config coverage: legacy ZSwap, common mixed mode, independent XSwap, disabled builds and relevant debug/failure variants.
3. Make guest setup conditional on real frontend capability and explicit device topology. The current nominal compressed correctness route activates zram1 but its test expects vda; reproduce and repair this mismatch in the trusted harness.
4. Add compressed-resident workload/evidence with nonzero data. Prove exercised store/load traffic and verify contents; keep zero-page handling a separate case.
5. Before C1, implement only shared-library/legacy correctness and the relevant compressed-resident measurement path. Before C2, add independence workloads and their counted proof/negative fixtures; before C3, add migration/pressure workloads and evidence. Old anchor is an expected negative control for ZSWAP=n XSwap, not a failed like-for-like performance arm.
6. Strengthen identity and cache binding for each config/workload/observer; absent, partial or contradictory phase evidence fails closed.
7. Install separate phase-specific narrow profiles and protocol validators only when that phase's capabilities are implemented and independently reviewed. The union profile-proposal.json is a planning inventory, not the C1 runtime contract. Keep old profiles/protocols unchanged.
8. Exercise baseline correctness and new workload validity before candidate performance. Prepare KASAN/lockdep/KCSAN and deterministic failures appropriate to each changed boundary; missing required coverage stops that stage.
9. Use durable start/execute/decide/value actions with contributor codex-tiering-01a1c6b6. Preserve reservations, failed attempts, STOP state and immutable identities.

The complete trusted change list and acceptance matrix are in validation.md; coverage-matrix.md enumerates proposed boots/builds and reset requirements. Kernel ownership/lifetime details are in compression.md and migration.md.

## Protocol proposal and budgets

Retain the current approved TCG shape and timing rules: 4 vCPU, 4096 MiB guest RAM, 16 GiB preallocated scratch swap, 900-second guest timeout, 10 A/A pairs, four AB/BA pairs, p90 calibration envelope, 25 percent ceiling, existing advisory p99 treatment and existing validity checks. Add one compressed-resident primary case with no lower physical backing; prove target residency and demand decode hits, and reject unexplained swap-cache-only/fallback samples. Retain disk and zram-64k as regression guards and the metadata probe. New configuration/proof fields require a new protocol revision and new scientific identity.

Four probe cases at three A/A runs plus one candidate run consume 12 + 4 guests. Three fast cases consume 60 A/A + 24 paired-comparison guests. This is 100 guests before correctness and invalid attempts. The proposed phase-specific matrix in coverage-matrix.md uses 8/12/12 correctness guests and at least 8 attempts for invalid/failure recovery. These are planned boots, not verified coverage. If the complete required matrix cannot fit, revise the plan before freezing; never omit a required gate to fit the budget. Multiple deterministic subcases may run in one guest only when the trusted workload records and verifies each subcase and their isolation.

One substantive candidate initially per campaign, at most 120 guests, 10 builds and 18 hours per campaign. Three-campaign line ceiling is 360 guests and 30 builds. Ceilings do not authorize retrying the same failed measurement under a new campaign. No slow tier, host mutation or code promotion.

Fresh calibration is budgeted. The 15 retained calibration-cache records inspected by R3 were expired. Reuse only after exact native identity/freshness validation, keeping original timestamps and counted provenance. New harness/config/case identities may prevent reuse.

## Decision and delivery

Each campaign reports implementation capability, correctness coverage, pressure mechanism and calibrated performance separately. Failed correctness stops dependent work. A noisy calibration stops performance ranking; do not claim speed or equivalence from a neutral mean.

Retain experiment records, failed attempts and patches; follow the repository's publication policy for completed campaigns. Produce a coherent final architecture narrative linking all campaigns while preserving each frozen ledger/protocol and exact review evidence. Reports must not merge or rewrite scientific identities.

No campaign, build or guest has been launched by this planning pass. The shared board and source audits are the current deliverables.

## Approved change scope

The user's architecture and experiment objective is recorded above. The repository's explicit core gate additionally names benchmark runners, guest images/parsers and new protocol measurement parameters. The concrete next action is to prepare and integrate the trusted capability bundle described here, then execute the three bounded campaigns. This approval is about that trusted capability/protocol change, not a repeat request to approve the already requested research direction.

Source: AGENTS.md, What needs owner approval: “Approval needed (core)” includes benchmark runners, guest images and parsers, and any protocol measurement parameter. The owner approved this scoped change on 2026-11-10; authorization.json retains the instruction. Each phase still needs its implemented capability and runtime gates. The broad unsupported profile remains disabled.
