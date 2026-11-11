# H26: first-failure compressed timing diagnostics

Status: implementation and guest-free checks complete. Coordinator integration and a separately counted diagnostic remain pending.

Commit: 454b6f45aa89a9dddff0d5c6e00a5dcd6ac7fd83, on isolated branch infra/c1-trace-diagnostic-01a1c6b6 at base 41c7a9e26b233dd9e2e9b683e71563b44f8c6752. The clean commit changes only benchmark/swap-standard/swapin.c and test_compression_evidence.py: 465 insertions and 23 deletions. H25 owns the source diagnosis; this task adds failure evidence only.

## Implemented behavior

The first failed decode observation retains the exact first trace-file read in the existing 32 KiB buffer. Reversible line tokenization restores every separator on success and early rejection; it needs no second success-path capture buffer. Read metadata records open/read/limit stage, byte count, errno and cap exhaustion. Parser metadata identifies the original rejection branch, prefix counts, whether scanning completed, and the first unexpected record's byte range and parsed return when available.

After that rejection, the observer attempts to disable tracing and reports the result. It emits the original bytes as bounded hex, preserving NUL, carriage return and non-ASCII bytes through serial transport. It never replaces those bytes with a later trace read. A one-shot guard prevents repeated diagnostic emission. The ordinary SWAPIN_FAIL result remains the workload outcome.

Later readbacks are explicitly labeled post_failure: tracing_on, current_tracer, trace_options, event enable/filter/format, kprobe registration/profile and per-CPU loss statistics. Each readback has its own byte count, error and truncation state. Readback payloads are capped at 4095 bytes each and CPU enumeration at 64; the first payload is capped at 32767 bytes. Cap exhaustion remains a failed read, including an exactly full capture, matching the previous reader. A failed tracing-disable request is visible and never reported as successful.

## Preserved contract

Source comparison confirms that observer setup, target readiness and the entire main body are byte-identical to the base except the two diagnostic order/index arguments. PID filter, registration, 16 KiB trace buffer, clock, target/reclaim/sample ordering, and t0/volatile-touch/t1 interval are unchanged. The exact-one header/entry/written/record, zero-return and loss predicates remain the same. Successful observations emit no diagnostics and do not change tracing state. The compile-time TRACE_ROOT override exists only to point unit fixtures at temporary files; the guest default remains fixed.

This patch does not isolate observer memory, alter the trace window, add accepted samples or choose a runtime root cause.

## Verification

| Check | Result |
| --- | --- |
| Full swap-standard discovery on final source | 179 tests run: 178 passed, 1 optional Linux-checkout test skipped |
| New failure-diagnostic tests | Eight tests covering all rejection reasons, exact bytes, partial EINTR reads, open/read/limit failures, one-shot dumps, readback bounds, disable failure and the silent success path |
| Frozen-predicate comparison | Identical decisions and unchanged input bytes across 306 deterministic valid/mutated traces, plus explicit branch cases |
| Compiler checks | Guest workload and fixture wrappers compile with gcc -O2 -Wall -Wextra -Werror |
| Source comparison | Setup/target/main comparison passed; diagnostic call arguments are the only main-body changes |
| Diff hygiene | git diff --check passed; isolated tree clean after commit |

The skipped test is test_runner.RunnerValidationTests.test_lifetime_fix_check_needs_a_real_commit, which requires a populated linux/ checkout. No kernel compilation, guest, image preparation, runtime probe, protocol/budget/raw mutation, main implementation edit, push or delegation occurred. All temporary compiler fixtures were removed by the tests. Nothing remains running from H26.

Reproduce the relevant checks with python3 -m unittest discover -s benchmark/swap-standard -p test_compression_evidence.py and the full suite with the pattern test_*.py. These synthetic and filesystem-fixture checks establish diagnostic behavior; the failed campaign's runtime cause still requires its first retained failing trace.

Source SHA-256: swapin.c = 26080a666441fed1b0b66d59f9f205e621a5cc734e1cccd785106ee281e577a9; test_compression_evidence.py = da67197dbd718b6ef6c1664a639636c72779ddecb8318832d11da7f15fce94c2.
