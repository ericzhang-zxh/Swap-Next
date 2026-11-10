# H3: Configured C1 coverage and timing admission

Status: implemented and guest-free verified; coordinator integration and real runtime validation remain.
Branch: infra/tiering-h3-01a1c6b6.
Source base: 5f0d57e3fe365db15878c5ca674cccc8558f36a5.

## Result

Revision 8 requires the complete frozen C1 correctness matrix before any timing launch or calibration-cache admission. A canonical pass revalidates all eight raw guest cases and both disabled build configurations. Missing, duplicate, failed, incomplete or uncounted evidence cannot satisfy the matrix.

The configuration catalog adds c1-common, c1-legacy, c1-debug, c1-kcsan, c1-noswap and c1-no-frontends. Historical swap-standard.config is unchanged. c1-common enables the frozen PID-filtered kretprobe observer prerequisites. c1-debug also enables and verifies ACPI/SRAT NUMA prerequisites from the pinned source, so CONFIG_NUMA alone cannot satisfy the auxiliary two-node contract.

Build preparation is counted before launch. A configured artifact carries source commit/tree, input/final config and image hashes, builder/toolchain identity, and its original counted build ledger. Native build-cache validation preserves original observation time and budget. Repeated successful coverage requests return the existing row; failed or interrupted builds remain spent.

Runtime reservations, parser calls and cache identities carry configuration, correctness-case and topology identities. Raw correctness verification binds the recorded complete QEMU command, topology arguments, guest image/source hashes, subcase status/reset evidence and final sanitizer configuration. Typed candidate failures require verified raw serial identity before they can invalidate history.

## Interfaces

Prepare one frozen build case:

    python3 evolve/standard_workflow.py build-coverage --campaign C --case CASE [--candidate ID]

Baseline rows may omit --candidate. Candidate rows require it. Multiple cases may reuse one exact configured artifact after native verification.

All revision 8 timing actions, including calibration and guest-launching reference checks, require:

    --candidate ID --correctness campaigns/C/<canonical-matrix>.json

Read-only status, plan, next, cache inventory and matrix_progress remain available without a correctness pass.

Schema 2 canonical matrix fields are campaign, source_commit/candidate_commit, baseline_commit, protocol_sha256, runs[{case_id,result_path,result_sha256}], and builds[{case_id,build_manifest,build_manifest_sha256}]. matrix_progress returns manifest_data after complete raw verification and otherwise identifies the next missing case or build without writing evidence.

The parser returns correctness_subcases[id] with status=PASS and reset=true for successful isolated subcases. Raw H2 reset strings are normalized by H1. The runner records topology_arguments and the full command. A single-node library test cannot substitute for c-numa.

## Validation

110 guest-free tests passed: 26 new coverage tests plus 84 existing workflow/cache/proof/reservation tests. git diff --check passed.

    python3 -m unittest evolve.test_compression_coverage evolve.test_standard_workflow evolve.test_calibration_cache evolve.test_reference_cache evolve.control.tests.test_guest_budget evolve.control.tests.test_correctness_proof

The new tests verify full/partial matrices, missing and extra counted attempts, subcase/reset failures, serial identity before typed failure, configuration/topology swaps, command and image hashes, resolved debug flags, counted build origin, symlink rejection, native cache revalidation, reservation before build command, successful idempotence, retained failed attempts, and refusal to calibrate or reuse timing before complete correctness.

Tests use synthetic source repositories, artifacts and serial-parser fixtures. They do not compile or boot a kernel. H1's real serial parser and H2's workload have their own tests and require integrated coordinator verification.

The current draft's eight guest IDs and two build-only IDs matched this catalog. After adding the ACPI prerequisites, c1-debug input_config_sha256 is:

    c58461570b79210f9d99c7eb2e3a6e492601960ea73394bb4e4c78b147cd0ba4

The coordinator must refresh the draft pin before freezing it.

## Limitations and next acceptance

No kernel build, guest image build, guest, campaign, AGY task, profile activation, publication or host mutation was executed by H3. Actual baseline/candidate capability, correctness and performance are unmeasured.

The parent owns H1/H3 integration, profile/protocol/session acceptance, image preparation, counted campaign execution and delivery. Actual K1 library tests must supply the reviewed allocation rollback, partial cleanup and NUMA-placement semantics. H2's unsupported standalone failure/locality stubs remain incomplete and are not scheduled as passing cases.
