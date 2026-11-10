# K1 result: shared page-compression library

Status: implementation committed; candidate builds and runtime coverage unverified.
Contributor: `codex-tiering-01a1c6b6`.
Candidate: `agents/c1-shared-store-v1` in `worktrees/codex-compress-lib-2026-11-10/c1-shared-store-v1`.
Base: `5e84ca928deeacb4eee656806a003f27d1eca82f`.
Head: `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`.
Tree: `8b085adc109e3b5467c3de998f11b04517f052a5`.
Author/committer: Eric Zhang <zxh@xh-zhang.com>; Assisted-by included, no DCO.
Scope: 7 allowed files, 1077 additions + 285 deletions = 1362 changed lines.

## Delivered behavior

The opaque library owns crypto-acomp contexts, scratch buffers, CPU lifecycle
and zsmalloc storage. It returns handle/length/error-stage values on the stack.
ZSwap retains its entry/index, pool registry, percpu references, RCU release,
memcg accounting, admission and LRU ownership. The codec name is stored once in
the library; its accessor requires the caller to keep the pool pinned.

Compression-only store reports codec versus allocation failure. Only a codec
failure reaches ZSwap's existing deferred writeback-permission decision; a
separate raw-store operation then copies the page without recompression.
Allocation failure never triggers raw retry. ENOSPC classification is retained.
Load is non-consuming and validates full-page decode output. Raw load preserves
the highmem-compatible copy and dcache flush path.

The shared fixed PREPARE CPUHP state registers at subsys initialization without
allocating codecs. Frontend pool creation remains late, after crypto. Failed
add-instance construction cleans every initialized possible-CPU context;
registered instances are removed before context destruction. Contexts survive
CPU hot-unplug as before. Frontend publication follows successful construction.

| Resource | Owner and release boundary |
| --- | --- |
| Input/destination folio | Caller retains folio lock/reference across operations. |
| Handle and length | Frontend entry owns each successful store; one free after unpublication and drained users. |
| Library pool and contexts | Frontend pool pins them; existing percpu-ref/RCU release drains users before library destruction. |
| Logical index, memcg reference/charge, LRU | Existing ZSwap paths; unchanged publication/accounting and partial-folio cleanup. |

## Test implementation

The exact ordered suite is `page_compress_alloc_rollback`,
`page_compress_partial_cleanup`, `page_compress_numa_placement` in suite
`page_compress`. Leaf allocation/free stubs are task-local; successful calls
use the real allocators. Tests record the induced failure and compare actual
successful-allocation/free counts, including request failure after a prior
CPU context succeeds when multiple CPUs are online. They verify surviving
nonzero data, subsequent recovery, compressed/raw object failures and empty
backing storage after cleanup. Abort-safe cleanup retains resource ownership.

NUMA uses a fresh pool for every online memory node and inspects actual SG
page nodes while mapped. Assertions and diagnostics run after read-end. It
emits the exact per-placement and total payloads required by the trusted
observer. No suite/test skips or synthetic successful operations are used.

## Source checks and footprint

- Diff whitespace: PASS. Checkpatch --strict --no-signoff: 0 errors, 0 checks,
  1 new-file MAINTAINERS warning; MAINTAINERS is outside the frozen scope.
- Exact source comparisons: unchanged zswap_entry definition, frontend
  publication/accounting/partial-store code (apart from the free API name),
  and reference/RCU release protocol: PASS.
- Exact allowed-file set, 2500-line ceiling and three ordered test names: PASS.
- Candidate status, including ignored/untracked files: completely clean.

High confidence from source layout: no per-object wrapper or entry growth;
per-CPU context fields/order are unchanged. On LP64, the new library wrapper
requests 160 bytes (two pointers, hlist node and 128-byte codec name); removing
those fields from ZSwap and retaining one pointer reduces its wrapper by 152
bytes. Net requested per-pool overhead is therefore 8 bytes plus one additional
allocation. Slab rounding, allocator metadata, generated stack/code size and
latency are unmeasured. Earlier provisional 72/136-byte estimates preceded the
final single-name boundary and are superseded by this layout.

## Limitations and next action

No candidate compilation, KUnit execution, sanitizer, guest, performance or
NUMA runtime result exists from this task. Source checks support proceeding to
the coordinator's counted c1-debug build and independent exact-tree review;
those results can falsify the current implementation. The new call boundaries,
initialization cleanup and real NUMA placement require runtime verification.
No benchmark/framework/protocol or host settings were changed. No task process
remains running; no push or promotion occurred.
