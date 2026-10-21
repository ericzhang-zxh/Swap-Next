# Execution runbook

1. Use a dedicated Linux KVM worker. Install the documented toolchain and verify `/dev/kvm` read/write access plus an actual guest boot. Device access alone is insufficient.
2. Initialize the pinned `linux/` submodule. Run controller tests and inspect `system/config/policy.json`.
3. Follow `Evolve/README.md` to prepare the guest template/initrd and build a baseline in the namespace runner. Do not run generated candidate build scripts on the host.
4. Create one candidate through `system/controller.py new`; preserve the resource/locking/error invariants in CODE_PATTERNS.md. Commit only the allowed source changes with the appropriate repository identity. AI must not add DCO signatures.
5. Run scope/static checks, then the Evolve evaluator. Preserve every failed build or run. Check raw evidence and provenance before interpreting metrics.
6. Close and archive the candidate. Never automatically promote or merge. A/A calibration, the full correctness matrix and independent holdout remain required for acceptance.

State, builds, worktrees and VM images are ignored runtime artifacts, not repository sources. The relocated system needs fresh baseline and guest setup; historical results are not proof that a new deployment works. STOP controls owned runner stages, not arbitrary host processes.
