# Allocation-first synchronous swap-in pilot

Contributor: codex-r02-20261103. One independently originated candidate; no ownership or pending-idea transfer.

The cold synchronous path currently looks in the cache in the caller, looks again in swapin_sync, and then checks under the allocator cluster lock. Test allocator-first ordering inside the helper, with cache retrieval after -EEXIST. Both allocator pre/post checks remain. Cached folios are still returned with a reference and callers still lock/revalidate them.

The earlier demand-precheck pilot failed baseline metadata stability. This new owner-requested experiment retains that negative evidence and performs exactly one fresh calibration under unchanged approved measurement parameters. Another noisy result stops execution; no threshold adjustment or same-campaign calibration retry is allowed. Performance remains unresolved until both probe and fast gates pass.

The verified baseline kernel and guest image are reused as build artifacts. No old measurements or correctness proof are relabeled. The shared native cache verified the baseline build; all guest image/source hashes match. Current machine inspection found no active experiment. The input protocol keeps TCG, 4 vCPU, 4096 MiB, 16 GiB scratch swap, fixed cases, pair counts and guards. Only one candidate is permitted, within standing caps of 120 guest attempts, 10 builds and 18 hours.

The upstream lookup-first algorithm is the control. An upstream shmem livelock discussion explains why cached-folio fallback matters; the candidate must retain that behavior. The search did not identify a separate compatible allocation-first upstream series. Shmem, THP, forced failures and sanitizer coverage remain explicit review/runtime limitations under the current guest capability.

No slow tier or candidate promotion. Report delivery follows the standing publication rule.
