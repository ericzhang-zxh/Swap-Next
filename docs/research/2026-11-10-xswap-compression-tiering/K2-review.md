# K2: Exact-tree C1 source review

Disposition: ready for the coordinator's counted c1-debug build after transparent resolution of the existing FILE_PATH_CHANGES checker notice. No blocking code finding is supported by this source review. This is the pre-build review; final independent campaign review remains separate.

- Anchor: `5e84ca928deeacb4eee656806a003f27d1eca82f`
- Candidate: `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad`
- Tree: `8b085adc109e3b5467c3de998f11b04517f052a5`
- Scope: seven allowed files; 1077 additions and 285 deletions. Revert target is the candidate commit above.

## Structural mechanism and ownership

The declared mechanism is supported: ZSwap delegates pool/context and handle operations to the opaque library while retaining its compact entry, index, references, admission, LRU and memcg accounting. `zswap_entry` and `zswap_store()` are byte-identical to the anchor; `zswap_store_page()` differs only at the object-free API. The stack result adds no per-object wrapper. Source layout agrees with K1's LP64 estimate: one additional pool allocation and eight additional requested bytes per pool before slab rounding. Performance remains unmeasured.

| Resource | Ownership, publication and release | Protection inspected |
| --- | --- | --- |
| Input/output folio | Caller retains ownership across store/load; load does not consume the handle. | Existing folio lock/reference contract; highmem mapping and raw-load dcache flush retained. |
| Handle and entry | Successful store returns one handle; failed store clears handle/length. Frontend publishes it and frees on failed index insertion or final entry removal. | Existing folio/index/LRU ordering; `zswap.c:1262-1337,1400-1408`. |
| Memcg charge/reference | Frontend charges after successful insertion and uncharges during entry release. | Existing objcg references and publication exclusions; `zswap.c:690-706,1291-1328`. |
| Library pool and codec name | Frontend pool pins the library; registry removal, zero percpu refs and deferred RCU work precede destruction. | `zswap.c:253-360,393-429,442-455`; accessor reads remain inside a reference or RCU lifetime. |
| Per-CPU request/buffer | Fully created before client publication; contexts survive CPU offline; instance removal precedes final context freeing. | CPUHP serialization plus context mutex across synchronous crypto wait; `page_compress.c:139-250,274-305,346-370`. |

Failed CPUHP add-instance is not published by the target API. The library explicitly cleans all possible-CPU contexts, then percpu/zsmalloc/pool storage; NULL and ERR_PTR cases are handled. PREPARE callbacks execute in the invoking task, so task-local fault stubs reach actual construction callbacks (`kernel/cpu.c:260-266,2334-2435`). Early CPUHP registration allocates no codec; frontend creation remains after crypto initialization.

Error classification and fallback match the anchor: codec failure alone reaches the frontend writeback-permission decision; allocation failure cannot trigger raw retry; ENOSPC retains poor-compression accounting. Raw storage, stored-incompressible counters, exact-page decode validation and the frontend large-folio cleanup path are preserved (`zswap.c:712-765,1298-1408`).

Confidence: high for these source conclusions. A failing exact-tree build, resource-balance assertion, sanitizer report or frontend accounting gate would reopen the affected conclusion.

## KUnit contract

All three ordered tests exercise real operations, rather than successful-operation stubs (`page_compress_test.c:55-173,457-560`).

- Allocation rollback injects native failure at every library leaf allocation, including a later CPU request when multiple CPUs are online, checks observed failure and successful allocation/free counts, and performs recovery roundtrips. Compressed and raw object-allocation failures retain earlier data.
- Partial cleanup stores two distinct nonzero generations, fails a third allocation, verifies both survivors, frees tracked handles, observes empty backing storage, and performs another roundtrip.
- NUMA placement creates a fresh pool per online memory node, reads actual SG page nodes while mapped, then asserts and emits the required per-node/total diagnostics after read-end. The target zsmalloc API returns at most two SG entries (`mm/zsmalloc.c:1125-1185`).

Cleanup actions precede stub/state teardown under KUnit's LIFO resource contract. The target CPUHP, crypto-acomp, zsmalloc and KUnit APIs match the new calls. The bool Kconfig dependency requires built-in KUnit, selects LZO for these tests, and leaves disabled frontend builds without the library object.

## Maintenance advisory

The coordinator's strict check reported zero errors and one FILE_PATH_CHANGES warning. This generic new-file notice has existing routing: `MAINTAINERS:17084-17092` covers `mm/`; the CORE pattern at `MAINTAINERS:17170` covers `include/linux/page_compress.h`; ZSwap remains explicitly covered at `MAINTAINERS:30194-30204`. Read-only `get_maintainer.pl --nogit --nogit-fallback` confirms MM/core and ZSwap routing.

The notice is advisory for this bounded experiment. The trusted checker must retain and transparently disposition this exact warning before replacing STATIC_REJECT; this review does not authorize suppressing other warnings. A dedicated library maintenance entry can be considered before upstream submission, outside the frozen C1 source scope.

## Verification and remaining coverage

K2 read the complete changed source, surrounding frontend lifetime paths, target API implementations, K1 contract/result, H2 observer contract, kernel process guidance and CODE_PATTERNS. Exact head/tree, clean worktree, source equivalence checks and diff whitespace were verified. No source edit, kernel build, KUnit execution, guest or campaign-state change occurred. No review process remains running.

The next counted build must confirm final Kconfig resolution and compiler/linker behavior. Runtime acceptance still needs the exact three-test KTAP suite, debug and two-node placement, sanitizer and hotplug coverage, frontend memcg/LRU/fallback/large-folio behavior, and the complete configured correctness matrix before timing. Allocator slab overhead, generated code/stack cost and latency require measurements.
