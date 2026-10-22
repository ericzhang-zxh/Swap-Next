# xswap structure diagnostics

This independent suite extends the frozen Phase I/II workload with a second
pressure cycle. Its campaign, baseline, deadline and launch budget are owned by
[protocol.json](protocol.json). The original `benchmark/xswap` suite and evidence
remain unchanged.

## Measurement

The original six snapshots and first-access latency samples are retained.
`mapped_clusters_after_settle` remains the primary metric. After that snapshot,
`usemem -O 5G` runs again; the workload records `after_repressure`, waits two
seconds, and records `after_resettle`. Every target word is checked again before
the original COW, live destroy and swapoff checks proceed. All original parser,
backend and provenance gates remain required.

Snapshots require all fifteen debugfs fields: the original six plus nonempty
and free cluster counts; highest nonempty and blocker cluster positions;
cache-only and referenced slot counts; highest cache-only and referenced cluster
positions; and cache-only cluster count. Highest positions use index plus one,
with zero for absence. The scan takes each cluster lock sequentially. Bounds are
checked, while equality with separately sampled usage is deliberately not assumed.

The second cycle is a diagnostic perturbation that can expose retained metadata
and cache pressure effects. Its snapshots are exploratory. Workload duration and
the sampled mapped-cluster maximum include this extra cycle and must not be
compared directly with the old suite. The primary snapshot precedes the cycle.

Every valid run is classified as high when its primary mapped-cluster count is
strictly greater than 219, otherwise low. This threshold describes the old
baseline's observed low state; it is not an acceptance threshold. Reports retain
individual runs and failed attempts alongside high-regime frequency and
95% Wilson intervals. Means and the discovery score only assist inspection.

The frozen observation baseline is `4f83412c1d59eaf6a4d2460cb47fe0177a3be0c4`.
It adds read-only topology counters to the imported Phase I/II reference.
Both runner and evaluator require a full baseline commit identity.

## Bounds and execution

- One guest at a time, 4 GiB RAM, two vCPUs, private 8 GiB disk, no network or
  host mounts. A global runner lock also excludes the other suites.
- A/A calibration: two AB/BA pairs per backend, eight independent boots total.
- Candidate evaluation: ten alternating AB/BA pairs per backend, 40 boots.
- At most four evaluated candidates and 96 total guest attempts, shared by
  diagnostics, calibration and evaluation. This permits at most two complete
  candidate evaluations after calibration, with eight attempts left for diagnostics.
- Both global STOP and `evolve/control/state/<protocol campaign>/STOP` apply.
  The UTC deadline is checked before and during every guest.

Prepare the trusted rootfs with `prepare-rootfs.py --rootfs-template PATH`.
Use `evolve/loop.py xswap-structure calibrate` and
`evolve/loop.py xswap-structure evaluate --candidate NAME` from the project root.
Direct diagnostics use `run.py --build NAME --backend disk|zswap` and consume the
same attempt ledger. `summarize.py` exports all retained evaluations and attempts.
Run parser/unit tests with `python3 -m unittest -v` in this directory.
`XSWAP_STRUCTURE_EVIDENCE_FIXTURE` optionally enables real-run provenance tests.

## Limitations

Formal performance acceptance and automatic promotion remain false. Missing
confirmation, holdout, fault injection, memcg, large-folio, sanitizer, full RAM
accounting and other gates are recorded in the protocol and each report.
The A/A sample is diagnostic calibration, not proof of a stable distribution.
See [shared limitations](../../DESIGN.md#limitations). The observation patch also
adds measurement overhead; candidate comparisons require that same baseline.
