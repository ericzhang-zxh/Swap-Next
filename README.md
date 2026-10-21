# Swap Next

A bounded kernel optimization laboratory: immutable candidate patches, isolated builds, paired KVM experiments, and OpenEvolve feedback. This is an experimental research system, not a production kernel or a proven performance improvement.

## Repository layout

```text
Swap-Next/
├── linux/       # upstream Linux submodule, pinned to a public commit
├── Evolve/      # OpenEvolve evaluator and proposal-feedback adapter
├── system/      # our candidate controller, policy, analysis and tests
├── config/      # kernel configuration used by the pilot
├── patches/     # independent experimental patches against upstream
└── results/     # historical observations, with explicit limitations
```

The submodule tracks `torvalds/linux` at `744e5400b36f84b4816e3ff8531ec2dff52b474c`. Swap is a subsystem within Linux; it is not a separate upstream repository. Our controller is outside the upstream tree. Candidates run in disposable `worktrees/`; the pinned submodule stays clean.

Clone this repository with `git clone --recurse-submodules <repository-url>`, or run `git submodule update --init linux` after a normal clone. The Linux checkout is large.

## Workflow

Run kernel tasks on a dedicated Linux KVM worker. See [Evolve](Evolve/README.md) for prerequisites and build/rootfs setup. The namespace launcher currently targets an x86-64 Debian/Ubuntu-style toolchain layout.

```sh
python3 system/controller.py status
python3 -m unittest discover -s system/tests -v
python3 system/controller.py new my-trial --hypothesis 'One concrete hypothesis'
# Edit only allowed paths in worktrees/my-trial and commit locally.
python3 system/controller.py check my-trial
```

The proposal author owns the hypothesis; OpenEvolve stores candidate programs and returns selection feedback. This adapter does not run a background model worker or call a paid model API. The full acceptance protocol remains disabled pending calibration and missing correctness/holdout gates. The separate pilot is for observations only. Nothing auto-merges, pushes, promotes, changes host swap, or replaces the host kernel.

## Current evidence

[The xswap discovery campaign](results/xswap-2026-10-21/README.md) completed three feedback-driven experiments on an independently imported Phase I/II reference, with 35 guest attempts (34 passed; one retained setup failure). No candidate was promoted: A/A revealed large metadata-state variation and all trials had mixed outcomes. The pinned Linux checkout remains unchanged.

[Three historical pilots](results/pilot-summary.json) comprise 24 independent guest boots. The two latest trials reused a locked table read and combined that change with early overflow-scan termination. Their pilot gates passed, but neither showed consistent latency gains. One proposed RCU simplification was rejected during review because the cluster lock alone did not establish table lifetime across an unlocked allocation path.

These results predate this repository layout. Each backend has only two AB/BA pairs per candidate; there is no A/A calibration, independent confirmation, or holdout. Metadata measures selected requested allocation bytes, not total physical RAM. Raw logs and VM artifacts are not published here. Relocation checks do not constitute a fresh kernel runtime validation.

## Provenance and license

Our controller and kernel modifications use GPL-2.0-only; see [LICENSE](LICENSE). Linux retains its own licenses in the submodule. OpenEvolve is an external pinned dependency with its own license. The code and experiment descriptions were developed with substantial AI assistance. No AI-generated Signed-off-by tags or human DCO certification are implied. Experimental patches are independent alternatives, not a patch series.

## Contributor guidance

Project-authored writing is in English. Follow [kernel code taste rules](system/CODE_PATTERNS.md) and use the repository-local [kernel patch review skill](.agents/skills/kernel-patch-review/SKILL.md) when reviewing kernel changes. This policy does not alter upstream content or global assistant preferences.
