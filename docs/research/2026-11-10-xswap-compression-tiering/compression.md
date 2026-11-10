# R1: Shared page compression and object storage

Status: research complete; implementation and runtime validation not started.
Owner: compression researcher.
Repository reference: `5f0d57e3fe365db15878c5ca674cccc8558f36a5`.
Kernel reference for all source anchors below:
`5e84ca928deeacb4eee656806a003f27d1eca82f`.

## Recommendation

Extract a small page-compression store from zswap, then make zswap and an
XSwap compressed backend independent clients of that store. Keep logical swap
identity, lookup indexes, LRU membership, admission policy, memcg ownership and
tier migration outside the library. Sharing implementation does not require
sharing one global pool, compressor setting or eviction policy.

There is only one compression implementation to extract in this reference:
XSwap currently calls zswap. It does not have a second independent compressor.
The library should reuse the existing crypto acomp and zsmalloc facilities.
A narrow source-only refactor is a useful precursor, but it cannot establish
independent XSwap compression or pressure-driven tiering.

## Existing implementation and evidence

All findings in this table have high confidence from direct source inspection.
The observation that would change them is a different selected kernel tree.

| Area | Exact evidence | Consequence |
| --- | --- | --- |
| Direct dependency | `mm/Kconfig:125-132` requires ZSWAP; `mm/swapfile.c:5476-5478` refuses XSwap creation when zswap is disabled. | Removing only the Kconfig dependency is insufficient. |
| I/O interception | `mm/page_io.c:238-240,507-508` calls zswap_store/load before backend I/O; `mm/swapfile.c:5515-5521` explicitly says XSwap's ops methods are not called. | Independent XSwap requires frontend dispatch changes as well as a library. |
| Storage engine | `mm/zswap.c:140-162,268-338,799-987`: per-CPU acomp contexts, scratch buffer, zsmalloc pool, compression and decompression. | These mechanisms form the extraction boundary. |
| Object identity | `mm/zswap.c:202-220`: swpentry, length, referenced, u8 pool_idx, handle, objcg, LRU; pool_idx is safe because the entry pins its pool. | Preserve compact entry metadata and pool lifetime; avoid adding an object allocation or per-object refcount solely for abstraction. |
| Publication | `mm/zswap.c:1487-1550`: initialize pool_idx before xarray publication; folio lock excludes store/invalidation; LRU publication follows refs, charges and metadata initialization. | The library must not take over entry publication. |
| Teardown | `mm/zswap.c:406-447,777-793`: detach pool registry, wait RCU, release CPU contexts and zsmalloc; entry free removes LRU, frees handle, releases pool and objcg, uncharges and decrements counters. | Preserve ordered teardown and exactly one release for every resource. |
| Raw fallback | `mm/zswap.c:893-923`: compression failure or a non-smaller result can be stored raw when frontend policy permits; length PAGE_SIZE means raw. | Keep this behavior explicit; do not equate codec failure with loss of the input page. |
| NUMA | `mm/zswap.c:759-765,814-822,914-915`: entry allocations use folio nid; codec scratch/context uses CPU node; zsmalloc allocation uses folio nid. | The library needs a caller-supplied allocation nid and must preserve CPU-local codec allocation. |
| Accounting guard | `include/linux/memcontrol.h:1945-1973`: !ZSWAP charging helpers become no-ops and policy helpers return true. | A CONFIG_ZSWAP=n XSwap must not call those stubs as if accounting worked. |
| Accounting context | `mm/memcontrol.c:6388-6418` assumes PF_MEMALLOC for forced-success zswap charging; `:6449-6457` bypasses zswap writeback policy when zswap is disabled. | New worker-driven operations need valid, fallible charging semantics and a frontend-neutral policy decision. |

## Proposed state and API ownership

Names below are a design sketch, not implemented symbols.

| Resource or decision | Owner | Lifetime or contract |
| --- | --- | --- |
| zsmalloc pool, per-CPU codec requests, wait objects, scratch buffers | Library pool | Fully construct before exposure; destroy only after caller drains objects and in-flight users. |
| Current compressor selection, pool registry and frontend pool references | Each frontend | Zswap can preserve its current u8 pool namespace and percpu_ref protocol. XSwap must have its own ownership, independent of zswap globals. |
| Compressed object handle and length | Frontend entry | Successful store transfers one handle to the caller; failed store transfers none. The entry or its explicit pin protects both handle and pool during load. |
| Logical swap entry and index publication | Zswap or XSwap frontend | Library never accepts a swp_entry_t, accesses an xarray, or installs a tier mapping. |
| Folio lock, entry pin, retry after concurrent invalidation | Caller | Callers establish these before library operations and revalidate after sleeping work where required. |
| memcg reference, admission, charges, statistics, LRU and eviction | Frontend | Library returns stored size and actual pool backing footprint; it must not silently apply zswap's policy to XSwap. |
| Migration source/destination, writeback and failure recovery | Tier framework | Outside the compression library; library load is non-consuming. |

Minimal operations:

- `create(algorithm, pool_name)` and `destroy(pool)`: establish and drain
  storage resources. A named codec must be available; no dependence on
  CONFIG_ZSWAP_COMPRESSOR_DEFAULT inside the library.
- `store(pool, folio, page_index, allocation_context, result)`: process one
  base page. Context includes nid, GFP constraints and explicit allow-raw
  policy. Result contains the handle and stored length; no extra heap-allocated
  wrapper is necessary.
- `load(pool, handle, length, destination_folio, page_index)`: decode or copy
  one base page, validate the output length, preserve the object on success
  and failure, and let the caller decide publication and retirement.
- `free(pool, handle)`: consume the caller-owned handle once.
- `backing_pages(pool)`: return actual zsmalloc backing pages. Payload lengths
  alone do not measure RAM released because allocator fragmentation exists.

The pin/read/release contract belongs to the frontend lifetime protocol:
pin entry and pool, read non-destructively through the library, then release the
pin or retire/free the object after the ownership transaction. Do not expose a
bare handle after dropping that pin. Generic migration does not require a new
library refcount for every handle. A shared reference manager can be considered
later if two clients establish a common need.

This split lets zswap keep its packed pool_idx representation without forcing
XSwap to resolve handles through zswap's global registry. Zswap's wrapper owns
the library pool and can destroy it when its existing percpu_ref/RCU release
path has drained. XSwap's wrapper owns and drains its own pool.

## Lifecycle and error-path obligations

1. Register the common CPU-hotplug state before either frontend adds a pool.
   Current setup is in zswap_setup at `mm/zswap.c:1878-1883`; retaining it there
   would fail when ZSWAP=n or zswap is never enabled. Move it into the library's
   once-only initialization, preserving initialization after crypto is ready.
2. Preserve online/offline/online handling from `mm/zswap.c:805-812`.
   Current CPU contexts survive hot-unplug and are freed when the pool dies.
   Do not destroy an acomp request while a synchronous waiter uses it.
3. Preserve the mutex-protected context and synchronous wait for async crypto
   completion at `mm/zswap.c:868-890,950-976`. NOWAIT storage allocation does
   not make the whole operation atomic or non-sleeping.
4. If CPU initialization partially fails, free every initialized possible-CPU
   context, remove the registered instance if present, free percpu memory, then
   destroy zsmalloc. Current cleanup is `mm/zswap.c:330-384`.
5. On allocation, compression or decode failure, return a structured failure
   category without publishing a half-object. Preserve the current distinction
   between codec failure, rejected raw fallback and zsmalloc allocation failure
   for frontend counters. A tolerated raw fallback is still successful storage.
6. Caller failure after successful store (index allocation, charge or mapping
   publication) must free the handle and undo acquired refs/charges. A partial
   large-folio store must invalidate every affected old/new entry consistently;
   current zswap does this at `mm/zswap.c:1604-1630`.
7. Keep single-base-page storage initially. Large folios can remain collections
   of base-page objects; no claim of large-folio decode support follows from
   extracting a function.
8. For later worker-driven promotion, obtain a valid memcg reference and reserve
   charge before committing the new RAM copy. Normal workers must not call the
   existing PF_MEMALLOC-only forced-success helper blindly. Charge failure
   leaves the old authoritative copy usable.

For accounting, the smallest extraction preserves zswap's existing behavior.
Independent XSwap needs shared internal compressed-memory charge primitives
available without CONFIG_ZSWAP, with the frontend supplying its accounting and
policy context. Preserve zswap's existing user-facing controls for zswap;
do not silently make XSwap's correctness depend on those controls or on
zswap_is_enabled(). The coordinator should freeze the XSwap accounting/control
contract before implementing that stage. A new public cgroup ABI is not needed
to extract the mechanism.

## Simpler alternatives

Reusing crypto acomp directly in XSwap is the narrowest codec-only change.
The reference zswap already does that (`mm/zswap.c:822-846,868-890,966-971`).
It would still duplicate codec-context lifecycle, raw fallback, zsmalloc
allocation/copy and cleanup, and therefore does not satisfy the shared
page/object-library objective. It is a useful lower-layer dependency, not a
replacement for the proposed extraction.

Reusing zram's zcomp is possible after separating it from the zram driver,
but is not a smaller behavior-preserving first patch on this baseline.
`drivers/block/zram/zcomp.h:59-96` supplies compression contexts and byte/SG
operations, not compressed-object ownership. Object allocation still occurs
in `drivers/block/zram/zram_drv.c:2314-2339`. Its CPUHP registration belongs
to zram (`zram_drv.c:3283-3284`), and its build-selected backend table uses
CONFIG_ZRAM_BACKEND_* (`zcomp.c:25-46`; `drivers/block/zram/Kconfig:17-58`).

There are also measurable behavior differences: zcomp allocates a two-page
compression buffer plus a one-page linearization buffer per stream
(`zcomp.c:64-70`) and destroys CPU streams on hot-unplug
(`zcomp.c:203-210`), whereas this zswap keeps its codec contexts until pool
destruction and uses crypto acomp with synchronous completion waiting.
Switching zswap to zcomp in the extraction would combine API extraction,
codec backend choice, memory cost and hotplug policy in one experiment.

Recommendation: preserve the zswap crypto-acomp backend in C1, extract the
shared page/object mechanism with unchanged behavior, and measure it before
C2 independence. A later convergence with zcomp is a separate hypothesis once
the shared boundary is established; it should compare the actual codec and
per-CPU footprint, not assume API similarity implies equivalence.

## Concrete source scope

These are proposed editable sets, not edits performed by R1.

| Stage | Modify existing files | Add files |
| --- | --- | --- |
| Shared store extraction, initially zswap client | `mm/zswap.c`, `mm/Kconfig`, `mm/Makefile`, `include/linux/cpuhotplug.h` | `mm/page_compress.c`, `include/linux/page_compress.h` |
| Independent XSwap compressed backend | Above plus `mm/swapfile.c`, `mm/page_io.c`, `mm/swap_state.c`, `mm/swap.h`, `include/linux/swap.h`, `include/linux/swap_ops.h` | `mm/xswap_compress.c` |
| Accounting independent of zswap | `include/linux/memcontrol.h`, `mm/memcontrol.c`; revise `mm/Kconfig` and frontend callers | No separate file required |
| Focused tests | `mm/Kconfig`, `mm/Makefile`, `tools/testing/selftests/mm/Makefile` where the chosen test integration needs them | `mm/page_compress_test.c` for KUnit; `tools/testing/selftests/mm/swap_next_compression.c` for guest validation |

The CPUHP enum edit renames/reassigns the existing
CPUHP_MM_ZSWP_POOL_PREPARE slot to the shared mechanism while preserving ordering
(`include/linux/cpuhotplug.h:116`). A dynamic state could avoid the header edit
but changes lifecycle details; it is not a reason to omit CPU-hotplug validation.

A hidden common config symbol should select CRYPTO and ZSMALLOC and build the
library; ZSWAP and XSWAP select it independently. Keep zswap's compressor choice
compatible and give XSwap an available default codec independently of
CONFIG_ZSWAP_COMPRESSOR_DEFAULT. The initial XSwap backend can use existing
internal headers; a new public `include/linux/xswap.h` is unnecessary unless a
real external caller appears.

No crypto algorithm or zsmalloc internals need to change for this approach.
Adding new VM-event IDs, per-lruvec policy fields or public interfaces would
expand this list and must be justified by the migration/accounting design.

## Staged, falsifiable hypotheses

1. **Shared mechanism:** moving codec contexts and object storage behind the
   library preserves zswap data and error behavior, compact entry size and
   frontend policy. Success is an exact-tree interface/lifetime review plus
   build/config and storage tests, then same-protocol equivalence screening.
   Falsifiers include changed charge balance, hidden zswap initialization
   dependency, leaked codec contexts, metadata growth or latency regression.
   Extraction alone is architectural preparation, not a speedup.
2. **Independent XSwap:** the XSwap compressed backend dispatches through
   swap_ops, can round-trip nonzero compressible data with CONFIG_ZSWAP=n,
   and owns its objects/accounting. Falsifiers include a linked dependency on
   zswap internals, no-op accounting, disk fallback masquerading as compression,
   or dependence on zswap.enabled. This stage requires the dispatch/lifetime
   design in R2.
3. **Pressure-driven demotion:** library decode plus the shared migration
   transaction releases actual RAM under pressure without lost data or an
   invalid destination. R2 owns the transaction; R3 owns execution capability.
   The library must neither select victims nor choose destination devices.

An internal refactor confined to mm/zswap.c is an optional prerequisite when
the true extraction infrastructure is not yet ready. It is not a substitute
for any of these three architectural milestones.

## Independence and validation criteria

Required configuration matrix:

- ZSWAP=y, XSWAP=n: existing zswap behavior and codec changes remain supported.
- ZSWAP=n, XSWAP=y: build, boot, create, compressed store/load and teardown work.
- ZSWAP=y, XSWAP=y: disable zswap at runtime; XSwap remains operational and owns
  a separate pool. Re-enabling zswap must not double-compress XSwap traffic.
- SWAP=n and both clients disabled: no unresolved references or orphan init.

Read the generated .config, linked symbols and boot identity; a requested
config fragment alone is not proof. Exercise nonzero compressible pages in a
guest with no lower backing device for the bounded round-trip case, and verify
XSwap compression/store/load counters or trace evidence plus stored objects.
An all-zero workload could pass through the zeromap without compression.
Then separately exercise incompressible data, exhausted pool, explicit
allocation failures and ordinary disk fallback. Always verify data contents.

For shared-store testing, include concurrent CPUs, pool/codec replacement while
old objects remain live, guest CPU hotplug, bad codec/init failure, allocation
failure, decode failure, highmem-compatible copy paths, partial multi-page
failure, memcg release/offline, and teardown races. Guest-only CPU hotplug is
sufficient; host CPU changes are outside scope.

A passing compressed-data round trip is not sufficient for memory-pressure
efficacy. Measure actual backing pages and temporary staging memory, and verify
charge release after objects and in-flight work retire. Payload bytes alone
cannot establish net RAM reclamation.

## Current executable scope and capability work

The current swap-core profile permits internal factoring in mm/zswap.c and
related existing swap files, but not new library files, Kconfig, Makefile,
CPU-hotplug headers or memcontrol changes. Its correctness modes contain only
xswap, and its declared gates do not include injected failures, memcg limits,
large folios or sanitizers. The existing baseline itself requires ZSWAP.

R3 confirmed the trusted runner also requires CONFIG_ZSWAP and unconditionally
uses zswap sysfs. Therefore a current-profile run can screen a behavior-preserving
precursor under the existing baseline. It cannot certify the common library,
CONFIG_ZSWAP=n or independent compression.

Required capability work is concrete:

- A narrowly defined shared-compression profile with the above file scope and
  a change-size budget appropriate to moving several hundred existing lines.
  Do not enable the broad, non-executable swap-architecture profile.
- Build/config validation that supports the full client matrix and does not
  silently restore CONFIG_ZSWAP.
- A guest adapter that conditionally uses zswap interfaces, validates XSwap
  independently, records exact .config/kernel identity and exposes owned-store
  evidence, charge balances and actual pool memory.
- Trusted test coverage for pool lifetime, codec/init/allocation errors, memcg,
  multi-page cleanup, concurrent load/free and guest CPU hotplug; sanitizer
  evidence proportionate to the new shared lifetime boundary.
- Frozen same-configuration control/treatment comparisons. For the new
  ZSWAP=n mode, report its correctness and resource behavior directly; do not
  pretend the unmodified reference supports that same mode.

The missing old-profile scope is work to implement, not evidence against the
architecture. Research completed without enabling profiles or launching runs.

## Peer coordination

R2 and R1 agreed that migration stays outside the library. R2 can initially
retain an XSwap-owned compressed index plus the existing xs_table physical
association; the library returns a pool-relative handle without zswap-entry
coupling. Entry/pool pins protect load and retirement. A replacement tagged
location representation is not required for the first RAM-to-SSD transaction.

R3 confirmed that the current runner and profile cannot supply CONFIG_ZSWAP=n
evidence. Its validation document owns the detailed harness matrix.

## Limitations

This document is a source-grounded design proposal, not an implementation,
build result or benchmark. The exact library API, XSwap accounting contract
and trusted test profile must be frozen by the coordinator before execution.
No kernel files, policy/profile/controller files, campaign state or host
configuration were modified by this ticket.

## Integrated plan review

Reviewed PLAN.md and the disabled, uninstalled profile-proposal.json. The shared
library boundary, frontend-owned pins/accounting and independent-config evidence
are faithful to R1. The profile is a planning superset and must become
stage-specific executable contracts. One wording/dependency issue remains if
unchanged: the section titled capability preparation before opening C1 includes
C2 independence and C3 migration workloads. Mark those as later-stage preparation
so C1 is gated by its own required shared-store and compatibility coverage.
Exact reviewed hashes and finding R1-P1 are recorded in tickets/R1.json.
No implementation or runtime validation was performed.
