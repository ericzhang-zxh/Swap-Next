# Preliminary independent C1 evidence and continuation review

**Disposition: the corrected-contract continuation is scientifically defensible, with one named trusted-planner finding to resolve before replacement execution. This is a preliminary evidence audit, not final acceptance.**

Snapshot: 2026-11-10 20:50:01 UTC. Trusted main: `13c3195eebd96698002237f2b6d8560b031029fc`.
Reviewer: `final_independent_review`, independent of implementation. All inspection and native evidence replay ran over SSH on the designated Linux worker. The only reviewer write is this file.

## Verified outcome

The original C1 contract is infrastructure-incomplete. It spent **3 guests and 3 builds**. Both baseline builds pass current native build validation; the candidate debug build compiled successfully but fails its required final configuration. No candidate guest, correctness matrix, probe calibration, fast calibration, or candidate timing result exists in this campaign.

| Item | Independently verified result | Primary evidence |
|---|---|---|
| Baseline common build | Native configured-build validation passes | `benchmark/kernel/builds/c1-base-common-20261110/result.json` and `configured-build.json`; ledger evaluation `3868cc40b0944c8f9b13b3aa529b5005` |
| Baseline legacy build | Native configured-build validation passes | `benchmark/kernel/builds/c1-5e84ca928dee-legacy/result.json` and `configured-build.json`; ledger evaluation `4894c2e365c1463292ae02dd5914fffd` |
| Candidate debug build | Compiler exit 0; native configured-build validation rejects `required final CONFIG_KASAN=y missing` | `benchmark/kernel/builds/c1-7d5a3cfab2ab-debug/`; ledger evaluation `6be443dc6e384b909ef8dd544f9e7211` |
| `c1-b-common-001` | Retained invalid baseline; sole failed raw gate is `configuration_identity`; blank `ONLINE_NODES` | Original result/serial/reservation plus explicit infrastructure supersession |
| `c1-b-common-002` | Native serial/provenance replay returns `CORRECTNESS_PASS` | Corrected `ONLINE_NODES flat`; same baseline build and counted replacement |
| `c1-b-legacy-001` | Native serial/provenance replay returns `CORRECTNESS_PASS` | 8,192 nonzero pages stored; 4,194,304 words verified; objects and charges drained |

The debug failure is explained by the actual inputs and target Kconfig, with high confidence: frozen `benchmark/config/compression-debug.config:829` sets `CONFIG_SLUB_TINY=y`, while lines 2424–2427 request KASAN. The candidate's `lib/Kconfig.kasan:52` requires `SYSFS && !SLUB_TINY`. Its final `output/.config:867` still enables SLUB_TINY and contains no enabled KASAN. A corrected build with every required final symbol verified would change this coverage conclusion. The compiler logs for these three builds contain no matches for warning, error, fatal, or undefined-reference diagnostics.

## PRELIM-C1-001 — Required guest-configuration build failure remains pending

**Priority: P2. Confidence: high. Status: unresolved at `13c3195`.**

Trigger: a required guest configuration has a retained, counted `BUILD_FAILED` outcome before any guest for that case has launched.

At `evolve/control/correctness_proof.py:653–669`, `matrix_progress()` checks build ledger outcomes only for `matrix["build_only"]`. It omits the required guest-configuration build outcomes. The actual retained `c-debug` failure therefore produced this native read-only replay:

```json
{
  "passed": false,
  "failed": false,
  "attempted": true,
  "pending": true,
  "verified_cases": ["b-common", "b-legacy"],
  "next_missing_case": "c-common",
  "reason": "Complete the next frozen matrix case; existing successful coverage is retained."
}
```

`evolve/session.py:280–286` consequently permits another correctness action. This can spend more resources in an already unsatisfiable frozen matrix and obscures its real blocker. `evolve/standard_workflow.py:652–655` independently refuses a repeated build of the failed configuration, and final configuration validation still rejects missing KASAN; no false correctness pass or erased spend was observed.

**Required resolution:** bind required guest-build outcomes to the exact source/configuration in matrix progress and stop progression on retained failed, interrupted, or incomplete execution outcomes. Preserve missing/unattempted cases as pending and successful partial coverage as reusable. Report infrastructure coverage failure separately from candidate runtime correctness failure. Demonstrate the correction against this retained row and suitable guest-free regression fixtures, recording the exact trusted revision.

The coordinator's explicit stop decision mitigates the current instance. At the snapshot, the durable action is `close-candidate`, and the campaign remains open. This review does not claim closeout has executed.

## Integrity of the inspected trusted corrections

**High confidence:** the flat-topology recovery preserves the failed observation and supplies a narrowly bounded new observation.

Native `correctness_proof._infra_supersessions()` verified the archived original image/harness, original raw result, serial log, reservation, exact baseline build/configuration, declared replacement identity, declaration-before-retry ordering, and replacement runtime. Its invalid result remains `BASELINE_INFRA_INVALID`, with `passed=false`. The diagnostic substitution is in memory only and never supplies a passed observation.

The current observer fails on unreadable/empty NUMA topology, emits `flat` only for absent node sysfs with single topology, and the parser permits it only for the designated non-NUMA configurations. Current configuration validation requires explicit final `NUMA=n`. Multi-node/debug identity remains strict.

**High confidence:** the checkpatch correction is an administrative classification with retained evidence. The original raw rejection remains present; both current raw checks contain exactly one `FILE_PATH_CHANGES` warning for three allowed additions. The filtered rerun reports zero diagnostics. The code first validates cumulative path scope, requires this exact single diagnostic, retains raw/filtered logs, and binds the executed checker identities. No unrelated warning or error was waived in the inspected candidate.

The partial-matrix change correctly preserves passing cases and still leaves `passed=false` until complete coverage. PRELIM-C1-001 is its concrete remaining continuation gap.

## Identity, evidence retention, and replacement contract

The exact candidate is unchanged:

- Commit: `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`.
- Tree: `8b085adc109e3b5467c3de998f11b04517f052a5`.
- Original anchor: `5e84ca928deeacb4eee656806a003f27d1eca82f`.
- Retained patch SHA-256: `69e085f0b3703ae2929c0cc8e863b6f606fce1b15e8a4d3ab3fd378ef785f704`; byte-identical to the exact base/head diff.
- Candidate worktree is clean; `linux/` remains at `744e5400b36f84b4816e3ff8531ec2dff52b474c`.

The original protocol SHA-256 is `62f82170cbdc317605f08f6289708d807db63748590c30ee0fc5b34218ed1426`. Its bytes and all six frozen configuration files match commit `7abfe80`.

I verified all **28/28** files in `campaigns/codex-compress-lib-2026-11-10/runs/closeout-runtime/archive.json` against the archived bytes. Its image manifest and harness hashes match both passing baseline raw records. The separate original-invalid runtime archive also passed the native supersession replay. These archives and the original Git revisions are necessary for historical replay after trusted code changes.

The concrete [replacement contract](C1-replacement-contract.json), SHA-256 `2937c1739003f7c31a3f9e39c93ce29086fd763f029323eb89b4dfe9bc778f25`, preserves the same logical C1 and candidate tree:

| Resource | Original C1 cap | Retained spend | Maximum replacement allowance |
|---|---:|---:|---:|
| Probe/correctness guests | 32 | 3 | 29 |
| Fast guests | 88 | 0 | 88 |
| All guests | 120 | 3 | 117 |
| Builds | 10 | 3 | 7 |

The clock authority is the original enforced `budget.created=1794340417.3836553`, with absolute deadline **2026-11-11 13:53:37.383655 UTC**. Session preparation started at 2026-11-10 19:02:55.969091 UTC; the contract discloses the distinction. Native workflow and guest reservation guards currently use the budget clock. The replacement must satisfy `actual_budget_created + frozen_wall_seconds <= 1794405217.3836553`; computing a duration before delayed creation is insufficient.

The contract's arithmetic preserves the 360-guest/30-build family ceiling and C1's original resources. Enforcement remains to be verified against the actual frozen replacement protocol, its line admission, and created budget. It must remain one logical hypothesis, with no new population success or candidate outcome inferred from opening a new directory.

Both baseline builds currently satisfy native reuse checks, including source tree, input/final configuration, image, toolchain/builder identity, source protocol, ledger, and original counted cost. Revalidate after integration. Reuse only the builds; rerun the complete corrected correctness matrix and all calibration/comparison observations under the replacement identity. The declared plan needs 108 fresh guests and six new candidate configuration builds if both baseline builds remain reusable, giving cumulative totals of 111 guests and nine builds before additional invalid attempts.

## Preconditions for replacement execution

1. Complete explicit infrastructure closeout of original C1, retaining every failed/invalid record, raw archive, and counted cost.
2. Resolve PRELIM-C1-001 at an exact trusted revision; do not convert infrastructure failure into a candidate runtime verdict.
3. Add a separate corrected debug configuration and frozen replacement protocol. Preserve original configuration/protocol bytes and retain every mandatory sanitizer, lifecycle, disabled-build, and topology requirement.
4. Verify the actual reduced pools, build ceiling, absolute deadline, exact same K1 tree, baseline reuse provenance, and current review disposition before a build or guest.
5. Complete fresh corrected matrix and calibration. Subsequent dependent phases still require their own evidence and remain within the approved family budget.

## Evidence index

All campaign-relative paths below use `campaigns/codex-compress-lib-2026-11-10/`.

| Evidence | SHA-256 / location |
|---|---|
| Guest/build spend and outcomes | `ledger/budget.json`, `ledger/ledger.json`, three `ledger/guest-reservations/*.json`, three `runs/evaluations/*/report.json` |
| Invalid common raw result | `runs/guests/c1-b-common-001/result.json`: `5076e03403000c191c77338785c38d60e7bf98b1941162059ad39d42acfedb0d` |
| Corrected common raw result | `runs/guests/c1-b-common-002/result.json`: `ac6efb4096b6361f064626fd2a68fe8d6f8e80fa23e834c1cd393c7191b45064` |
| Legacy raw result | `runs/guests/c1-b-legacy-001/result.json`: `e80ead65e8fcb02e8c37744f14ff884b95afdd5d8a6c54f10a7e47d7d91a5658` |
| Explicit baseline supersession | `ledger/baseline-infra-supersessions/c1-b-common-001.json`: `8a7a9b4614c0b6336df8d8eda0759747f35f82a17f2bdcd96a73e912e40dd273` |
| Current exact checker evidence | `candidates/c1-shared-store-v1/static/1794343006122714768-698cdc19297a/` |
| Coordinator stop decision/current action | `ledger/session-inputs/stop-invalid-debug-contract.json`, `ledger/session.json` |
| Original phase lifetime ceiling | `campaigns/lines/xswap-compression-tiering.json:16–19`; line aggregation/admission in `evolve/research.py:404–426` and `evolve/control/controller.py:683–687` |

## Limitations

This preliminary review inspected live evidence, relevant trusted validation changes, exact source/patch identities, and the KASAN dependency. It replayed native read-only build, raw-result, supersession, and matrix-progress validators. It did not perform a full independent K1 lifetime/source review, execute the test suite, build a kernel, start a guest, change campaign state, inspect unfinished H8 implementation, push, publish, or accept any candidate. No build or guest process was observed during the process check; coordinator closeout was active separately. No reviewer process remains running. Final acceptance requires review of integrated revisions and the resulting complete evidence.
