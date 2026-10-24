# H5 design review: linearize split compressed objects

Candidate: `218750fed80a7ac099d46c5a3a26799a5d185d14`. Scope and checkpatch pass.

Source: repaired P123 baseline `5e84ca928deeacb4eee656806a003f27d1eca82f`.

Judgment: suitable for bounded fast discovery. Confidence: medium. The source mechanism is reachable when a compressed zsmalloc object spans two pages; its runtime frequency needs profiling.

The native synchronous zstd decoder uses one-shot decompression when source and destination are contiguous. A two-element zsmalloc source scatterlist makes it stream. Copy only split compressed objects into the existing PAGE_SIZE per-CPU buffer under its existing mutex, then use the public non-DMA virtual source API after setting request parameters. A short compressed copy may cost less than streaming. Direct single-SG inputs, async transforms and uncompressed pages retain their paths.

## Invariants

- Preserve mutex -> SG begin -> copy/decompress/wait -> SG end -> mutex unlock.
- The compression buffer is exclusively owned under acomp_ctx->mutex; compressed length is below PAGE_SIZE.
- The folio destination stays an SG entry, retaining crypto cache flushing.
- The slot, entry, pool references, errors, memcg charges and rollback remain in their existing paths.
- No allocation, new object lifetime, or CPU-local pointer escape is introduced.

## Source locations

`mm/zswap.c` compression buffer allocation/ownership and zswap_decompress; `mm/zsmalloc.c` zs_obj_read_sg_begin creates one or two entries; `include/crypto/acompress.h` set_params clears virtual flags and set_src_nondma sets the source; `crypto/zstd.c` zstd_decompress selects one-shot for a full input/output segment.

## Falsifier

Reject on any correctness failure or calibrated latency guard regression. A result within A/A noise does not establish a win. Existing 4 KiB zstd guests cover the target data path; exact split frequency, async codecs, KCSAN and fault injection remain gaps.

## Independent review of exact patch

Review of `218750fed80a7ac099d46c5a3a26799a5d185d14` found no blocking correctness issue. The unchanged mutex protects the PAGE_SIZE buffer through completion; SG begin/end retains migration protection; set_params clears the prior virtual-source flags before each request; callback flags and destination cache maintenance survive. CPU migration does not invalidate the pool-owned context. Async transforms retain SG input. Confidence is medium pending runtime/error coverage. The review did not build, boot, publish or add a signoff.
