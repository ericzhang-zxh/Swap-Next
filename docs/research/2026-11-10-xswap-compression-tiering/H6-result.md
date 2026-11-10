# H6: Audited baseline infrastructure recovery

Status: integrated as 96eac45, original attempt retained, named counted replacement passed.
Source commit: 44a5d46e050ac31bc4a09f8308d0d276158bd024.

The explicit baseline-only operation replays unchanged original artifacts with their archived parser, requires a sole flat-topology identity defect and passing scientific gates, and pins the replacement to the same baseline kernel/configuration/case with the fixed image. It preserves the original reservation, budget consumption, raw bytes and failed outcome. A declaration is not a correctness pass; the exact newly reserved replacement must pass current validation. Candidate failures, incomplete attempts, other failed gates, changed evidence and retry chains remain blocking.

The isolated regression selection passed 102 tests, including 16 recovery cases. The integrated coverage/session/workflow selection passed 106 tests. Actual archived input preflight classified the original as BASELINE_INFRA_INVALID. The explicit declaration is ledger/baseline-infra-supersessions/c1-b-common-001.json (SHA-256 8a7a9b4614c0b6336df8d8eda0759747f35f82a17f2bdcd96a73e912e40dd273) inside the C1 campaign; its immutable bugfix evidence is H5-result.md.

Run c1-b-common-002 passed all current gates, including data roundtrip, fork/COW, concurrent fault, live destroy, swapoff and configuration identity. The matrix verifier now retains successful b-common and b-legacy rows and reports candidate coverage pending. Total consumption at this boundary is three guests and two builds. No candidate runtime or timing result exists yet.

Confidence: high for this narrowly verified recovery. A failed replacement, changed archived/current runtime hash, missing original reservation or extra failed scientific gate invalidates it. This facility does not classify unrelated infrastructure incidents.
