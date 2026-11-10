# Runtime incident 002: contradictory frozen debug input

The first counted candidate build compiled K1 successfully, then the trusted configured-build validator rejected it because final CONFIG_KASAN=y was missing. The input simultaneously requested CONFIG_KASAN=y and CONFIG_SLUB_TINY=y; the pinned kernel requires SYSFS && !SLUB_TINY for KASAN. Every other required debug flag resolved correctly. This is an infrastructure coverage failure, with no candidate guest, sanitizer result or timing result.

- Candidate: 7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad.
- Counted row: 6be443dc6e384b909ef8dd544f9e7211; build: c1-7d5a3cfab2ab-debug.
- Compilation: exit 0, passed=true, 117.262 seconds. Configured coverage: BUILD_FAILED, required final CONFIG_KASAN=y missing.
- Frozen input SHA-256: c58461570b79210f9d99c7eb2e3a6e492601960ea73394bb4e4c78b147cd0ba4.
- Final config SHA-256: 551176da172052a53db99292ad8d04b5b3ae806053bd9dd833b52405a4e2d2d8.
- Built image SHA-256: c4f352a5f5f85819be4ef70953d8918346c6366dd5e5acc99660762dea473a44.

The original contract and evidence remain immutable. The current trusted runtime is archived under the original campaign runs/closeout-runtime/ with all 28 pinned runtime files, in addition to the earlier invalid-baseline archive. The coordinator is closing this scientific contract and preparing a separately frozen corrected C1 contract on the unchanged candidate tree. C1-replacement-contract.json caps it at the remaining 29 probe guests, 88 fast guests and seven new builds and preserves the original execution deadline. This is the same logical phase, with all old resource consumption retained; there is no candidate-selection or resource reset.

H8 adds a distinct debug-v2 input with SLUB_TINY disabled and leaves the old file unchanged. Required KASAN, lockdep, failures, NUMA and KUnit coverage are preserved. Actual corrected final configuration and runtime still require counted validation. C2 and C3 remain dependent on C1 correctness. An independent reviewer is auditing the continuation and will review final evidence and conclusions.
