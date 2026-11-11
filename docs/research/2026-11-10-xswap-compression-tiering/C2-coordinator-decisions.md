# C2 pre-freeze coordinator decisions

Status: preparation only. These decisions refine the authorized independent-XSwap scope; C2 activation and runtime still require complete C1 correctness and independently reviewed native capability. The kernel and capability workers must report an unimplementable requirement before weakening it.

## Admission and physical-path policy

Use allocator backing pages as the admission-cap unit, not compressed-byte charges. The default finite cap is 20 percent of total guest RAM pages, matching the existing ZSwap pool-percent policy for the common comparison. Record the effective page limit, actual library backing pages, stored lengths, metadata and charge bytes separately. The compressed timing target remains 128 MiB; both arms must show zero cap rejection and zero physical fallback. The cap is nonbinding for that measurement, and no result may claim exact equality of total memory footprint from matching percentages.

A per-device cap of zero is the explicit physical-case bypass. It must return FALLBACK before compressed/raw object publication, with readback before allocation and zero independent object/decode deltas. It changes admission only and does not evict live objects. Existing objects remain readable after a cap change. No C3 pressure or writeback policy is implied.

Do not admit PAGE_SIZE raw copies in the first independent frontend. Incompressible input takes declared physical fallback; without eligible backing, retain/redirty the authoritative locked input through the existing caller contract. Verify bounded retention and correct data. Zero pages and library-level raw representations remain separately classified and cannot satisfy compressed decoder evidence.

## Failure and race evidence

Add a dedicated internal default-off XSwap test configuration if needed. Preserve every C1 input byte: derive new immutable debug-common and race-common inputs in addition to the three independent inputs when enabling the new test symbol. This still uses nine candidate source/configuration builds. Keep performance/common input free of active test hooks. Hooks must be per-device/generation, once-only, resettable and compiled only for the intended debug/race configurations.

Injected refusal at the frontend generic-charge boundary is sufficient for the frontend rollback test when it reaches the same checked error branch and is explicitly labeled injected. Successful real obj_cgroup_charge/uncharge activity with ZSWAP=n remains mandatory. Record whether the core call was attempted and its actual return; never report an injected refusal as a natural core failure. This contract makes no claim of naturally failing core charge allocation or a strict independent compressed-byte quota.

Physical-error coverage must execute the actual bio completion owner. A narrowly targeted debug-only completion-status injection is acceptable when it binds the real request to device generation, logical/physical key and direction, records the original and injected status, and proves the actual redirty/not-uptodate and writeback-end/unlock paths. A submission refusal or counter-only mock is insufficient. Label it an injected completion error, not a demonstrated storage-device fault. Preserve an authoritative copy and verify recovery after the once-only injection clears.

Allocation, publication, partial-folio rollback, decode-over-old-backing and reuse/lifetime cases retain the full validation-contract requirements. Test hooks cannot fabricate a higher-order input, physical association, completed fault, overlap or cleanup. Deterministic barriers must be lock-safe, bounded and observable; no waiting while holding a spinlock or disabling scheduler/watchdog checks.

## Comparison and value boundary

Freeze revision 9 and a narrow independent-XSwap profile only after its real adapters and adversarial checks exist. Keep A=5e84ca928deeacb4eee656806a003f27d1eca82f as the native baseline/parent and preserve K=7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad as exact predecessor provenance. Review the full A-to-C source and the incremental K-to-C mechanism separately. A versus C is the cumulative instrumented timing comparison; no marginal C2 speedup over K is measured by it.

The practical capability criterion is actual compressed operation, real accounting and balanced lifecycle with ZSWAP=n, plus preserved coexistence and physical fallback. Keep sequential compressed swap-in mean primary and existing random/disk/zram guards, noise limits and fresh calibration. Functional independence can be reported when its complete evidence passes; a noisy timing tier remains inconclusive for speed or equivalence. Significant measured regression stops advancement. A neutral exploratory screen does not advance the cross-campaign baseline or promote code.

C3 source planning may use retained C2 knowledge. Its execution requires complete C2 correctness and an explicitly reviewed selected-target/writeback/pressure contract. No new public cgroup ABI, reinterpretation of memory.zswap controls, host change, slow tier or promotion is introduced here.

## Resource preconditions

The complete proposed C2 allocation is twelve correctness guests, sixteen probe guests and eighty-four fast guests: 112 planned within 120. Nine candidate configuration builds and one typed expected-negative anchor build consume ten. Native reuse of unchanged A/common and A/legacy builds is required before opening. New inputs or test symbols do not create additional build slots. No failed or interrupted attempt is erased, and no untested subcase is marked complete because it shares a guest.

Confidence is high in these accounting and evidence boundaries, while hook feasibility and the grouped 900-second runtime remain unmeasured. The next acceptance artifact is an exact native capability implementation and independent review, after C1's dependency gate.

## Bounded first-candidate stores

The first C2 implementation uses one nonblocking store token per frontend, held across the complete folio store, per-subpage allocation/cap checks/publication and rollback. Contention returns RETRY with the locked input still authoritative. It never waits for the token or holds a sleepable serialization lock across recursive reclaim. This bounds unpublished store work without relying on the library per-CPU mutex, which protects only a single base-page codec operation.

The implementation review must derive transient backing-page headroom from the actual allocator chain bound and delayed release behavior. A cap check occurs after each real allocation and before publication; a breach rolls back unpublished work. This choice may reduce concurrent write-side throughput and is an explicit prototype cost to measure, not a free simplification. Required race observations may prove intersecting entered operations and refusal, but may not describe serialized stores as simultaneous mutation.

## Real-path diagnostic preparation and scalar lifetime

The old-physical decode test may use a debug-only retained-folio setup. A once-only hook takes an extra folio reference after actual physical pageout eligibility; it observes a real successful BIO completion. A same-open control operation then waits writeback in process context, locks and revalidates the exact device generation/logical key, unmapped folio and positive real swap count, writes a deterministic new data generation, and calls the real swap_writeout path. The test requires compressed publication without a second physical write, then releases the pin and uses normal reclaim before the injected demand fault. No PTE, physical-table or accounting fabrication is permitted. Report this as coordinated debug preparation. Close/cancel/timeout drains the actual pins; an in-flight rewrite owns its reference and observes cancellation.

BIO completion hooks retain only scalar operation metadata after the existing owner may release folio lifetime. Record actual redirty/uptodate/end-writeback/unlock/owner-return transitions in order; never dereference the folio after an unlocking/release transition without a separately valid pin. Legacy overlap identifies a real old-pool release worker and actual memcg offline interval with explicit ordinary-device epoch/pool/owner. It does not claim overlap with an object whose reference prevents that same pool's release.

With one store token, pre-allocation registered backing B<C and per-subpage cap checks, one zsmalloc allocation adds at most the configured chain bound M. The conservative registered-pool bound is C+M; cap lowering retains existing B0 and therefore yields max(B0,C+M). Deferred-free chains remain counted until real release and block further admission when B>=C. This bounds registered pool pages, not all instantaneous physical allocations or unrelated allocator migration overhead.

Diagnostic-reference drain failures must return through the existing re-enable path before device users are killed. After users and handles are drained, a bounded allocator-page-zero poll may support a real last live snapshot. A timeout retains the observed nonzero value and makes teardown evidence incomplete; the actual destructor can still flush deferred frees safely. Never reinsert a device after killing users or fabricate a post-destroy zero read.

## Pre-freeze debug-coverage placement correction

The non-test independent configuration cannot emit targeted operation-owner events. Move the complete `incompressible_control`, `no_target_retention` and `swap_charge_denied` phases to the existing `debug-independent` group, where CONFIG_XSWAP_TEST is enabled. Preserve every event, retention, lock, data and cleanup predicate. The ordinary independent group retains its real positive and zero controls; the ordinary fallback group retains cap, incompressible physical fallback and physical roundtrip. This changes only the unfrozen C2 phase placement, with the same twelve correctness boots and nine candidate configurations. No test symbol is added to performance/common configurations, and no new build is introduced.

The retained-folio rewrite uses one base page and the existing trusted `word_pattern(0, word, generation)` formula. For unsigned 64-bit words: stamp is 0xa5c31f7200000001 XOR (generation shifted left by 40); word zero is stamp, word one is its complement, and every later word is 0x636f6d7072657373 XOR (generation times 0x0101010101010101), with unsigned 64-bit arithmetic. The kernel test hook and guest verifier must implement the same documented formula, retaining actual V0 physical completion and V1 compressed publication provenance.

## Revision-9 observer isolation

The first-failure C1 diagnostic contract expired before guest launch. Its source instrumentation remains available, but no new trace establishes the old failure cause. Revision 9 prospectively prevents observer private mappings from being reclaimed: after all target/control allocations it uses mlockall for current/future mappings, then unlocks only the exact target. Actual smaps verification must show complete unlocked target coverage and locked accessible private observer mappings, excluding only named kernel special mappings. Syscall success alone is insufficient. Both compared arms use the same isolation, target, ordering and timed interval, with fresh calibration. Any infeasible or missing proof blocks the new adapter. H29 owns its exact source-feasibility and implementation; H24 owns matching contract/parser fields. Original revision-8 behavior and failed evidence remain unchanged.
