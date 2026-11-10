# H25: compressed timing observer diagnosis

Decision: retain the failed R5 probe attempt and hold timing conclusions. The highest-priority diagnostic is a bounded dump of the first failing observation, preserving the current rejection rule. Source inspection supports observation-path contamination by same-PID anonymous-page faults as a plausible cause (medium confidence); it establishes no deterministic text-format mismatch and no actual runtime root cause.

Scope: read-only diagnosis on the designated Linux worker. Project source is `41c7a9e26b233dd9e2e9b683e71563b44f8c6752`; the measured baseline kernel is `5e84ca928deeacb4eee656806a003f27d1eca82f`. This is separate from C2/H24 work. Only this document was written.

## Retained evidence and established outcome

Attempt: `48fd11859f014277b7188b6874673175-swapin-compressed-0`, campaign `codex-compress-lib-r5-2026-11-10`, build `c1-base-common-20261110`, baseline compressed-backend probe calibration. The counted reservation remains `STARTED` and binds the R5 frozen protocol, `c1-common`, `single`, TCG and the baseline build.

The raw directory is `campaigns/codex-compress-lib-r5-2026-11-10/runs/guests/<attempt>/`. Hashes independently checked:

| Artifact | SHA-256 |
| --- | --- |
| `result.json` | `062011b64633567f5d4546129c385c14536e2c2121bb5b9f03eedd0bffbb51fb` |
| `serial.log` | `5018cc8eddbe54aa8aee59baf90272b23f08bab15259004ce10fa91f454502ed` |
| `started.json` | `b0ef4572aca1c4a4f2c0aa92fa0d294c2fedd71f8d6c4eb9b266ab80f46812ea` |
| Measured `swapin.c` | `cfccbce37b1ad5640860ff3c3e335abb5c517bd175d4d14ca1a50046ce65fb0c` |
| Complete C1 correctness proof | `f53bf3552546426a382657f4580d5b25bd25287e74fb032873da8ba8246d45cd` |

The current `swapin.c`, `bench.sh` and `guest-init` equal their project commit and measured guest-source fingerprints. The correctness proof's eight referenced raw results retain matching hashes, `integration_pass=true`, `run_valid=true` and all recorded gates true; its two disabled-build manifests retain matching hashes and `passed=true`. The timing failure occurred on the original baseline, independently of K1's candidate runtime.

| Serial line | Retained observation |
| --- | --- |
| 146 | Observer setup completed: PID-filtered `zswap_load` return probe, `maxactive=64`, monotonic-raw timing. |
| 147–148 | One XSwap device, no physical swap backing; initial compressed store and pool counters are zero. |
| 149 | 32,768 target pages, 32,713 swapped, one reclaim round. |
| 150 | 32,756 stored pages, 73,551,872 pool bytes, zero incompressible pages. |
| 151–152 | `SWAPIN_FAIL compressed_decode_unproven`, then `BENCH_FAIL workload`. |

The control flow establishes that target coverage, compressed storage and the immediately preceding per-target pagemap/mincore check passed before at least one attempted timed load reached `decode_observed()` ([swapin.c](../../../benchmark/swap-standard/swapin.c), lines 387–435 and 450–465). The failure marker does not identify the order or target index, so the record does not establish that the first target failed.

The environment validity checks passed: `run_valid=true`, `clocksource_invalid=false`, no invalid reasons, normal QEMU exit, wall time 9.01051046489738 seconds. Integration failed because the workload stopped before `COMPRESSED_SAMPLES`; the outer parser reports `parse_complete=false`. No completed sequential/random distribution or payload verification marker exists. The raw directory contains the serial/result/start artifacts and harness snapshot, but no trace-file dump, parser branch, read errno, event count or probe-miss snapshot.

## Text-format contract

The pinned kernel's default text path is compatible with the parser's expected shape. Confidence: high for this source comparison. The observation that would change this assessment is an actual failure dump or option readback showing a different formatting path.

| Parser expectation | Exact pinned-kernel source |
| --- | --- |
| One `# entries-in-buffer/entries-written: E/W` header | `kernel/trace/trace.c:2897–2905`; the following `#P` text is accepted because the parser does not require the header to end after the second number. |
| Context followed by a space and `decode_return: ` | `kernel/trace/trace_output.c:656–684` appends `: `; `kernel/trace/trace_kprobe.c:1622–1651` prints the event name and return-probe symbols. `kernel/trace/trace_probe.h:314–321` keeps event name and group distinct. |
| A final ` ret=0` | `kernel/trace/trace_probe.c:45–56,2866–2890` prints the requested `s64` field as signed decimal and prefixes its name with a space. `mm/zswap.c:1661–1676,1710–1733` defines zero as successful load/decompression. |
| One retained entry, one written entry, one record | `kernel/trace/trace.c:2821–2857` derives written count from retained entries plus overruns. Normal filtered-out records are not simply added to that count: discard decrements the ring-buffer entry in `kernel/trace/ring_buffer.c:5142–5163`. |

A source-derived example, **not an observed runtime trace**, is `...: decode_return: (caller+offset <- zswap_load) ret=0`. The return-probe argument and the parser's decimal conversion agree on successful zero. No `ret=0x0`, group-name prefix or required trailing field is introduced by the inspected default printer.

The observer does not read back or pin `trace_options`. New instances inherit global options (`trace.c:8694`); defaults include context information and exclude binary, hex, raw, verbose and latency format (`trace.c:500–517`). A changed option could suppress/change a required header or record shape. The retained evidence contains no such option readback, so actual format remains unobserved. Existing `TraceObserverTests` use a hand-written valid string and malformed variants (`test_compression_evidence.py:537–570`); they do not reproduce live reclaim, observer faults or trace-file syscall behavior.

## Leading hypothesis: the observer counts its own faults

The capture window is broader than the timed target load. `target_ready()` checks the target and clears the trace through an `O_TRUNC` write, then closes it (`swapin.c:103–116`, supported by kernel `trace.c:3618–3633`). Tracing was enabled during setup and remains enabled until after both measurement loops (`swapin.c:91–99,421–479`). The sequence after clearing is therefore timer reads, target touch, timer read, entry into `decode_observed()`, and opening/reading/closing the trace file. The filter is only `common_pid == getpid()`, with no target-address or swap-slot binding.

The shell enters the workload memcg before launching `swapin` (`bench.sh:130–135,256–268`). Its explicit reclaim writes a byte count to that memcg's `memory.reclaim`, not an address range (`swapin.c:285–298,387–392`). The kernel passes the whole memcg to proactive reclaim with `MEMCG_RECLAIM_MAY_SWAP` (`mm/memcontrol.c:5191–5201`, `mm/vmscan.c:8172–8180`). The target mapping, workload anonymous state and observer stack/heap have no separate reclaim boundary or memory lock in this source.

`decode_observed()` allocates a 32 KiB local buffer after the target touch (`swapin.c:143–149`). Entering its frame, calling helpers or copying trace text into user memory can touch anonymous pages in the same process. If those pages were swapped, their successful `zswap_load` returns satisfy the same PID filter. The uncertainty is whether this particular execution touched previously swapped anonymous pages or only fresh/resident pages. A frame's size alone does not distinguish those cases.

The pinned kernel does not automatically stabilize this observation: `__tracing_open()` pauses tracing only when `pause-on-trace` is set (`trace.c:3438–3445`), and that option is absent from the default flags. The ring-buffer iterator explicitly documents that a concurrent write can stop iteration (`ring_buffer.c:6451–6460`). Thus same-PID loads may cause additional records or a live-read/header inconsistency, not necessarily a simple two-record trace. Confidence: medium in this explanation of the observed failure; high in the exposed capture/reclaim paths.

The stored count exceeds the target-swapped count by 43 pages. Those non-atomic aggregate snapshots support investigation of non-target storage; they cannot assign those pages to this PID, its observer stack or a particular interval. Both XSwap readahead paths explicitly skip readahead on this baseline (`mm/swap_state.c:923–925,1021–1023`), so `page-cluster=3` alone is not a source-supported explanation for multiple target decodes.

Missing records, missed return probes, a trace read error/overflow and changed formatting remain distinguishable alternatives. `decode_observed()` merges read failure and every parser rejection into one return value (`swapin.c:49–61,119–149`). The final `kprobe_profile` loss check is never reached on this path (`swapin.c:471–480`), so the current record cannot rank those alternatives from actual counts.

## Smallest diagnostic needed

Use one separately counted diagnostic attempt with the same kernel, configuration, guest resources, target size, reclaim behavior and timing order. A diagnostic-only harness/image change needs its own exact source and artifact identity. Preserve the failed R5 attempt, its cost and its rejection; do not rescore it or treat the diagnostic as a calibration sample.

At the first failing `decode_observed()` only, retain the **original bytes returned by the first trace read before tokenization**, the attempted order and page index, read byte count/error/truncation state, and a structured reason: header count, entries, written count, record count, first unexpected record and parsed return value. The existing parser and exact-one, zero-return, no-loss decision remain unchanged. Keep the dump bounded by the existing 32 KiB read cap and label truncation as failure. Emit the preserved buffer after disabling the observer; a second trace read must not replace the first failing buffer.

Then collect clearly labeled post-failure readbacks of `current_tracer`, `trace_options`, event enable/filter/format, the registered probe, per-CPU buffer loss counters and `kprobe_profile`. These readbacks separate configuration and loss explanations; their later timestamps keep them distinct from the original failing read. Preserve them as raw diagnostic evidence alongside the parser reason.

That single capture should distinguish a compatible one-record trace rejected by parsing, an empty/missing trace, extra successful returns, loss, or a failed read. If it shows extra returns, a subsequent bounded diagnostic must attribute them to the target swap slot or fault address before selecting an observer-memory isolation fix. Accepting any successful record, relaxing cardinality/loss rules, or locking the target mapping would destroy the current per-target evidence requirement. Source-only suspicion is insufficient to choose one of those changes.

## Limitations

No runtime trace was retained, so the actual failing parser branch, read outcome and source of any extra/missing event remain unknown. H25 performed no new native correctness acceptance, implementation, compiler/test run, guest, campaign-state change, commit, push, publication or delegation. Source format and control-flow findings are reproducible with `git -C linux show 5e84ca928deeacb4eee656806a003f27d1eca82f:<path>` and the project commit above. No H25 process remains running. Revisit this diagnosis when the first failing raw observation is available.
