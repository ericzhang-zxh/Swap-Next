# Controlled xswap hole probe

This preparation contains a guest workload only. It tests mapped metadata
retention while a live anchor occupies high virtual swap clusters, with explicit
placement prerequisites and complete data checks. No runner, parser, protocol or
campaign integration is included. Run it only inside the trusted disposable guest
after xswap and its physical `/dev/vda` backend have been set up.

## Fixed experiment

The target is the existing 64-bit x86, 4 KiB page, 4 GiB RAM guest. The pinned
kernel uses `SWAPFILE_CLUSTER=256`; this workload fixes that value explicitly.
Linux pagemap swap entries carry the swap type in bits 0..4 and the swap offset
in bits 5..54. The workload divides that offset by 256 to report cluster indexes.
A different page size or word size is rejected; changing the kernel cluster size
requires a reviewed workload update.

1. Allocate and fill 1 GiB with eight repeated, page-distinct 64-bit values per
   page. Each cycle has a distinct salt so stale data from another cycle differs.
   `MADV_PAGEOUT` and a two-second wait must leave at least 75% of filler pages
   swapped. Every swapped entry inspected must have the supplied xswap type.
2. While the first filler remains swapped, allocate and fill a distinct 64 MiB
   anchor, page it out, and inspect its PTEs. At least 1,000 anchor pages must be
   swapped and the minimum swapped anchor cluster must be at least 512.
3. Read back and verify every filler word, unmap it, and record metadata both
   immediately and after a two-second settle. Inspect anchor pagemap entries at
   both points without touching anchor data. The same 1,000-page/high-cluster
   prerequisites remain mandatory throughout all three cycles.
4. Repeat filler creation, pageout, readback verification and unmap twice more,
   retaining the original anchor. No external `usemem` pressure is used.
5. Verify every anchor word, fork a child that modifies one word and verifies its
   whole private mapping, and verify the parent's whole mapping after child exit.
   Page out the anchor again and require live xswap PTEs before destroying xswap.
   Verify all anchor words after destroy and again after `swapoff("/dev/vda")`.

## Evidence contract

Pass the active xswap type as the sole argument, as in the existing guest-init
convention. An unsuccessful prerequisite or system call prints
`XSWAP_FAIL hole_probe <reason>` and exits unsuccessfully. There are no placement
fallbacks or pageout retries.

`PLACEMENT` records include label, cycle, swapped page count, total page count,
and minimum/maximum swapped cluster indexes. Zero min/max with zero swapped pages
means absence, not placement in cluster zero. The workload rejects wrong swap
types and missing populated pages.

Every metadata block uses `META_BEGIN <phase>` / `META_END` and requires exactly
the fifteen observation fields used by `xswap-structure`. Unknown, duplicated,
missing, malformed or negative fields fail closed. The scan is sequential, so
fields do not describe a globally atomic snapshot.

Snapshot phases are:

- `before`;
- `cycleN_filler_swapped`, for N = 0, 1, 2;
- `anchor_high_placement`, immediately after first anchor placement;
- `cycleN_after_unmap` and `cycleN_after_settle`, for each cycle.

Each cycle emits `HOLE_CYCLE_BEGIN N`, `FILLER_DATA_PASS N` and
`HOLE_CYCLE_PASS N`. Successful final gates emit `ANCHOR_DATA_PASS`, `COW_PASS`,
`DESTROY_LIVE_XSWAP_PTES <count>`, `DESTROY_LIVE_PASS`, `SWAPOFF_LIVE_PASS` and
`KERNEL_WORKLOAD_PASS`. The surrounding future guest runner must still validate
empty swaps, backend activity, kernel warnings, boot identity and completion.
The current xswap-structure parser is intentionally incompatible with this probe.

## Validation and limitations

Preparation was checked remotely with
`gcc -Wall -Wextra -Werror -fsyntax-only workload.c`. No binary was executed and
no guest evidence exists for this probe yet.

The workload sequence and patterns are deterministic; allocator placement and
MADV_PAGEOUT completion depend on kernel state. Failed prerequisites invalidate
the experiment instead of measuring a substitute state. A high anchor establishes
high live occupancy; the retained metadata snapshots still need interpretation to
distinguish nonempty clusters, cache-only slots and unmapped holes. Filler
readback deliberately changes cache state before unmap. Final swapoff verifies
retained data, but does not require residual live physical-backend PTEs then.
This is a structural diagnostic with no timing, throughput or performance
acceptance claim. It has no concurrency stress, failure injection or sanitizers.
