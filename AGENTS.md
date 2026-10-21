# Swap Next contributor contract

- Read README.md, system/PRINCIPLES.md, system/CODE_PATTERNS.md and system/config/policy.json first.
- Run all kernel and sparse work on the designated Linux worker, never the controller laptop.
- Do not modify the linux submodule checkout. Create candidate worktrees through system/controller.py.
- Read linux/Documentation/process/coding-assistants.rst and its required process documents before kernel work.
- Workers execute one assigned hypothesis; no further delegation, scope changes, evaluator changes or publishing.
- Preserve locks, reference ownership, warnings, accounting and failure handling.
- Never weaken correctness gates or treat missing evidence as PASS.
- No host reboot, host swap changes, raw host disks, sudo, automatic merge or promotion.
- Keep runtime state, secrets, machine paths and credentials out of commits.
- AI tools must not add Signed-off-by. A human must review and certify any upstream contribution.
