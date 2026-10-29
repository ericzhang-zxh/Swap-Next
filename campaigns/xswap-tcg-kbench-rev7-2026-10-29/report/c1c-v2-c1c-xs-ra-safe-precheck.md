# Pre-check: round-2 candidate c1c `v2-c1c-xs-ra-safe` @b69e47c9

Pre-boot review for campaign `xswap-tcg-kbench-rev7-2026-10-29`. I only read files and git. I did not build, boot, run sparse or checkpatch, commit or push. Times are PDT (UTC−7). Line numbers refer to the c1c tree (`<box>/wt-c1c`) unless another file is named.

## Verdict: **GO-WITH-CONDITIONS**

**GO here means only "OK to boot the fast-tier screen".** It is not acceptance, not eligibility for the slow tier, and not a parent decision. My round-1 process findings still apply to every rev7 verdict: rev7 is the unmerged PR #8, there is no recorded owner approval, and the void tooling has no PR.

- I found no confirmed kernel defect that blocks a boot.
- I agree that A1, A3 and A4 are closed by code reading. A5 holds, with an argument. A2 and A6 are still open.
- The read-I/O-error behaviour is acceptable-as-stock.
- Before the first guest boots, must-fix items M1–M2 (plan and record, not code) must be done and conditions C1–C4 must hold.

## Identity, scope and size

| Item | Finding | Evidence |
|---|---|---|
| Commit | b69e47c9118b442751767ef704fbac9cb74b50c3. Parent 5e84ca928deeacb4eee656806a003f27d1eca82f. `git rev-list --count 5e84ca92..b69e47c9` = 1. | `git log` in <box>/wt-c1c |
| Tree | 58d43c9477b94d19d090d9d0af3a091b78ec1bac (matches) | `git log --format=%T` |
| Author / date | ericzhang-zxh, 2026-10-29 13:39:44 −0700. No Signed-off-by. `Assisted-by: LLM checkpatch`. | `git show -s` |
| Patch file vs diff | The body from `diff --git` up to the `-- ` trailer is byte-identical to `git diff 5e84ca92 b69e47c9`. The file sha256 (82d27cb5…) differs only because of the format-patch header and trailer. The bare diff sha256 is 8b4e1388…. | `patches/c1c-v2-c1c-xs-ra-safe.patch` |
| Scope | Only `mm/swap_state.c` changes, which is in the campaign allowlist. 1 of 8 files. | `git diff --stat` |
| Size | +191/−8 = 199 changed lines. Within the campaign's 1000 and the base policy's 300. | same |
| checkpatch / apply | The write-up reports 0/0/0 and a clean apply. **I did not re-run either.** | write-up table |

## A1–A6 and the I/O-error question

| # | Hypothesis claim | My finding | file:line | Confidence |
|---|---|---|---|---|
| **A1** TOCTOU unbacked speculative read → !uptodate → SIGBUS | Closed by a recheck under `ci->lock` after insertion | **Agree: closed by code reading, not by test.** See "A1 trace" below. | swap_state.c 759-779, 827-845, 864; swapfile.c 2355-2356, 3551-3586, 832-841, 5072-5077; zswap.c 1026, 1055-1061; page_io.c 507-537 | medium-high |
| A1 unwind | Same as `__swap_cache_alloc`'s failed-charge unwind | **Mostly correct, but not the same.** Refs, stats and the v2 memcg charge are balanced. It differs because the unwind runs *after* `memcg1_swapin()` and `workingset_refault()`. Consequences: on cgroup-v1 memsw, the still-swapped slot's swap_cgroup id stays cleared, and the refault is counted and its shadow lost. Both are low severity and correctness-neutral on v2. There is precedent: `xswap_unuse_rmap` L3559-3562 and zswap writeback `err:` L1101-1105. | swap_state.c 369-379, 507-537, 841-843; memcontrol-v1.c 340-376 | high |
| A2 lockdep / ci->lock context | Open | **Agree: open.** The new code takes only `ci->lock`, with a new folio lock held (folio → ci order, as in stock). There is no nested `pci` lock, no allocation and nothing that sleeps under the spinlock. `lockdep_assert_held` was added. A lockdep run is still required for acceptance. | swap_state.c 766, 800-804, 835-837 | medium |
| **A3** swapoff | Closed via SWP_WRITEOK | **Agree.** `del_from_avail_list(p, true)` clears SWP_WRITEOK (swapfile.c 1527), reached from `swap_info_remove` (4071, called 4050) before `try_to_unuse` (4107). The target checks then send unuse to the single-folio path. The backend-WRITEOK clause also matters for A1 (see below). | swap_state.c 766-767, 775-778, 1094, 1200 | high |
| **A4** VMA-mode asymmetry | Closed via the target check | **Agree in code.** Not exercised: the scored disk arm most likely runs cluster mode, because virtio_blk sets `BLK_FEAT_ROTATIONAL` (drivers/block/virtio_blk.c 1442) → `nr_rotate_swap>0`. The write-up's D3 assumption ("default VMA mode") is likely wrong for disk. | swap_state.c 1199-1201, 1235-1241 | high (code); medium (mode) |
| A5 phys device not pinned | Argued closed | **Agree with the argument.** An admitted neighbour holds its locked cache folio until the read ends. Phys swapoff's `xswap_unuse_rmap` must find that folio and `folio_lock` it (3551-3554), and a not-yet-inserted neighbour loses to unuse's own folio (-EEXIST). So the device cannot finish `try_to_unuse` under an in-flight read. The demand-path unpinned read is pre-existing. | swapfile.c 3478-3597, 4107; swap_state.c 853-858 | medium |
| A6 memcg | Open | **Agree: open.** Charging is stock readahead charging, and a charge failure takes `__swap_cache_alloc`'s own unwind. memcg_limits and allocation_failure have not run. | swap_state.c 507-517 | high (status) |
| **I/O error** (R4) | Not closed; stock behaviour | **Acceptable-as-stock** (see below). Not must-fix for the screen. Test-required (io_failure gate) before acceptance. | memory.c 4994-5000, 5078-5081, 5304-5310; swap_state.c 853-856; swapfile.c 3559-3562 | high |

### A1 trace: hint → `swap_read_folio` for a neighbour

1. **Cluster mode.** `swap_cluster_readahead` checks the target hint at L1094 and each neighbour hint at L1114 (`continue` if it fails, so no ref is taken).
2. **VMA mode.** `swap_vma_readahead` checks the target hint at L1200 and each neighbour hint at L1237 (`folio = NULL`, then the stock `put_swap_device` and `continue`; refs are symmetric).
3. **Insertion.** Both modes call `swap_cache_read_folio(..., readahead=true)`, which reaches `__swap_cache_alloc` (L443-538).
   - It runs `__swap_cache_add_check` under `ci->lock` twice. A freed or cached slot gives -ENOENT/-EEXIST, so no folio is created.
   - It inserts the folio locked and off the LRU, then charges memcg.
4. **Recheck.** L864 calls `xswap_ra_folio_keep` → `swap_cluster_get_and_lock(folio)` → `xswap_ra_slot_ok`. That re-reads `xs_table[slot]`, the xswap device's SWP_WRITEOK, the backend's SWP_WRITEOK and the backend's !SWP_SYNCHRONOUS_IO.
   - If it fails: `swap_cache_del_folio` (−nr refs, stats back, `folio_swapped` true so the slot is not freed), then `folio_unlock`, then `folio_put` frees the folio and uncharges memcg. NULL is returned before `folio_add_lru` / `swap_read_folio`. No !uptodate folio is left in the cache.
5. **Read.** `swap_read_folio` re-reads phys under the same lock (page_io.c 515-520). The WARN branch (522-529) is reachable only if the backend changed after step 4. With F locked in the cache, the `xs_table` writers are:
   - **Slot free** (`xswap_release_slot_backend` at 2355-2356): only runs from `__swap_cluster_free_entries`, which needs a shadow and no folio. ✓
   - **Cluster table free** (`__free_cluster` 832-841, shrink 5072-5077): only for empty or going-away clusters. ✓
   - **Backend set** (`xswap_backend_alloc` 4705+): swapout of the cached folio itself, or zswap writeback. Writeback must first create its own cache folio (zswap.c 1026), which gets -EEXIST while F is cached. ✓
   - **`xswap_unuse_rmap` drop** (3578-3586): runs after it has `folio_lock`ed *the* cache folio, so it waits for F. ✓
   - **Edge case:** between unuse's `folio_unlock` (3575) and the `xs_table` clear (3578-3586), the unuse folio could be reclaimed and a new F inserted. The recheck still rejects F, because the backend has lost SWP_WRITEOK (swapoff is in progress). So the backend-WRITEOK clause is load-bearing, not just advisory. ✓
   - **`xswap_reclaim_backing`** (3429+): uses `folio_trylock`, which fails on a locked F. ✓
6. **Zswap store / refusal.** These happen with the swap-out folio in the cache, so neighbour insertion gets -EEXIST and returns the uptodate folio. ✓

**Residual risk.** The argument assumes there are no other `xs_table` writers (write-up R5). I found the same set by grep (`xswap_slot_set_backend`, `xswap_release_slot_backend`, `xswap_free_xs_table`, the unuse clear). No run exercises these races (see C2).

### Other checks on the +191 lines

- **Refcounts on every exit.**
  - Cluster `continue`: no ref.
  - VMA `NULL` path: stock `put_swap_device`.
  - `xswap_ra_folio_keep` failure: −nr cache refs, then −1 alloc ref → freed.
  - `swapin_sync`: if `swapin_readahead` returns NULL, it falls back to the stock loop.
  - ✓ high.
- **Large folios.** Readahead is admitted only when `orders == BIT(0)` (L939). Readahead allocates `BIT(0)` only (L857). ✓ high.
- **Sleeping or allocation in atomic context.** There is none in the new code. `swap_cluster_get_and_lock` warns on `!in_task()`. ✓ high.
- **Data races.** `si->flags & SWP_XSWAP` is a plain read of an init-time constant. `swap_info[]` and `psi->flags` are read with `READ_ONCE` as hints. Run KCSAN before acceptance. medium.

### Sync-backend gating (p99 mechanism)

- **The gate is correct.** It rejects any slot whose backend has SWP_SYNCHRONOUS_IO (L776-778). zram and brd backends set that flag (swapfile.c 5708). The xswap device itself carries it too (5512), which is why `swapin_sync` is the entry point.
- **It removes the round-1 mechanism on zram rather than mitigating it.** The zram-64k arm (backend zram0) goes back to the baseline path: swap_ra should be ≈0, p99 ≈1.0 and the zram mean gain is given up (write-up R7).
- **What the zram arm measures now.** Only the hint overhead: one `ci->lock` plus a VMA-history write per adjacent fault (L897-908).
- **Same effect on the zswap backend.** The protocol's zswap backend writes back to zram1 (`protocol.json` backends.zswap; bench.sh 63/70), so c1c readahead is gated off there too.

### Read I/O error: call **acceptable-as-stock**

- **Stock fault path.** `do_swap_page` takes a cached folio from `swap_cache_get_folio` (memory.c 4994) without checking whether it is uptodate.
  - It locks the folio. If it is !uptodate it returns `VM_FAULT_SIGBUS` (5078-5081).
  - `out_nomap` → `folio_free_swap` does not drop it while the PTE still holds the swap count (5304-5310).
  - `swap_cache_read_folio` likewise returns any cached folio as-is (853-856).
- **So yes: a neighbour read error turns into a SIGBUS for a later fault on that page.** There is no re-read, unless reclaim evicts the clean, unmapped !uptodate folio first. At swapoff, `xswap_unuse_rmap` drops it (3559-3562).
- **This is identical to upstream semantics** for readahead on every async swap device, and to a demand-read error, which SIGBUSes anyway.
- **What c1c adds** is exposure on xswap disk-backed neighbours. A *transient* error can be frozen into the cache, where a later demand read might have succeeded.
- **Not must-fix for the screen.** A fix would need memory.c (outside scope) or end_io work. The io_failure gate stays required before acceptance.

## Must-fix list (before the first boot; plan and record, not code)

1. **M1: pre-register the KILL in a durable record.**
   - Today the KILL and falsifiers exist only in `<box>/swap-next-proposals-v2/c1c-xs-ra-safe.md`. That directory is not a git repo, and the file mtime is 13:42.
   - Put the KILL, the falsifiers and the probe key `swapin-disk:swapin_vmstat_delta.swap_ra:up` into the candidate's hypothesis record when `controller new` runs, and commit or hash it before the probe guest. AGENTS.md Campaign lifecycle allows committing candidate records to main.
   - Record the sha256 and time in the run LOG.
2. **M2: fix the KILL statistic.**
   - The write-up says "geomean over fast pairs". The c1b plan uses the median, and analysis.py decides on the median.
   - Pre-register one statistic. I recommend the median log ratio.
   - Note that 0.90 is inside the A/A envelope. zram seq.p99 noise 0.1988 → ln(1.1988) = 0.181 → guard ratio ≈0.834. So 0.90 carries a material false-kill rate.
   - Either keep 0.90 and accept that rate explicitly, or use the guard threshold (≈0.83). Decide before boot.

## Conditions for the screen

- **C1: the correctness guest must use the disk backend, not zswap.**
  - With the zswap backend, the physical backend is zram1 (SWP_SYNCHRONOUS_IO), so c1c's readahead and recheck never run. That run would test nothing new.
  - With the disk backend, readahead, the recheck path and `swapoff_live_pages` are all exercised. Round 1 showed swap_ra 4104 on disk.
  - Require `correctness_vmstat_delta.swap_ra > 0` in that proof, as well as the 5 protocol gates.
- **C2: say plainly that A1 rests on code reading.**
  - Neither legal correctness backend combines an async physical backend with zswap transitions. bench.sh 80-88 disables zswap after xswap creation on disk, and only disk|zswap are allowed (216).
  - A zswap-mixed + async-backend + forced-writeback + swapoff-under-load test needs a harness or protocol change, which requires a PR and Hurric's approval.
  - Record it as NOT RUN. Do not claim A1 is "tested".
- **C3: the budget fits exactly, with no spare.**
  - The plan is 1 correctness + 3 probe + 16 fast + 1 reserve = 21, against the coordinator's ~21 under the 111 cap (`plan-r2-r3.md`). Pool view: fast 27 left, probe 12 left.
  - A second validity rerun would leave the eval INCOMPLETE. Do not add a zswap correctness guest.
  - Round 3 gets nothing.
- **C4: the probe must use the disk key, and the falsifiers must be checked as written.**
  - Use the disk key (the zram key would fail by design).
  - Read the falsifiers as specified: zram swap_ra ≈0, disk swap_ra ≈115k, disk seq.mean median ≥2.5, no WARN (page_io.c 527) or SIGBUS.
  - FAST_PASS remains a non-regression screen, and the disk effect is TCG-only.
- **Optional (non-blocking):** move the recheck into `__swap_cache_alloc`'s second locked section (L490-505), before the folio is inserted and charged. That removes the unwind, together with the memcg-v1 and workingset side effects. A rebuild would change the tree, so it is a new candidate.

## Limitations

- **Nothing was run.** No compile, sparse, checkpatch re-run, lockdep, KASAN, KCSAN, fault injection or memcg/mTHP gate (these belong on hurricpc-wsl or the worker). No guest.
- **A1, A3, A4 and A5 are judged by reading** the 5e84ca92-based c1c tree (`swap_state.c`, `swapfile.c`, `page_io.c`, `zswap.c`, `memory.c`, `memcontrol-v1.c`). The `xs_table` writer set comes from grep. A writer reached through a path I did not read would break A1.
- **Cluster vs VMA mode on the disk arm** is inferred from virtio_blk's default `BLK_FEAT_ROTATIONAL`. It was not confirmed from guest logs.
- **Budget numbers** are from `ledger/budget.json` and `plan-r2-r3.md`. The 111 cap is the coordinator's figure and is not in any file.
- **The round-1 process findings** (unapproved rev7, unreviewed void tooling) are unchanged and outside this pre-check.
