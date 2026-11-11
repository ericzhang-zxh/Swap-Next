# H27: first-failure trace diagnostic admission review

Status: **H26 source review PASS; R6 closed without runtime admission; closeout audit PASS**. Confidence: high for the inspected implementation, unchanged source bytes and verified closeout state. Final R6 admission was never completed, and no R6 guest was launched.

Authority: [H27 ticket](tickets/H27.json). The final closeout disposition below supersedes that ticket's pre-closeout admission snapshot. Source rationale is [H25](H25-timing-observer-diagnosis.md); the retained failed R5 outcome is [incident 006](runtime-incident-006.md).

## Exact source reviewed

| Item | Identity |
| --- | --- |
| H26 implementation | `454b6f45aa89a9dddff0d5c6e00a5dcd6ac7fd83` |
| Integrated implementation | `d82bd89647e73ade587de05f731cb6a503d1d2d7` |
| Implementation diff SHA-256 | `c8e45a340ecc6dea5d21d3795033a70fbf6f886abdea270d12a90b5cbf494436` |
| `swapin.c` SHA-256 | `26080a666441fed1b0b66d59f9f205e621a5cc734e1cccd785106ee281e577a9` |
| `test_compression_evidence.py` SHA-256 | `da67197dbd718b6ef6c1664a639636c72779ddecb8318832d11da7f15fce94c2` |

Only those two files change. Their current bytes equal both the isolated H26 and integrated commit blobs. The full source and test diff has been reviewed, and independent `git diff --check` passes.

## Source findings

No blocking finding remains. The following checks were independently established by source inspection and read-only exact comparisons:

- The first trace read retains the original 32 KiB capacity and the same open/read/EOF/error/limit decisions. Partial data is NUL-terminated inside the buffer, and its actual returned byte count is retained even on read failure. An exactly exhausted capacity still fails conservatively.
- The parser traverses the same nonempty newline-delimited strings as the old predicate, preserving C-string treatment of embedded NUL. It uses the same header and return conversions and the same exact-one header/entry/written/record and zero-return conditions. Every temporarily replaced separator is restored on normal advancement and early rejection. Its extra state records prefix counts, scan completeness, bad-record offset/length and the converted return; it does not introduce a successful rejection path.
- Failure output uses that same restored first-read buffer and its recorded byte count. No later trace read can substitute for it. Hex encoding retains binary/NUL/carriage-return bytes through the serial channel. The one-shot guard precedes emission; the workload still returns failure after the dump.
- The tracing-disable request occurs only after rejection and reports its own outcome. All eight fixed readbacks and per-CPU stats are explicitly post-failure. Each readback is limited to 4095 payload bytes; CPU enumeration is capped at 64, with out-of-range enumeration and read truncation visible. This bounds payloads and keeps later state distinct from the original observation.
- Setup, the PID filter, kretprobe registration, target-readiness/reclaim logic and all code from `probe_misses()` through the end of `main()` compare byte for byte with pre-H26 source after normalizing only the two new diagnostic order/index arguments. The target size, sample selection/order, clock and `t0 / volatile touch / t1` source interval are unchanged. Successful observations neither dump diagnostics nor change tracing state.
- The `TRACE_ROOT` compile-time override is a temporary-filesystem fixture hook. The guest's default path and guest-only setup marker remain unchanged. No runtime root-cause fix, observer isolation or acceptance relaxation is introduced.

The new tests exercise failure reasons, exact retained bytes, partial EINTR reads, open/read/limit failures, output bounds, one-shot behavior, failed-disable reporting and silent success. Their embedded legacy predicate matches the pre-H26 source predicate. H26's 306 valid/mutated trace comparisons are synthetic decision-equivalence evidence. The coordinator's retained main-suite log reports **179 tests, OK, no skips**; H27 inspected that log but did not compile or rerun tests.

The diagnostic image can change observer code layout or stack use even with the same source timing interval. A reproduced first-failure trace will be evidence for its own exact harness; the old R5 cause remains unproven until reconciled against the new observation. This boundary is preserved by the diagnostic-only contract.

## Prepared R6 plan (not executed)

Preparation established passing native configuration validation and the standard workflow's contract check: all eight correctness cases, two disabled-build cases and the approved profile remained intact. The capability readout had no missing capability and carried no independent launch authority.

The prepared plan retained timing cases, thresholds, validity, configuration pins, observer contract and NUMA identities. It narrowed execution to eight fresh native correctness guests on the diagnostic image, followed by exactly one original-baseline compressed diagnostic. No accepted calibration, candidate timing, fast run or new kernel build was planned. The positive unused one-fast/one-build caps were schema minima. None of the planned guests ran.

Final admission required complete frozen/native/image binding before launch. That review was interrupted before completion, and the frozen R6 deadline elapsed. R6's caps remain nine probe, one unused fast, one unused build and 3600 seconds, bounded by the earlier R5 deadline. The old R5 correctness proof remains historical evidence; the diagnostic image's fresh full native correctness gate was never executed.

## Preparation checks completed before freeze

All five old protocol and budget hashes match the draft continuation. Native closed state, reservation counts and counted build ledger rows independently reproduce Original C1/R2/R3/R4/R5 costs of `3/3`, `2/1`, `3/0`, `2/0` and `9/5` guests/builds: **nineteen guests and nine builds**. All five campaign STOP files remain absent, with closure enforced by their closed state.

All eight distinct reusable artifacts pass native `verify_build_binding` and `_configured_build` against the unchanged draft configuration pins and current builder/toolchain identity. These checks include actual final-config and kernel-image bytes plus original counted provenance; they perform no compilation and create no new coverage record.

| Reusable build | Manifest SHA-256 |
| --- | --- |
| `c1-base-common-20261110` | `8f15f75eb6ae661d7531f99392902ae184e1f58d04989064d5098f8db8c0a5b2` |
| `c1-5e84ca928dee-legacy` | `ddac55cc53053dae857517e7c3f0dffd0815f61f89c5e5c92051e990ecdcb2cc` |
| `c1-7d5a3cfab2ab-debug-v2` | `d27ba832157cc32c334d3ecf9decdf7d18e90c2438dfa857ad61656e0fd1b6ff` |
| `c1-7d5a3cfab2ab-common` | `4e59c3c5dad923edb29027ed555b1fab18f23c8fd0dce86ad80abd1017329216` |
| `c1-7d5a3cfab2ab-legacy` | `3bb5f7fe6ab35e642ec57667f19c95e61b2c3e814af460c4fc60a3259ffaae1c` |
| `c1-7d5a3cfab2ab-kcsan` | `f38a715c8df0424aaef5d3ff609fb825f8e860cba2f3bdd65962cfe66b9cb71a` |
| `c1-7d5a3cfab2ab-noswap` | `d08d6aaee0576169527a23e38462728a0065430960056447f8260452e7575bf6` |
| `c1-7d5a3cfab2ab-no-frontends` | `5b5def31917e8673cf19c78ee3a76cf2dc8fa304b2e2c263561f58f76b2f72f4` |

The baseline pair retains Original C1 counted identities, debug-v2 retains R2, and the other five retain R5. The common and debug builds cover multiple matrix rows, yielding eight distinct build artifacts for eight guest rows plus two disabled-build rows. These are preparation checks; they yielded no H27 runtime admission.

## Final closeout audit

Read-only verification on **2026-11-11 at 09:08 UTC** establishes a closed runtime boundary. The native [campaign record](../../../campaigns/codex-compress-lib-r6-2026-11-10/campaign.json) and [candidate record](../../../campaigns/codex-compress-lib-r6-2026-11-10/candidates/c1-shared-store-r6.json) are closed. The [session closeout](../../../campaigns/codex-compress-lib-r6-2026-11-10/ledger/session-closeout.json) retains the deadline-exhausted reason, completed native close-candidate and close-campaign actions with return code zero, and false performance-acceptance and automatic-promotion fields. The machine claim is absent; its native release log names R6 and the same reason. The recorded execution process identities are no longer live, and the read-only process scan found no R6 or QEMU runtime process.

The frozen protocol, policy and continuation bytes match commit `dc0027fb76b1adc008c493b0f84208c11e711102` and the ticket hashes. The budget, initial reservation, source/static/review and image-manifest pins remain unchanged. The campaign-record hash changed with native closure. Budget creation remains `1794354546.1003957`; the unchanged 3600-second cap yields deadline `1794358146.1003957` (**2026-11-11 00:49:06 UTC**), earlier than the retained R5 deadline. No deadline extension or budget reset occurred.

The only R6 guest reservation, `c1r6-b-common-001`, remains `RESERVED`, with no launch marker. The R6 ledger contains ten verified build-coverage rows for eight reused artifacts, all with `build_reserved: false`; it contains no guest execution. The campaign has no raw guest runtime directory or correctness/calibration result. The unlaunched reservation stays counted.

| C1 segment | Counted reservations | Launched reservations | Counted builds |
| --- | ---: | ---: | ---: |
| Original | 3 | 3 | 3 |
| R2 | 2 | 2 | 1 |
| R3 | 3 | 3 | 0 |
| R4 | 2 | 2 | 0 |
| R5 | 9 | 9 | 5 |
| R6 | 1 | 0 | 0 |
| **C1 total** | **20** | **19** | **9** |

The five old protocol and budget hashes still match the continuation pins. Each earlier launched reservation remains `STARTED`; this column counts launches, not successful outcomes. The totals stay within the original 120-guest/10-build phase caps. R6 contributes preparation and one retained reservation, with zero new kernel builds or runtime samples.

| Closeout evidence | SHA-256 |
| --- | --- |
| `campaign.json` | `f17055b04c058d65a587dc921e2b21ba1994110f225efcb050ec09803035cd20` |
| `ledger/budget.json` | `985b39c79d5fbb0f2f7d471679458e8c3c4906ff35fbfa378b91796654d7baf2` |
| `ledger/session-closeout.json` | `da454685e5bafdce9cc0fc837a2000179bfb8c703a53f3c4249f98bea8a263b9` |
| `candidates/c1-shared-store-r6.json` | `574e9e5028fbd1a24b6854af77e3946fb3e6057563f2d664ba6f63723d92edc8` |
| Initial reservation | `986349a697dd92262afd5c43feb44b36c685f72941f15718aa51f3745a44642d` |

The native session remains active at the agent-owned `explain` delivery stage with `closed: true` and `claim: null`. Runtime closeout is verified; report delivery is still outstanding and is outside this audit.

## Limitations

H27 only updated this review document. It did not compile or rerun tests, build a kernel, operate an image or guest, probe runtime, change campaign state, commit, push, publish or delegate. The H26 source PASS is retained against unchanged file hashes; final runtime admission was never completed. Live first-failure trace capture and full fresh correctness on the diagnostic image remain unmeasured. R5 correctness remains its separately retained historical result, and its timing work remains incomplete. Reopen the source review for changed implementation bytes or evidence of altered decisions, corrupted first-read capture, unbounded output or successful-path diagnostics. Reopen the closeout finding if a launch marker, runtime artifact, changed budget/deadline or live owned execution contradicts the recorded boundary.
