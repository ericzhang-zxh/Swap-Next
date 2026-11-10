# SPDX-License-Identifier: GPL-2.0-only
"""Fixed C1 configuration/correctness catalog and build identity checks."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
BASE_GATES = ["data_roundtrip", "fork_cow", "concurrent_fault",
              "swapoff_live_pages", "no_new_kernel_warnings"]
CONFIGS = {
    "standard": {"path": "benchmark/config/swap-standard.config",
                 "purposes": ["timing", "correctness"],
                 "required": {"SWAP": "y", "ZSWAP": "y", "XSWAP": "y",
                              "MEMCG": "y", "TRANSPARENT_HUGEPAGE": "y", "THP_SWAP": "y"},
                 "forbidden": ["KASAN", "KCSAN", "PROVE_LOCKING"]},
    "c1-common": {"path": "benchmark/config/compression-common.config",
                  "purposes": ["timing", "correctness"],
                  "required": {"NUMA": "n", "SWAP": "y", "ZSWAP": "y", "XSWAP": "y", "MEMCG": "y",
                               "TRANSPARENT_HUGEPAGE": "y", "THP_SWAP": "y",
                               "KALLSYMS": "y", "KPROBES": "y", "KPROBE_EVENTS": "y", "FTRACE": "y"},
                  "forbidden": ["KASAN", "KCSAN", "PROVE_LOCKING"]},
    "c1-legacy": {"path": "benchmark/config/compression-legacy.config",
                  "purposes": ["correctness"],
                  "required": {"NUMA": "n", "SWAP": "y", "ZSWAP": "y", "MEMCG": "y", "KALLSYMS": "y", "KPROBES": "y", "KPROBE_EVENTS": "y", "FTRACE": "y"},
                  "forbidden": ["XSWAP", "KASAN", "KCSAN"]},
    "c1-debug": {"path": "benchmark/config/compression-debug.config",
                 "purposes": ["correctness"],
                 "required": {"SWAP": "y", "ZSWAP": "y", "XSWAP": "y", "MEMCG": "y",
                              "KASAN": "y", "PROVE_LOCKING": "y", "FAULT_INJECTION": "y",
                              "FAILSLAB": "y", "FAIL_PAGE_ALLOC": "y",
                              "FAULT_INJECTION_DEBUG_FS": "y", "NUMA": "y", "HOTPLUG_CPU": "y",
                               "ACPI": "y", "X86_64_ACPI_NUMA": "y", "ACPI_NUMA": "y",
                               "PCI": "y", "SMP": "y",
                              "KUNIT": "y", "KUNIT_DEBUGFS": "y", "PAGE_COMPRESS_KUNIT_TEST": "y", "KALLSYMS": "y", "KPROBES": "y", "KPROBE_EVENTS": "y", "FTRACE": "y"},
                 "forbidden": ["KCSAN"]},
    "c1-kcsan": {"path": "benchmark/config/compression-kcsan.config",
                 "purposes": ["correctness"],
                 "required": {"NUMA": "n", "SWAP": "y", "ZSWAP": "y", "XSWAP": "y",
                              "MEMCG": "y", "KCSAN": "y", "KALLSYMS": "y", "KPROBES": "y", "KPROBE_EVENTS": "y", "FTRACE": "y"},
                 "forbidden": ["KASAN"]},
    "c1-noswap": {"path": "benchmark/config/compression-noswap.config",
                  "purposes": ["build-only"], "required": {},
                  "forbidden": ["SWAP", "ZSWAP", "XSWAP"]},
    "c1-no-frontends": {"path": "benchmark/config/compression-no-frontends.config",
                        "purposes": ["build-only"], "required": {"SWAP": "y"},
                        "forbidden": ["ZSWAP", "XSWAP"]},
}
# Preserve the frozen debug input; the versioned input fixes KASAN's allocator
# dependency while retaining the same correctness requirements.
CONFIGS["c1-debug-v2"] = copy.deepcopy(CONFIGS["c1-debug"])
CONFIGS["c1-debug-v2"].update(path="benchmark/config/compression-debug-v2.config",
                             forbidden=CONFIGS["c1-debug"]["forbidden"] + ["SLUB_TINY"])

GROUPS = {
    "regression": {"config_id": "c1-common", "mode": "xswap", "backend": "disk",
                   "workload": "correctness", "topology_id": "single", "subcases": []},
    "legacy-roundtrip": {"config_id": "c1-legacy", "mode": "plain", "backend": "zswap",
                         "workload": "compression", "topology_id": "single",
                         "subcases": ["roundtrip"]},
    "legacy-lifecycle": {"config_id": "c1-legacy", "mode": "plain", "backend": "zswap",
                         "workload": "compression", "topology_id": "single",
                         "subcases": ["roundtrip", "codec_switch", "invalid_codec",
                                      "memcg_balance", "memcg_offline", "memcg_limits"]},
    "compressed-roundtrip": {"config_id": "c1-common", "mode": "xswap", "backend": "compressed",
                             "workload": "compression", "topology_id": "single",
                             "subcases": ["roundtrip"]},
    "debug-failures": {"config_id": "c1-debug", "mode": "xswap", "backend": "compressed",
                       "workload": "compression", "topology_id": "single",
                       "subcases": ["invalid_codec", "library_unit", "large_folio",
                                    "memcg_balance", "memcg_offline", "memcg_limits"]},
    "race-lifecycle": {"config_id": "c1-kcsan", "mode": "xswap", "backend": "compressed",
                       "workload": "compression", "topology_id": "single",
                       "subcases": ["concurrent_fault", "codec_switch", "live_destroy"]},
    "numa-lifecycle": {"config_id": "c1-debug", "mode": "xswap", "backend": "compressed",
                       "workload": "compression", "topology_id": "numa2",
                       "subcases": ["library_unit", "guest_hotplug", "memcg_balance"]},
}
NUMA2_ARGS = ["-object", "memory-backend-ram,id=c1-node0,size=2048M",
              "-object", "memory-backend-ram,id=c1-node1,size=2048M",
              "-numa", "node,nodeid=0,memdev=c1-node0,cpus=0-1",
              "-numa", "node,nodeid=1,memdev=c1-node1,cpus=2-3"]


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def get_config(config_id="standard", root=ROOT, purpose=None):
    _need(config_id in CONFIGS, "unknown trusted configuration ID")
    value = copy.deepcopy(CONFIGS[config_id])
    if purpose is not None:
        _need(purpose in value["purposes"], "configuration is not allowed for " + str(purpose))
    path = Path(root) / value["path"]
    _need(path.is_file() and not path.is_symlink(), "missing trusted configuration file")
    value.update(id=config_id, input_config_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return value


def final_values(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        match = re.fullmatch(r"CONFIG_([A-Z0-9_]+)=(.*)", line)
        unset = re.fullmatch(r"# CONFIG_([A-Z0-9_]+) is not set", line)
        if match:
            values[match[1]] = match[2]
        elif unset:
            values[unset[1]] = "n"
    return values


def validate_final(config_id, config_path, purpose=None):
    _need(config_id in CONFIGS, "unknown trusted configuration ID")
    spec = CONFIGS[config_id]
    if purpose is not None:
        _need(purpose in spec["purposes"], "configuration is not allowed for " + str(purpose))
    values = final_values(config_path)
    for key, value in spec["required"].items():
        _need(values.get(key) == value, "required final CONFIG_" + key + "=" + value + " missing")
    for key in spec["forbidden"]:
        _need(values.get(key, "n") == "n", "forbidden final CONFIG_" + key)
    return {"config_id": config_id, "purpose": purpose,
            "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
            "values": values}


def pinned_config(protocol, config_id, root=ROOT, purpose=None):
    _need(protocol.get("protocol_revision") == 8, "named configuration contract requires revision 8")
    value = get_config(config_id, root, purpose)
    pins = protocol.get("configurations", {})
    pin = pins.get(config_id) if isinstance(pins, dict) else None
    _need(isinstance(pin, dict) and set(pin) == {"input_config_sha256"},
          "missing or malformed frozen configuration pin")
    _need(pin["input_config_sha256"] == value["input_config_sha256"],
          "frozen configuration input hash mismatch")
    return value


def topology_args(topology_id, protocol, purpose="correctness"):
    _need(topology_id in ("single", "numa2"), "unknown trusted topology")
    if topology_id == "single":
        return []
    _need(purpose == "correctness", "NUMA topology is correctness-only")
    guest = protocol.get("guest", {})
    _need(guest.get("vcpus") == 4 and guest.get("mem_mib") == 4096,
          "two-node correctness topology requires 4 vCPU and 4096 MiB total")
    return list(NUMA2_ARGS)



def validate_topology_record(protocol, result, purpose="correctness"):
    expected = topology_args(result.get("topology_id"), protocol, purpose)
    _need(result.get("topology_arguments") == expected, "recorded topology arguments mismatch")
    command = result.get("command")
    _need(isinstance(command, list) and command and all(isinstance(item, str) for item in command),
          "missing complete guest command")
    _need(command.count("-numa") == expected.count("-numa"), "guest command topology mismatch")
    if expected:
        matches = sum(command[index:index + len(expected)] == expected
                      for index in range(len(command) - len(expected) + 1))
        _need(matches == 1, "guest command omits or duplicates frozen topology arguments")


def matrix_cases(protocol):
    _need(protocol.get("protocol_revision") == 8, "correctness matrix requires revision 8")
    matrix = protocol.get("correctness_matrix")
    _need(isinstance(matrix, dict) and type(matrix.get("schema_version")) is int and matrix["schema_version"] == 1,
          "missing frozen correctness matrix")
    rows = matrix.get("cases")
    _need(isinstance(rows, list) and rows, "correctness matrix cases must be nonempty")
    ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    _need(all(isinstance(value, str) and NAME.fullmatch(value) for value in ids)
          and len(ids) == len(set(ids)), "invalid or duplicate correctness case ID")
    return rows


def correctness_group(group, config_id):
    """Resolve an exact trusted group and its explicitly versioned debug input."""
    _need(group in GROUPS, "unknown trusted correctness group")
    spec = copy.deepcopy(GROUPS[group])
    if config_id == "c1-debug-v2" and group in ("debug-failures", "numa-lifecycle"):
        spec["config_id"] = config_id
    _need(config_id == spec["config_id"], "correctness group config_id mismatch")
    return spec


def correctness_case(protocol, case_id):
    rows = matrix_cases(protocol)
    row = next((row for row in rows if row["id"] == case_id), None)
    _need(row is not None, "unknown frozen correctness case")
    group = row.get("group")
    spec = correctness_group(group, row.get("config_id"))
    _need(row.get("role") in ("baseline", "candidate"), "invalid correctness source role")
    for key in ("config_id", "mode", "backend", "workload", "topology_id"):
        _need(row.get(key) == spec[key], "correctness group " + key + " mismatch")
    if "subcases" in row:
        _need(row["subcases"] == spec["subcases"], "correctness subcase list differs from trusted group")
    extra = row.get("required_gates", [])
    _need(isinstance(extra, list) and all(isinstance(x, str) and x for x in extra)
          and len(extra) == len(set(extra)), "invalid correctness gate list")
    gates = list(BASE_GATES) if spec["workload"] == "correctness" else [
        "compression_evidence", "compression_reset", "no_new_kernel_warnings",
        *["compression_" + name for name in spec["subcases"]]]
    spec.update(copy.deepcopy(row))
    spec["subcases"] = list(GROUPS[group]["subcases"])
    spec["required_gates"] = list(dict.fromkeys(gates + extra))
    topology_args(spec["topology_id"], protocol)
    return spec


def build_only_cases(protocol):
    matrix_cases(protocol)
    rows = protocol["correctness_matrix"].get("build_only", [])
    _need(isinstance(rows, list), "build-only cases must be a list")
    ids = []
    for row in rows:
        _need(isinstance(row, dict) and isinstance(row.get("id"), str)
              and NAME.fullmatch(row["id"]), "invalid build-only case")
        _need(row.get("role") in ("baseline", "candidate"), "invalid build-only source role")
        spec = CONFIGS.get(row.get("config_id"), {})
        _need(spec.get("purposes") == ["build-only"], "case is not a trusted build-only configuration")
        ids.append(row["id"])
    _need(len(ids) == len(set(ids)), "duplicate build-only case")
    _need(not set(ids) & {row["id"] for row in matrix_cases(protocol)},
          "build-only case ID collides with a guest case")
    return copy.deepcopy(rows)


def validate_protocol(protocol, root=ROOT):
    """Validate the complete stage-specific identity contract without executing it."""
    pinned_config(protocol, "c1-common", root, "timing")
    rows = [correctness_case(protocol, row["id"]) for row in matrix_cases(protocol)]
    _need(any(row["role"] == "baseline" for row in rows)
          and any(row["role"] == "candidate" for row in rows),
          "matrix must contain baseline and candidate coverage")
    required = {("baseline", "regression"), ("baseline", "legacy-roundtrip"),
                ("candidate", "regression"), ("candidate", "legacy-lifecycle"),
                ("candidate", "compressed-roundtrip"), ("candidate", "debug-failures"),
                ("candidate", "race-lifecycle"), ("candidate", "numa-lifecycle")}
    _need(len(rows) == len(required) and {(row["role"], row["group"]) for row in rows} == required,
          "C1 requires the complete eight-case correctness matrix")
    for row in rows:
        pinned_config(protocol, row["config_id"], root, "correctness")
    builds = build_only_cases(protocol)
    _need(len(builds) == 2 and {(row["role"], row["config_id"]) for row in builds}
          == {("candidate", "c1-noswap"), ("candidate", "c1-no-frontends")},
          "C1 requires both candidate disabled build configurations")
    for row in builds:
        pinned_config(protocol, row["config_id"], root, "build-only")
    used = {row["config_id"] for row in rows + builds}
    _need(set(protocol.get("configurations", {})) == used,
          "frozen configuration pins differ from C1 coverage")
    for case in protocol.get("cases", {}).values():
        _need(case.get("config_id") == "c1-common"
              and case.get("topology_id", "single") == "single",
              "performance cases require c1-common configuration and single topology")
    return {"cases": rows, "build_only": builds}


BUILDER_FILES = ("benchmark/kernel/build.py", "benchmark/kernel/build_namespace.sh",
                 "benchmark/kernel/lifetime.py")
TOOLCHAIN_PROGRAMS = ("gcc", "ld", "as", "ar", "nm", "objcopy", "objdump", "make")


def build_environment(root=ROOT):
    """Read the same compiler tools selected by the namespace launcher."""
    root = Path(root)
    tools = {}
    for name in TOOLCHAIN_PROGRAMS:
        path = (Path("/usr/bin") / name).resolve(strict=True)
        tools[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "version": subprocess.check_output(
                           [str(path), "--version"], text=True, timeout=15).strip()}
    cc1 = Path(subprocess.check_output(
        ["/usr/bin/gcc", "-print-prog-name=cc1"], text=True, timeout=15).strip()).resolve(strict=True)
    tools["cc1"] = {"sha256": hashlib.sha256(cc1.read_bytes()).hexdigest()}
    return {"builder": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                        for name in BUILDER_FILES}, "toolchain": tools}


def verify_build_binding(root, manifest_path, commit, config_id, current_environment=None, require_counted=True):
    """Require the sidecar emitted by counted configured-build preparation."""
    root, path = Path(root), Path(manifest_path)
    if not path.is_absolute():
        path = root / path
    binding_path = path.with_name("configured-build.json")
    _need(binding_path.is_file() and not binding_path.is_symlink(),
          "missing configured build provenance")
    def checked_bytes(file):
        relative = file.relative_to(root)
        parent = root
        for part in relative.parts:
            parent /= part
            _need(not parent.is_symlink(), "configured build provenance path uses a symlink")
        _need(file.resolve().is_relative_to(root.resolve()), "configured build provenance escapes repository")
        return file.read_bytes()

    binding = json.loads(checked_bytes(binding_path))
    _need(type(binding.get("schema_version")) is int and binding["schema_version"] == 1
          and binding.get("source_commit") == commit
          and binding.get("config_id") == config_id,
          "configured build provenance identity mismatch")
    _need(binding.get("build_manifest_sha256") == hashlib.sha256(checked_bytes(path)).hexdigest(),
          "configured build manifest changed")
    _need(binding.get("input_config_sha256") == get_config(config_id, root)["input_config_sha256"],
          "configured build input changed")
    tree = subprocess.check_output(["git", "-C", str(root / "linux"), "rev-parse",
                                    commit + "^{tree}"], text=True, timeout=15).strip()
    _need(binding.get("source_tree") == tree, "configured build source tree mismatch")
    environment = current_environment if current_environment is not None else build_environment(root)
    _need(binding.get("environment") == environment, "configured build environment changed")
    if require_counted:
        campaign, evaluation = binding.get("campaign"), binding.get("evaluation_id")
        _need(isinstance(campaign, str) and NAME.fullmatch(campaign)
              and isinstance(evaluation, str) and re.fullmatch(r"[0-9a-f]{32}", evaluation),
              "configured build lacks counted source identity")
        source = root / "campaigns" / campaign
        protocol_path = source / "protocol.json"
        _need(hashlib.sha256(checked_bytes(protocol_path)).hexdigest() == binding.get("protocol_sha256"),
              "configured build source protocol changed")
        protocol = json.loads(checked_bytes(protocol_path))
        ledger = json.loads(checked_bytes(source / "ledger/ledger.json"))
        records = [row for row in ledger if row.get("id") == evaluation]
        _need(len(records) == 1, "configured build source record missing or duplicate")
        record = records[0]
        _need(record.get("action") == "build-coverage" and record.get("status") == "BUILD_VERIFIED"
              and record.get("build_reserved") is True and record.get("commit") == commit
              and record.get("config_id") == config_id
              and record.get("build_manifest_sha256") == binding["build_manifest_sha256"],
              "configured build source record differs from artifact")
        budget = json.loads(checked_bytes(source / "ledger/budget.json"))
        spent = budget.get("builds")
        reserved = sum(row.get("build_reserved") is True for row in ledger)
        _need(type(spent) is int and 1 <= reserved <= spent <= protocol["budget"]["build_attempts"],
              "configured build was not counted within its source budget")
    return binding
