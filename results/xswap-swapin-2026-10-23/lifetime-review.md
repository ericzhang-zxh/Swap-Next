# Independent descriptor lifetime review

Date: 2026-10-23. Scope: read-only source and retained evidence review over SSH on hurricpc-wsl; no build, guest, kernel edit, promotion or publication performed.

## Disposition

No actionable remaining descriptor-lifetime defect is supported by the inspected paths. Confidence: medium. The source fix is suitable as the baseline for the owner-authorized bounded H1/H2 discovery experiments, subject to the controller retaining its actual gates. This is a code-review disposition, not a declaration that every policy gate passed or a merge approval. A concrete unpinned descriptor access outside the bound/RCU/lock protocol, or a failing targeted runtime trace, would change this disposition.

Reviewed head: `5e84ca928deeacb4eee656806a003f27d1eca82f`; direct base: `b1eb429f257641dab45dd1633fda80c353d26250`; Phase III seed: `b2beda7fe460f911b88d27890993347588d70748`. Diff changes mm/swap.h, mm/swap_state.c and mm/swapfile.c. Source references below are relative to `worktrees/xswap-p123-2026-10-23/xs-desc-lifetime-v1/` in `/home/xuanhao/playground/Swap-Next`.

## Source reasoning and ownership

| Resource | Owner/reference holder | Published when | Released when | Protection |
|---|---|---|---|---|
| cluster_info mapping | swap device; grow/shrink worker | map and lock initialization precede release-store of nr_clusters_mapped | FREE-only suffix isolated, bound lowered, PCP cache invalidated, RCU grace period, cluster-lock drain, unmap | xswap_lock serializes map/unmap; lookup uses acquire bound inside RCU; returned cluster lock extends protection |
| count/swap table | cluster | rcu_assign_pointer after initialization | empty cluster removes pointer and retires count table; extend/memcg tables cleared under cluster ownership | ci lock for mutation; table reader RCU protects table, outer new RCU protects descriptor |
| folio | allocation caller, then swap cache and transient caller refs | second availability check and cache insertion under ci lock | failure folio_put; successful cache follows existing locked-folio lifetime | folio lock/reference plus slot/cache ownership |
| swap slot | PTE count or swap-cache owner | allocation and count update | last count/cache user disappears | ci lock; pinned callers remain on existing helper |
| compressed object | zswap xarray/LRU | existing zswap store | invalidation or successful writeback | writeback revalidates xarray identity after securing locked swap-cache folio |
| physical backend/memcg charge | xswap backend record | backend allocation/charge path | unlink/free or rollback; xs table retirement releases remaining backends | existing virtual/physical cluster locks; no charge logic changed by this patch |

The original stale zswap callback can now arrive after shrink safely: swap_cluster_lock_unpinned() enters RCU before checking the mapping bound, acquires ci->lock while the descriptor is protected, and returns NULL outside the mapped prefix (mm/swap.h:176-237). A reader observing the old bound is drained before unmap; a reader retaining ci->lock after leaving RCU is drained by the unmapper taking that lock (mm/swapfile.c:5036-5110). The FREE-only isolation under si->lock excludes new list allocations, and its trylock check avoids taking ci->lock in the opposite blocking order (5150-5247).

The sleeping folio allocation interval no longer retains ci: each availability check reacquires it by offset, and a missing descriptor after allocation releases the new folio (mm/swap_state.c:443-505). Extend-table retry likewise obtains a fresh descriptor, frees the speculative allocation if it disappeared, and rechecks table/count state (mm/swapfile.c:1807-1861). swap_dup_entries_cluster keeps its original ci across its atomic retry only under its documented existing slot-pin contract (2039-2085).

The publication audit includes xswap_map_clusters (4824-4928), xswap_grow (4942-4993), isolate_lock_cluster/swap_cluster_populate (751-895), __free_cluster (832-850), and swap_cluster_free_table (629-669). A sleeping population keeps its cluster isolated with NONE, so it cannot satisfy shrink FREE-only selection. Newly mapped clusters remain NONE until the grower publishes them to the free list; concurrent shrink cannot select that range. The existing per-CPU local-lock critical section and explicit allocator RCU sections cover cached-descriptor allocation/reclaim (1201-1260, 1286 onward). Shrink clears PCP device pointers before waiting for readers.

Swap-cache reads now nest table lookup RCU inside the descriptor lookup RCU (mm/swap_state.c:81-161). The returned folio still uses existing try_get and caller lock/entry revalidation. swapoff clears WRITEOK, stabilizes the shrink worker, drains device users and RCU before teardown (mm/swapfile.c:4070-4167); teardown drains remaining mapping readers through the same unmap helper. Backend/free/charge semantics are unchanged. No new lock-order inversion or cleanup leak was identified in these changed paths.

## Retained runtime evidence

Every named completed run has exit_code 0, integration_pass true, all recorded gates true, and an empty kernel_diagnostics list. Serial log hashes were independently recomputed and matched result.json; raw serial scans found BENCH_PASS and no BUG/WARNING/Oops/KASAN/KCSAN/circular-locking diagnostic signatures.

| Run under benchmark/swap-standard/runs/ | Rounds / verified workers | Grows / shrinks | zswap writeback pages |
|---|---:|---:|---:|
| repro3-base-wbdelay-1 | 10 / 20 | 86 / 26 | 4203706 |
| repro3-base-wbdelay-2 | 9 / 18 | 79 / 22 | 3749780 |
| repro3-cand-wbdelay-1 | 9 / 18 | 78 / 26 | 3794659 |
| repro3-cand-wbdelay-2 | 9 / 18 | 91 / 25 | 3768388 |
| base-debug-lifetime-1 | 9 / 18 | 75 / 22 | 3745487 |
| cand-debug-lifetime-2 | 9 / 18 | 74 / 23 | 3737426 |
| cand-std-lifetime-1 | 10 / 20 | 36 / 11 | 4166837 |

Evidence for each row: its result.json, serial.log, and frozen harness/. Delayed baseline head is `7d7fe2ec76901c0bf4cd84dba215be69c9d788aa`; delayed candidate head is `bd96dc6da7ed924933133e85af5e94d9ef56a17c`. Candidate instrumentation diff against 5e84ca928 is 15 added lines in mm/zswap.c: delay one in 16 async-worker writebacks after get_swap_device and before cache allocation, configured to 2000 ms. Standard/debug candidate rows use exact 5e84ca928. Both baseline and candidate passed, so runtime evidence establishes no reproduction in these runs; the source interleaving and repair reasoning carry the lifetime conclusion.

Retained failed gate: `desc-v1-debug-lifetime-1/result.json` reports integration_pass false, lifetime_data false, 2 rounds and 4 verified workers. Its serial CHURN_PASS says rounds=2, workers=4, verified_workers=4; absence of diagnostics and BENCH_PASS do not turn this into an integration pass. It remains part of the evidence.

## Static evidence

- `evolve/control/state/xswap-p123-2026-10-23/xs-desc-lifetime-v1/static.json`: SCOPE_PASS for head 5e84ca928, measured from Phase III seed; retained checkpatch.log has zero errors/warnings, diff-check.log has no diagnostics. These are prior checks, not rerun here.
- `benchmark/kernel/builds/{xs-desc-v1,xs-desc-v1-debug,xs-desc-v1-noxswap}/result.json`: passed true, exact head 5e84ca928. Debug output/.config has PROVE_LOCKING, PROVE_RCU, DEBUG_ATOMIC_SLEEP, DEBUG_VM enabled. KCSAN is disabled. The noxswap build is not evidence of CONFIG_SWAP=n coverage. Build log includes config override warnings and a container whoami notice; do not describe it as an entirely warning-free log.
- `worker-scratch/logs/sparse-desc-v1.log`: SPARSE_NO_NEW means the retained filtered diagnostics match. Both `sparse/xswap-p123-ref.diag` and `sparse/xs-desc-v1.diag` contain `mm/memory.c:282:9: error: incompatible types in conditional expression (different base types)`. `sparse-desc-v1.sh` filters output through grep/sed without preserving make status. This supports equal observed diagnostic sets, not a successfully completed full sparse gate.

## Limitations and next step

No fresh runtime reproduction, deterministic race scheduler, KASAN/KCSAN matrix, allocation/I/O fault injection, or comprehensive large-folio/swapoff matrix was executed in this read-only assignment. The retained stress checks exercise data, grow/shrink and writeback with lockdep/RCU debug in applicable builds; they do not establish race freedom. Sparse completion remains an evidence gap. Policy-required gates must remain accurately represented; readiness for bounded discovery must not be transformed into promotion acceptance.

Proceed with the explicitly authorized H1/H2 discovery scope using the exact fixed baseline once the primary controller resolves any admission requirements. Preserve failures and require fresh review of the additional unpinned neighbor paths introduced by readahead. If reverting this fix for comparison, revert 5e84ca928 only in an isolated baseline; the original descriptor race then remains applicable. No performance benefit is claimed by this review.
