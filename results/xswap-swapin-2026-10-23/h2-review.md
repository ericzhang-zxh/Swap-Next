# H2 independent source review

Reviewed f7093a0732ae9b46e31a9ceb90c2b14eb8038c16 against 5e84ca928deeacb4eee656806a003f27d1eca82f. No supported blocking defect found.

- `xa_load()` protects its lookup internally with RCU. The new helper converts the result to a boolean without dereferencing or retaining the compressed object; the caller holds the swap device reference protecting the tree.
- The target read remains unconditional. Speculative xswap neighbors require an advisory actual-residency hint; normal swap-cache allocation and reads revalidate current state.
- VMA cross-device references remain balanced on skipped and successful paths. Direct cluster/shmem callers preserve device protection.
- CONFIG_ZSWAP=n has a false stub. ZSWAP depends on SWAP; XSWAP depends on both. No unsupported configuration reference was found.

Source review does not establish runtime safety. Stale hints can change which backend ultimately serves a speculative read. This is ordinary swap-cache prefetch, not decompressor batching. Large-folio behavior, fault injection and KCSAN remain outside this discovery evidence.
