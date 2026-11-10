# C1 compression correctness workload contract

This document describes implemented observer behavior, not executed kernel
coverage. The new workload has been compiled and tested without a guest.
A pass becomes evidence only after the trusted runner binds its complete raw
output to the exact kernel tree, effective config, image, topology, case,
counted reservation and reviewed workload source.

## Invocation and setup

Install the guest-compatible `compression` binary in the guest's existing
`/opt/bench/bin` PATH. The existing image builder links its probes against
the image glibc; static linking is also checked as an optional build. Run one
case per invocation:

```sh
compression --mode xswap --case roundtrip --type 0 \
  --bytes 33554432 \
  --cgroup /sys/fs/cgroup/bench \
  --reclaim /sys/fs/cgroup/bench/memory.reclaim
```

For legacy zswap, use `--mode plain --swap-device /dev/vda`. Omit `--type`
unless the harness independently knows the active physical swap type.
Optional `--alternate-codec lz4` makes the codec replacement choice explicit.
Without it, the alternate is lz4, or lzo when the initial codec is lz4.

The guest initializer must create `/run/swap-next-guest` containing exactly
`swap-next-guest-v1\n`. This is an operational guard against accidental host
execution, not authentication that the process runs in a VM. The trusted runner
owns VM identity. The workload requires root and a 4096-byte base page.

The caller must already reside in the named cgroup. The root cgroup's memory
controller must be enabled. The workload creates a unique sibling leaf
`/sys/fs/cgroup/swap-next-comp-<pid>`, joins it before touching the target
mapping and uses that leaf's `memory.reclaim`. It restores the caller's cgroup
and removes the leaf before a successful reset. The supplied `--reclaim`
must match `--cgroup/memory.reclaim`; it identifies the caller contract, while
target reclaim uses the isolated leaf. Do not place another process in it.

XSwap mode requires exactly one active virtual swap device, the requested
type, priority 32767 and no physical swap. Legacy mode requires exactly one
specified physical swap device and no XSwap device. Ordinary zswap needs
physical swap slots; it cannot use the no-backing XSwap topology.

Keep zswap enabled for these C1 tests. Disable its shrinker in legacy
compressed-resident cases to avoid reclaim deliberately writing the objects
to the physical backend. The workload records runtime enable/shrinker state
and initial codec; it does not change the shrinker globally.

Bytes must be 2 MiB-aligned, between 2 and 128 MiB. Default 32 MiB.
The codec-switch and hotplug cases hold two mappings of that size.
Default data uses nonzero repeated words plus a distinct page/generation stamp;
it cannot legitimately use the zero-page shortcut.

## Raw output

Each invocation has exactly one begin, reset, case and end record:

```text
COMPRESS_BEGIN schema=1 mode=xswap case=roundtrip bytes=33554432
COMPRESS_OBS case=roundtrip phase=before key=swap_devices value=1
...
COMPRESS_RESET case=roundtrip status=PASS
COMPRESS_CASE case=roundtrip status=PASS reason=ok
COMPRESS_END schema=1 status=PASS cases=1
```

Exit codes: 0 PASS, 1 FAIL, 77 INCOMPLETE, 64 invalid arguments. Missing
capability, unobserved operation or unsupported topology never yields PASS.
A reset failure overrides the case result to FAIL. Read-only or unsupported
invocations emit `COMPRESS_RESET ... status=PASS untouched=1`; this says only
that the invocation made no fixture changes.

`COMPRESS_OBS` values are nonnegative integers. Key uniqueness is scoped by
case and phase. The topology and counter snapshots share the `before`
phase but use distinct keys. Optional runtime text is:

```text
COMPRESS_CONFIG case=roundtrip codec=lzo
```

The parser must verify case identity, marker ordering/completeness, all
required observations, derived predicates, reset and exit status. A PASS
label or exit code alone is not a certificate. Repeated invocations in one
boot require separate complete blocks and successful reset between them.

### Common observations

| Phase | Keys |
| --- | --- |
| before/reset topology | swap_devices, virtual_devices, physical_devices, no_backing, intended_device_matches; xswap_priority in XSwap mode |
| configuration | zswap_enabled, shrinker_enabled |
| mapping_a / mapping_b | nonzero_pages |
| stored_a; or stored_old/stored_new | target_pages, swapped_pages, absent_swapcache_pages, target_type |
| before/stored/decoded/cleanup counter snapshots | stored_pages, pool_bytes, incompressible_pages, zswpin, zswpout, pswpin, pswpout, memcg_present; memcg_zswap_bytes and memcg_zswapped_bytes when the leaf exists |
| decoded | verified_words |
| reset | objects_and_charges_drained, temporary_memcg_removed; codec_restored and cpu_restored when applicable |

For ordinary data cases, at least 90 percent of the mapping must have swapped
PTEs of the intended type and `mincore` must report no uptodate swap-cache folio.
At reference `5e84ca92`, `mm/mincore.c:48-85` derives that bit from
`swap_cache_get_folio()`. Pagemap alone would allow a swap-cache false positive.

The workload additionally requires actual stored-object and store-counter
growth, positive compressed memcg charge, no incompressible-object growth,
aggregate decoder traffic and verification of every data word. Physical
PSWPIN/PSWPOUT must remain unchanged for ordinary compressed cases.
In legacy mode the declared backing device exists but the tested traffic
must still remain compressed. The explicit quota-denial case has different
expectations below.

These counters are aggregate phase observations, not synchronous per-target
decode events. They complement the nonzero data, topology, pagemap and mincore
evidence. Buffered memcg state gets bounded polling; absent observation still
returns INCOMPLETE. No per-page timing or decoder attribution is claimed.

Reset unmaps both mappings, restores touched codec/CPU/affinity controls,
waits for stored-page count to equal its initial value, requires pool backing
bytes not above their initial value and requires zero compressed charge in
the leaf when still present. It then removes the empty leaf and rechecks the
original swap topology. This detects retained objects/backing pages, not every
possible codec-context or allocator metadata leak.

## Cases and precise coverage

| Case | What observed PASS establishes | Important limits |
| --- | --- | --- |
| roundtrip | Nonzero target data reaches compressed storage outside swap cache, is decoded and all words match. | No per-page performance claim. |
| memcg_balance | Roundtrip plus observed positive compressed charge and zero charge after teardown. | Not a cgroup limit test. |
| codec_switch | Old compressed targets remain nonresident after switching to a distinct codec and storing new targets; both generations decode correctly; original codec restored. | Does not directly observe every pool's internal refcount or CPU-context memory. |
| invalid_codec | A nonexistent codec is rejected with EINVAL/ENOENT; configured codec stays unchanged; subsequent roundtrip works. | Not allocation failure or codec-context initialization failure injection. |
| concurrent_fault | Eight barrier-released children fault the same 32 targets, which were each independently verified swapped and absent from swap cache; each child checks data/COW and parent data remains intact. | Does not force one particular kernel lock interleaving. |
| live_destroy | A live compressed XSwap mapping survives device destruction with a reader child, complete data verification and recreation of the original type/priority. | Requires XSwap. The reader is concurrent work, not an instrumented exact fault/teardown interleaving. |
| memcg_offline | The leaf has live compressed charges, the task leaves and the leaf is actually removed, then all data remains readable and global objects drain. | Decoded snapshot has memcg_present=0; removed-leaf stats must not be fabricated. |
| memcg_limits | A dedicated leaf's memory.zswap.max is set/read back as 0; four real PAGEOUT/reclaim attempts keep zswap/zswapped charges zero, global stored_pages/zswpout unchanged and all data remains correct. | Zero-quota admission only. XSwap without backing must retain usable pages; legacy mode may use its explicitly declared physical fallback. |
| guest_hotplug | An allowed online guest CPU is used for old storage, observed offline and online, then used for new storage; old/new data survives and CPU/affinity are restored. | Unsupported guest CPU controls are INCOMPLETE. No host CPU changes. |
| large_folio | MADV_COLLAPSE produces an exact-mapping AnonHugePages observation equal to the input bytes; the 2 MiB-order zswpout counter increases and compressed data survives. | If collapse, exact mapping observation or order-specific store is absent, INCOMPLETE. Does not prove a partial-store failure path. |
| library_unit | Exact reviewed three-test page_compress KUnit suite has complete passing raw KTAP. | Requires the actual candidate suite and separately reviewed real operations/assertions. Observer plumbing does not implement or certify those operations. |

Case-specific keys in phase `case`:

- codec_switch: `codec_switched=1`, `old_and_new_data_verified=1`;
  `old_pool` is a counter snapshot and `old_after_switch` is the old-target
  residency snapshot.
- invalid_codec: `invalid_codec_errno`, `codec_unchanged=1`.
- concurrent_fault: `workers=8`, `concurrent_target_pages=32`,
  `concurrent_absent_swapcache_pages=32`, `cow_parent_verified=1`.
- live_destroy: `destroy_live_swapped_pages>0`, `destroy_observed=1`,
  `concurrent_destroy_reader_verified=1`, `original_type_recreated=1`.
- memcg_offline: `offline_live_compressed_bytes>0`, `live_memcg_removed=1`.
- memcg_limits: `zswap_quota_bytes=0`, `quota_pageout_attempts=4`,
  `quota_data_verified=1`; phase `quota` includes residency and counter
  snapshots. The common positive-store/decoder predicates do not apply.
- guest_hotplug: `target_cpu`, `cpu_offline_observed=1`,
  `cpu_online_observed=1`.
- large_folio: `huge_input_bytes=bytes`, `large_zswpout_before`,
  `large_zswpout_after>before`.

The following case IDs deliberately return INCOMPLETE with
`targeted_observer_available=0`: `allocation_failure`, `partial_failure`,
`init_failure`, `numa_locality`. Kernel config, a rejected codec,
page-array cleanup or memcg offlining cannot substitute for these operations.
Do not schedule their stubs as passing gates.

## Candidate KUnit observer

The fixed source is `/sys/kernel/debug/kunit/page_compress/results`.
The complete bytes appear between:

```text
COMPRESS_KTAP_BEGIN suite=page_compress
KTAP version 1
1..1
    KTAP version 1
    # Subtest: page_compress
    1..3
    ok 1 page_compress_alloc_rollback
    ok 2 page_compress_partial_cleanup
    ok 3 page_compress_numa_placement
ok 1 page_compress
COMPRESS_KTAP_END suite=page_compress
```

This is the debugfs envelope in `lib/kunit/debugfs.c` at the fixed reference.
The observer rejects missing/extra/reordered/unknown/duplicate results,
wrong plans/suite, any failed result, SKIP/TODO, truncated/oversized output
and embedded NULs. It does not trigger or rerun the suite. The runner binds
the recorded boot execution and source identity.

Expected semantics, to be independently verified in the actual K1 test source:

1. `page_compress_alloc_rollback`: real library operation with an actually
   induced/observed allocation failure and resource/data rollback assertions.
2. `page_compress_partial_cleanup`: real sequence with successful earlier
   objects and an observed later failure, then exact cleanup and surviving-data
   assertions. This is not automatically large-folio frontend coverage.
3. `page_compress_numa_placement`: iterate every online memory node, perform
   real library allocations and inspect actual placement (for example, the
   node of each zsmalloc SG page exposed by the public read API). Emit
   requested/actual node observations and total node/placement counts in KTAP.
   One node is legitimate in the debug boot; a locality claim requires the
   separately identified two-node auxiliary boot and its placement evidence.

Structured phase `case` contains `kunit_expected=3`,
`kunit_observed=3`, `kunit_failed=0`, `kunit_skipped=0` and a key equal
to each expected test name with value 1. Those values reflect parsing, not a
replacement for reviewed test implementation and retained raw KTAP.

The parser must treat the enclosed KTAP as raw text only. Never parse a
COMPRESS_OBS/CASE-looking string inside it as a second evidence record.
An absent suite returns INCOMPLETE. The original baseline without this suite
is an expected negative control, not a passing candidate proof.

## Guest-free verification

```sh
cc -std=gnu11 -static -O2 -Wall -Wextra -Werror \
  -o /tmp/compression-check benchmark/swap-standard/compression.c
/tmp/compression-check --selftest
python3 -m unittest discover -s benchmark/swap-standard \
  -p test_compression_workload.py -v
```

The selftest emits `COMPRESS_SELFTEST_PASS` and no guest coverage markers.
The Python tests compile the executable and a pure-function wrapper, then
exercise negative KTAP fixtures, full-pattern corruption detection, arguments
and the missing-guest-marker refusal. They start no VM and alter no kernel,
swap, cgroup, sysfs or CPU settings.
