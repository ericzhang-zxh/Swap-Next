# H29: revision-9 timing observer

Status: **isolated implementation and fixture verification complete; runtime admission pending**. Confidence is high for the inspected source, exact wire compatibility and guest-free checks. Commit 9192dde921b4e07bc73c7c5a8099b2d2d2bb91c9 is ready for coordinator integration and independent review. Nothing from H29 remains running.

Authority: [H29 ticket](tickets/H29.json), [coordinator decisions](C2-coordinator-decisions.md) and [wire contract](C2-wire-contract.md). The original R5 timing cause remains unproven, and R6 remains expired and unlaunched.

## Exact delivery

| Item | Identity |
| --- | --- |
| Branch | infra/c2-timing-observer-01a1c6b6 |
| Worktree | worktrees/framework-c2-timing-observer-01a1c6b6 |
| Base | dc0027fb76b1adc008c493b0f84208c11e711102 |
| Commit | 9192dde921b4e07bc73c7c5a8099b2d2d2bb91c9 |
| Binary diff SHA-256 from base | 6cd16a0435cd8ceee9e1b1f7f9dd4b615726df437225e464c52d329d9579f561 |
| swapin.c SHA-256 | ef22f63908aa733b6b561e4d753be4963596c9bcf62a9ec7741fbee7793615d9 |
| test_c2_timing_observer.py SHA-256 | 0d3f211c3c9aff862bc4d8fe18d33350a14acbb817f8d44b1c285671dd3786c7 |

The commit changes only the two owned implementation/test files, uses Eric Zhang <zxh@xh-zhang.com>, and contains no DCO sign-off. The worktree is clean. This shared result is separate from the isolated implementation commit.

## Source feasibility and implemented behavior

At exact anchor A, 5e84ca928deeacb4eee656806a003f27d1eca82f, mm/mlock.c sets current/future VM_LOCKED through apply_mlockall_flags, explicitly ignores individual mlock_fixup errors, and uses apply_vma_lock_flags to split/unlock the exact target range. fs/proc/task_mmu.c exposes actual VM_LOCKED as smaps lo. Source feasibility passes; syscall success alone cannot satisfy the implemented proof.

The new argc11 path retains the old six arguments, then requires xswap-independent-v1 ROLE FULL_SOURCE_SHA pid_kretprobe_frontend_v2 FRONTEND. A must name the exact anchor and legacy frontend; C must name a distinct full lowercase source SHA and independent frontend. Arguments are cross-checked against the actual launched command line. Symbol selection has no environment or fallback path.

A uses zswap_load and C uses xswap_load_folio. Both retain r64, signed zero return, the current PID filter, a 16 KiB trace buffer and monotonic-raw timing. Eight raw setup readbacks verify the actual registration, filter, tracer, buffer size, enable state, field format and supported rendering options. The raw text preserves exact bytes in bounded hex.

After allocating and filling the target and control data, revision 9 calls mlockall(MCL_CURRENT|MCL_FUTURE), then munlock only for the exact 128 MiB target. Actual smaps bytes before reclaim and after measurement prove complete, contiguous, unlocked anonymous rw-p target coverage, base-page sizes, no huge-page residence and the no-huge-page flag. Every accessible private observer VMA must have lo and no lf; only exact vvar, vvar_vclock, vdso and vsyscall kernel names are exempt. Unknown accessible shared mappings, duplicate/malformed fields, gaps, syscall failure and missing readback fail closed. Headers and VmFlags agree. The source records locked mapping/resident bytes and target unlocked bytes.

A reads actual legacy codec, cap, shrinker and limit/writeback/poor-compression counters at before/stored/after. C retains the unchanged schema-1 raw frontend snapshots at those phases, validates full key order, generation/pool/driver continuity, quiescence, compressed stored lengths, ownership/charge balances, zero raw admission, nonbinding finite cap and zero physical traffic. Its normalized STATE fields derive compressed_live, pool_backing_pages*4096 and raw_live.

The observer has a 256 KiB static smaps buffer that becomes locked with the other observer mappings in both arms. Actual retained memory is reported by each smaps proof; guest setup/pinning cost remains unmeasured. The temporary whole-process lock also touches the target before reclaim and then unlocks it. No target warming was added after reclaim.

## Verification

- gcc -O2 -Wall -Wextra -Werror -fsyntax-only and git diff --check pass.
- The complete isolated swap-standard suite reports **204 tests, OK, one skip**. The skip is the existing real-commit test requiring a linux checkout inside the worktree. That exact test separately passes from the main checkout using unchanged runner/test source and the actual kernel object store. The new H29 file contributes **25 passing test methods**, including adversarial subcases.
- Fixtures cover exact source arguments/command line, matched registration and readbacks, both frontend routes, canonical counters, raw snapshot identities/balances, complete smaps coverage, unlocked-observer/locked-target refusal, truncation and injected lock/unlock failures. Both lock syscalls are replaced at compile time; the fixture binary has no undefined mlockall/munlock symbol. No host pinning experiment runs.
- Actual C-emitted fixture readbacks, both isolation envelopes, and candidate snapshots or baseline policy records replay through the current H24 host parser. **Both A and C pass all 25 host gates** for that synthetic replay. The replay checks unchanged before/after source hashes; it is fixture integration evidence.
- Byte comparisons against the base confirm target_ready, the complete H26 trace/loss/topology section, data/selection/clock/report helpers and both timed loops plus fixed shuffle are unchanged. The t0/touch/t1 intervals, target data, eligibility, sample selection and exact-one/no-loss predicate are preserved.

Relevant commands:

    python3 -m unittest discover -s benchmark/swap-standard -p 'test_*.py' -v
    python3 -m unittest test_runner.RunnerValidationTests.test_lifetime_fix_check_needs_a_real_commit -v
    python3 campaigns/codex-compress-lib-r6-2026-11-10/runs/control/c2-preparation/h29-c2-wire-replay.py

The second command was run from the main benchmark/swap-standard directory solely to cover the isolated worktree's skipped read-only check.

| Retained local check artifact | SHA-256 |
| --- | --- |
| campaigns/codex-compress-lib-r6-2026-11-10/runs/control/c2-preparation/h29-swap-standard-tests.log | c6b1df7144404d7cf55ad54f181ba7375545ebbbb4c7a5115d1d683d90141fa6 |
| campaigns/codex-compress-lib-r6-2026-11-10/runs/control/c2-preparation/h29-c2-wire-replay.py | 0c8b0918dcca053f38f5f10dee2b84b7d4329296e0d7c00ddebd205fc943d43a |
| campaigns/codex-compress-lib-r6-2026-11-10/runs/control/c2-preparation/h29-c2-wire-replay.log | bea2d712d2c7da906838f093176de0a6659c93b42c585cebaaeaeb6c29cb0a80 |
| campaigns/codex-compress-lib-r6-2026-11-10/runs/control/c2-preparation/h29-preservation.json | 55e05c74c757f3e0ae8e18096d48d23124f2569a5f9bd4fe086149950da59b1e |

The cross-parser replay binds H24 evidence.py SHA-256 907bcb2bf0e9518d913b5d7dca89ae7f24145e4b7134ef6cbb2b7fcbb65ae1a5, configurations.py b31883e142ac650360e63842b8d46ea9b5ce1f6e7f49aebb7905210131b73c0d and test_c2_evidence.py 5a407d361eef999b9b563f94bd3316fd402cab1762981cb5e3bcb4e296238447.

## Limitations and remaining admission

No kernel source edit/build, guest image, VM, host pinning experiment, host configuration change, main implementation edit, push, delegation or campaign-state mutation occurred. Fixture readbacks do not establish actual guest isolation, decode behavior, timing calibration or a speedup. Old argc3/argc6 paths and H26 failure capture remain available; no old sample is rescored.

Coordinator integration, fresh independent review, complete capability and correctness gates, and a separately frozen, independently admitted revision-9 runtime contract remain outstanding. H28 shell files are outside this delivery and were not taken over. Reopen this source/fixture finding if implementation bytes change, host replay fails, or live evidence contradicts source-role binding, mapping isolation, exact decode cardinality or retained memory assumptions.

## H30 fixture follow-up

Commit 66177c9420648afd1e5b1bc8723fde3b6991db58 corrects the nonblocking fixture defect reported after original implementation integration ee8c28f. The original negative legacy-counter strings contained literal backslash-n bytes and therefore failed the newline read boundary. They now contain actual newline terminators.

For each of the three counters, the fixture explicitly confirms that the actual file passes c2_read before the same file is rejected by debug_number's canonical decimal path. Canonical zero and U64_MAX controls both pass and return their exact values. The five invalid forms per counter cover negative/sign-prefixed input, a leading zero, u64 overflow and an extra field. The full legacy policy path also rejects each invalid form.

Focused verification: **25 tests, OK**, plus git diff --check. Only test_c2_timing_observer.py changes; production swapin.c remains byte-identical at SHA-256 ef22f63908aa733b6b561e4d753be4963596c9bcf62a9ec7741fbee7793615d9. The new test file SHA-256 is d058c2da2a34a258f88b43a1bc1576b8322036726a873e41ed5fb32cf02c9a02. The retained receipt campaigns/codex-compress-lib-r6-2026-11-10/runs/control/c2-preparation/h29-counter-fixture-followup.log has SHA-256 2b1232ecef14f61d1b6a0c8616f2349491dbb4f8e52f2f7bdd0a6e66ba1355dc. The earlier complete-suite and cross-parser receipts remain tied to their original file hashes; this follow-up adds focused evidence for the corrected validation branch.

The isolated worktree is clean. No new scope, kernel/image/VM execution, host pinning experiment, main integration, push or H28 takeover occurred. Nothing remains running.
