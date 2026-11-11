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


# New input files preserve all C1 bytes and keep test hooks out of timing.
for _name, _base, _independent, _test in (
        ("c2-independent", "c1-common", True, False),
        ("c2-debug-common", "c1-debug-v2", False, True),
        ("c2-debug-independent", "c1-debug-v2", True, True),
        ("c2-race-common", "c1-kcsan", False, True),
        ("c2-race-independent", "c1-kcsan", True, True)):
    _config = copy.deepcopy(CONFIGS[_base])
    _config.update(path="benchmark/config/compression-" + _name + ".config",
                   purposes=["correctness"])
    _config["required"].update(MEMCG="y", ZSMALLOC="y", CRYPTO_LZO="y",
                               XSWAP_TEST="y" if _test else "n")
    if _independent:
        _config["required"].update(ZSWAP="n", XSWAP="y", PAGE_COMPRESS="y")
    if _name == "c2-independent":
        _config["purposes"].append("expected-negative")
    CONFIGS[_name] = _config
del _name, _base, _independent, _test, _config

C2_CONTRACT = "xswap-independent-v1"
C2_BINDING_KEYS = ("contract_id", "source_role", "source_commit", "source_tree", "frontend",
                   "observer_id", "observer_symbol")
C2_TOPOLOGY = "c2-numa2-nehalem-v1"
C2_BASELINE = "5e84ca928deeacb4eee656806a003f27d1eca82f"
C2_PREDECESSOR = "7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad"
C2_OBSERVER = {
    "id": "pid_kretprobe_frontend_v2", "instrumented": True,
    "clock": "monotonic_raw", "maxactive": 64, "buffer_size_kb": 16, "per_target_decode": True,
    "target_residency": "pagemap_and_mincore", "loss_policy": "fail",
    "isolation_strategy": "mlockall_current_future_target_munlock_v1",
    "isolation_proof": "raw_smaps_v1",
    "arms": {"baseline": {"symbol": "zswap_load", "success_return": 0},
             "candidate": {"symbol": "xswap_load_folio", "success_return": 0}},
}
C2_ADMISSION = {
    "codec": "lzo", "cap_unit": "allocator_backing_pages", "percent": 20,
    "physical_bypass_pages": 0, "raw_admission": False,
    "legacy_controls": "zswap_only",
}
C2_GROUPS = {
    "physical-regression": {"config_id": "c1-common", "mode": "xswap", "backend": "disk",
        "workload": "correctness", "topology_id": "single", "frontend": "physical",
        "subcases": ["physical_regression"]},
    "legacy-roundtrip": {"config_id": "c1-legacy", "mode": "plain", "backend": "zswap",
        "workload": "compression", "topology_id": "single", "frontend": "legacy",
        "subcases": ["legacy_roundtrip"]},
    "legacy-lifecycle": {"config_id": "c1-legacy", "mode": "plain", "backend": "zswap",
        "workload": "compression", "topology_id": "single", "frontend": "legacy",
        "subcases": ["legacy_roundtrip", "legacy_codec_switch", "legacy_invalid_codec",
                     "legacy_memcg_balance", "legacy_memcg_offline", "legacy_memcg_limit"]},
    "independent-roundtrip": {"config_id": "c2-independent", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": "single", "frontend": "independent",
        "subcases": ["independent_roundtrip", "zero_control"]},
    "coexistence": {"config_id": "c1-common", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": "single", "frontend": "mixed",
        "subcases": ["xswap_legacy_disabled", "xswap_legacy_quota_zero", "ordinary_legacy_disabled",
                     "ordinary_legacy_quota_zero", "both_live"]},
    "fallback": {"config_id": "c2-independent", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": "single", "frontend": "independent",
        "subcases": ["cap_bound", "incompressible_fallback", "physical_fallback"]},
    "debug-common": {"config_id": "c2-debug-common", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": "single", "frontend": "mixed",
        "subcases": ["library_unit", "legacy_lifecycle", "independent_large_folio"]},
    "debug-independent": {"config_id": "c2-debug-independent", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": "single", "frontend": "independent",
        "subcases": ["incompressible_control", "no_target_retention", "swap_charge_denied",
                     "init_refusal", "entry_refusal", "charge_refusal", "publish_refusal",
                     "rollback_first", "rollback_middle", "rollback_last", "decode_old_backing",
                     "write_completion_error", "read_completion_error", "reused_slot", "live_destroy"]},
    "numa-independent": {"config_id": "c2-debug-independent", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": C2_TOPOLOGY, "frontend": "independent",
        "subcases": ["independent_node0", "independent_node1", "live_cpu_hotplug", "owner_balance"]},
    "race-common": {"config_id": "c2-race-common", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": "single", "frontend": "mixed",
        "subcases": ["mixed_load_free", "legacy_pool_offline", "mixed_live_destroy"]},
    "race-independent": {"config_id": "c2-race-independent", "mode": "xswap", "backend": "compressed",
        "workload": "compression", "topology_id": "single", "frontend": "independent",
        "subcases": ["fault_cow_invalidate", "reused_slot_overlap",
                     "live_destroy_overlap", "backing_swapoff_overlap"]},
}
C2_CASES = (
    ("b-regression", "baseline", "physical-regression"),
    ("b-legacy", "baseline", "legacy-roundtrip"),
    ("c-regression", "candidate", "physical-regression"),
    ("c-legacy", "candidate", "legacy-lifecycle"),
    ("c-independent", "candidate", "independent-roundtrip"),
    ("c-coexistence", "candidate", "coexistence"),
    ("c-fallback", "candidate", "fallback"),
    ("c-debug-common", "candidate", "debug-common"),
    ("c-debug-independent", "candidate", "debug-independent"),
    ("c-numa-independent", "candidate", "numa-independent"),
    ("c-race-common", "candidate", "race-common"),
    ("c-race-independent", "candidate", "race-independent"),
)
C2_NEGATIVE = {"id": "b-independent-unsupported", "role": "baseline",
               "config_id": "c2-independent", "expectation": "xswap_unavailable_without_zswap"}

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
NUMA2_SOCKETS_V2_SMP = "4,sockets=2,cores=2,threads=1"
NUMA2_NEHALEM_V3_CPU = "Nehalem-v1,vme=off,enforce=on"
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


def validate_final(config_id, config_path, purpose=None, *, protocol_revision=None):
    _need(config_id in CONFIGS, "unknown trusted configuration ID")
    spec = CONFIGS[config_id]
    if purpose is not None:
        _need(purpose in spec["purposes"], "configuration is not allowed for " + str(purpose))
    values = final_values(config_path)
    for key, value in spec["required"].items():
        _need(values.get(key) == value, "required final CONFIG_" + key + "=" + value + " missing")
    for key in spec["forbidden"]:
        _need(values.get(key, "n") == "n", "forbidden final CONFIG_" + key)
    if protocol_revision == 9:
        expected_test = "y" if config_id.startswith(("c2-debug-", "c2-race-")) else "n"
        _need(values.get("XSWAP_TEST", "n") == expected_test,
              "C2 final CONFIG_XSWAP_TEST differs from its exact configuration purpose")
    return {"config_id": config_id, "purpose": purpose,
            "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
            "values": values}


def pinned_config(protocol, config_id, root=ROOT, purpose=None):
    _need(protocol.get("protocol_revision") in (8, 9), "named configuration contract requires revision 8 or 9")
    value = get_config(config_id, root, purpose)
    pins = protocol.get("configurations", {})
    pin = pins.get(config_id) if isinstance(pins, dict) else None
    _need(isinstance(pin, dict) and set(pin) == {"input_config_sha256"},
          "missing or malformed frozen configuration pin")
    _need(pin["input_config_sha256"] == value["input_config_sha256"],
          "frozen configuration input hash mismatch")
    return value


def topology_args(topology_id, protocol, purpose="correctness"):
    _need(topology_id in ("single", "numa2", "numa2-sockets-v2", "numa2-nehalem-v3", C2_TOPOLOGY), "unknown trusted topology")
    if topology_id == "single":
        return []
    _need(purpose == "correctness", "NUMA topology is correctness-only")
    guest = protocol.get("guest", {})
    _need(guest.get("vcpus") == 4 and guest.get("mem_mib") == 4096,
          "two-node correctness topology requires 4 vCPU and 4096 MiB total")
    return list(NUMA2_ARGS)



def smp_argument(topology_id, protocol):
    """Keep legacy CPU defaults; align the versioned NUMA layout by socket."""
    topology_args(topology_id, protocol)
    if topology_id in ("numa2-sockets-v2", "numa2-nehalem-v3", C2_TOPOLOGY):
        return NUMA2_SOCKETS_V2_SMP
    return str(protocol["guest"]["vcpus"])


def effective_accelerator(topology_id, accelerator):
    """Version only the auxiliary CPU; frozen single-topology timing stays max."""
    if topology_id not in ("numa2-nehalem-v3", C2_TOPOLOGY):
        return list(accelerator)
    _need(accelerator == ["-accel", "tcg,thread=multi,tb-size=256",
                          "-machine", "pc", "-cpu", "max"],
          "Nehalem topology requires the frozen TCG accelerator")
    return [*accelerator[:-1], NUMA2_NEHALEM_V3_CPU]


def validate_topology_record(protocol, result, purpose="correctness"):
    if result.get("topology_id") == C2_TOPOLOGY:
        _need(protocol.get("protocol_revision") == 9
              and result.get("config_id") == "c2-debug-independent"
              and result.get("correctness_group") == "numa-independent",
              "C2 NUMA topology identity mismatch")
        adapted = dict(result, topology_id="numa2-nehalem-v3",
                       config_id="c1-debug-v2", correctness_group="numa-lifecycle")
        validate_topology_record(protocol, adapted, purpose)
        return
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
    if result.get("topology_id") in ("numa2-sockets-v2", "numa2-nehalem-v3"):
        nehalem = result["topology_id"] == "numa2-nehalem-v3"
        _need(not any(item.startswith(("-M", "--M")) for item in command),
              "guest command uses a noncanonical machine alias")
        _need(result.get("config_id") == "c1-debug-v2"
              and result.get("correctness_group") == "numa-lifecycle",
              "socket topology requires the versioned NUMA correctness group")

        if nehalem:
            _need(result.get("workload") == "compression"
                  and result.get("backend") == "compressed" and result.get("mode") == "xswap",
                  "Nehalem topology is compression correctness-only")
            _need(protocol.get("accelerator", {}).get("require") == "tcg"
                  and result.get("accelerator") == "tcg",
                  "Nehalem topology requires TCG")
            # These alternative configuration channels could override the CPU
            # or memory layout without changing the canonical option values.
            _need(not any(item.startswith(("-global", "--global", "-set", "--set",
                                          "-readconfig", "--readconfig", "-device", "--device",
                                          "-enable-kvm", "--enable-kvm"))
                          for item in command), "guest command has a topology override")

        def option_values(arguments, option):
            if nehalem:
                for item in arguments:
                    normalized = item[1:] if item.startswith("--") else item
                    # -machine and -monitor are distinct from the short -m.
                    if option == "-m" and normalized.startswith(("-machine", "-monitor")):
                        continue
                    _need(not normalized.startswith(option) or item == option,
                          "noncanonical guest topology option: " + option)
            _need(not any(item.startswith(option + "=") or item == "-" + option
                          or item.startswith("-" + option + "=") for item in arguments),
                  "noncanonical guest topology option: " + option)
            indexes = [index for index, item in enumerate(arguments) if item == option]
            _need(all(index + 1 < len(arguments) for index in indexes),
                  "missing guest topology option value: " + option)
            return [arguments[index + 1] for index in indexes]

        _need(option_values(command, "-smp") == [NUMA2_SOCKETS_V2_SMP],
              "guest command CPU topology mismatch or duplicate -smp")
        _need(option_values(command, "-m") == ["4096"], "guest command memory topology mismatch")
        for option in ("-object", "-numa"):
            _need(option_values(command, option) == option_values(expected, option),
                  "guest command NUMA topology mismatch or duplicate " + option)
        accelerator = protocol.get("accelerator", {}).get("qemu")
        _need(isinstance(accelerator, list) and all(isinstance(item, str) for item in accelerator),
              "missing frozen CPU and machine arguments")
        if nehalem:
            accelerator = effective_accelerator(result["topology_id"], accelerator)
            _need(result.get("qemu_accel") == accelerator,
                  "recorded effective accelerator mismatch")
            _need(command[1:1 + len(accelerator)] == accelerator,
                  "guest command effective accelerator mismatch")
        for option in (("-accel", "-cpu", "-machine") if nehalem else ("-cpu", "-machine")):
            frozen = option_values(accelerator, option)
            _need(len(frozen) == 1 and option_values(command, option) == frozen,
                  "guest command differs from frozen " + option)


def matrix_cases(protocol):
    _need(protocol.get("protocol_revision") in (8, 9), "correctness matrix requires revision 8 or 9")
    matrix = protocol.get("correctness_matrix")
    _need(isinstance(matrix, dict) and type(matrix.get("schema_version")) is int and matrix["schema_version"] == 1,
          "missing frozen correctness matrix")
    rows = matrix.get("cases")
    _need(isinstance(rows, list) and rows, "correctness matrix cases must be nonempty")
    ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    _need(all(isinstance(value, str) and NAME.fullmatch(value) for value in ids)
          and len(ids) == len(set(ids)), "invalid or duplicate correctness case ID")
    return rows


def correctness_group(group, config_id, topology_id=None):
    """Resolve an exact trusted group and its explicitly versioned debug input."""
    _need(group in GROUPS, "unknown trusted correctness group")
    spec = copy.deepcopy(GROUPS[group])
    if config_id == "c1-debug-v2" and group in ("debug-failures", "numa-lifecycle"):
        spec["config_id"] = config_id
    _need(config_id == spec["config_id"], "correctness group config_id mismatch")
    if topology_id in ("numa2-sockets-v2", "numa2-nehalem-v3"):
        _need(group == "numa-lifecycle" and config_id == "c1-debug-v2",
              "socket topology requires the versioned NUMA correctness group")
        spec["topology_id"] = topology_id
    _need(topology_id is None or topology_id == spec["topology_id"],
          "correctness group topology_id mismatch")
    return spec


def correctness_case(protocol, case_id):
    if protocol.get("protocol_revision") == 9:
        return c2_correctness_case(protocol, case_id)
    rows = matrix_cases(protocol)
    row = next((row for row in rows if row["id"] == case_id), None)
    _need(row is not None, "unknown frozen correctness case")
    group = row.get("group")
    spec = correctness_group(group, row.get("config_id"), row.get("topology_id"))
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
    if protocol.get("protocol_revision") == 9:
        return validate_c2_protocol(protocol, root)
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


def c2_correctness_group(group, config_id, topology_id):
    _need(group in C2_GROUPS, "unknown C2 correctness group")
    spec = copy.deepcopy(C2_GROUPS[group])
    _need(config_id == spec["config_id"] and topology_id == spec["topology_id"],
          "C2 group configuration/topology mismatch")
    return spec


def c2_correctness_case(protocol, case_id):
    row = next((row for row in matrix_cases(protocol) if row["id"] == case_id), None)
    _need(row is not None, "unknown frozen C2 correctness case")
    expected = next((item for item in C2_CASES if item[0] == case_id), None)
    _need(expected is not None and (row.get("role"), row.get("group")) == expected[1:],
          "C2 correctness case source/group mismatch")
    spec = c2_correctness_group(row["group"], row.get("config_id"), row.get("topology_id"))
    for key in ("mode", "backend", "workload", "frontend"):
        _need(row.get(key) == spec[key], "C2 correctness " + key + " mismatch")
    _need(row.get("subcases", spec["subcases"]) == spec["subcases"], "C2 phase list mismatch")
    extra = row.get("required_gates", [])
    _need(isinstance(extra, list) and all(isinstance(value, str) and value for value in extra)
          and len(extra) == len(set(extra)), "invalid C2 correctness gate list")
    spec.update(copy.deepcopy(row))
    spec["subcases"] = list(C2_GROUPS[row["group"]]["subcases"])
    base = BASE_GATES if spec["workload"] == "correctness" else ["no_new_kernel_warnings"]
    spec["required_gates"] = list(dict.fromkeys([
        *base, "configuration_identity", "source_role_identity", "compression_evidence",
        "compression_reset", *["compression_" + name for name in spec["subcases"]], *extra]))
    # Linked-config validation supplies sanitizer gates to the verified matrix
    # summary, after raw parser equivalence. Serial markers cannot assert them.
    topology_args(spec["topology_id"], protocol)
    return spec


def negative_build_cases(protocol):
    if protocol.get("protocol_revision") != 9:
        return []
    rows = protocol.get("correctness_matrix", {}).get("negative_builds")
    _need(rows == [C2_NEGATIVE], "C2 requires its exact expected-negative anchor build")
    return copy.deepcopy(rows)


def validate_c2_protocol(protocol, root=ROOT):
    _need(protocol.get("contract_id") == C2_CONTRACT and protocol.get("baseline_commit") == C2_BASELINE,
          "C2 contract/baseline identity mismatch")
    _need(protocol.get("predecessor_commit") == C2_PREDECESSOR,
          "C2 must preserve exact C1 predecessor provenance")
    _need(protocol.get("compression_observer") == C2_OBSERVER,
          "C2 source-role observer contract mismatch")
    _need(protocol.get("compression_admission") == C2_ADMISSION, "C2 admission contract mismatch")
    pinned_config(protocol, "c1-common", root, "timing")
    rows = [c2_correctness_case(protocol, row["id"]) for row in matrix_cases(protocol)]
    _need([row["id"] for row in rows] == [case[0] for case in C2_CASES],
          "C2 requires twelve ordered correctness rows")
    builds = build_only_cases(protocol)
    _need(builds == [
        {"id": "c-noswap", "role": "candidate", "config_id": "c1-noswap"},
        {"id": "c-no-frontends", "role": "candidate", "config_id": "c1-no-frontends"}],
        "C2 requires both exact disabled-build rows")
    negative = negative_build_cases(protocol)
    for row in rows:
        pinned_config(protocol, row["config_id"], root, "correctness")
    for row in builds:
        pinned_config(protocol, row["config_id"], root, "build-only")
    for row in negative:
        pinned_config(protocol, row["config_id"], root, "expected-negative")
    used = {row["config_id"] for row in rows + builds + negative}
    _need(set(protocol.get("configurations", {})) == used, "C2 frozen configuration set mismatch")
    for case in protocol.get("cases", {}).values():
        _need(case.get("config_id") == "c1-common" and case.get("topology_id") == "single",
              "C2 performance requires unchanged common/single identity")
    return {"cases": rows, "build_only": builds, "negative_builds": negative}


def validate_negative_final(config_id, config_path, source_commit):
    _need(config_id == "c2-independent" and source_commit == C2_BASELINE,
          "expected-negative configuration applies only to the exact C2 anchor")
    values = final_values(config_path)
    _need(values.get("SWAP") == "y" and values.get("MEMCG") == "y",
          "expected-negative build lacks ordinary swap/memcg support")
    _need(values.get("ZSWAP", "n") == "n" and values.get("XSWAP", "n") == "n",
          "old anchor unexpectedly enables a compressed frontend")
    _need(values.get("PAGE_COMPRESS", "n") == "n" and values.get("XSWAP_TEST", "n") == "n",
          "expected-negative anchor contains candidate-only symbols")
    return {"status": "EXPECTED_UNSUPPORTED_CONFIG", "guest_eligible": False,
            "config_id": config_id, "source_commit": source_commit,
            "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
            "values": values}


def runtime_source_binding(protocol, root, build, config_id, backend, case=None):
    """Derive revision-9 arm identity from retained build and native source records."""
    _need(protocol.get("protocol_revision") == 9 and protocol.get("contract_id") == C2_CONTRACT,
          "C2 runtime source requires its exact contract")
    root = Path(root)
    _need(isinstance(build, str) and NAME.fullmatch(build), "invalid C2 build identity")

    def read_bound(relative):
        path = root / relative
        parent = root
        for part in Path(relative).parts:
            parent /= part
            _need(not parent.is_symlink(), "C2 source identity uses a symlink")
        _need(path.is_file(), "missing C2 source identity artifact: " + str(relative))
        return json.loads(path.read_bytes())

    prefix = Path("benchmark/kernel/builds") / build
    manifest = read_bound(prefix / "result.json")
    binding = read_bound(prefix / "configured-build.json")
    commit, tree = manifest.get("commit"), binding.get("source_tree")
    _need(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)
          and isinstance(tree, str) and re.fullmatch(r"[0-9a-f]{40}", tree),
          "C2 build lacks exact source identity")
    _need(manifest.get("passed") is True and manifest.get("exit_code") == 0
          and binding.get("source_commit") == commit and binding.get("config_id") == config_id
          and binding.get("build_manifest_sha256")
              == hashlib.sha256((root / prefix / "result.json").read_bytes()).hexdigest(),
          "C2 build source/configuration binding mismatch")
    _need(binding.get("guest_eligible", True) is True,
          "expected-negative build is never guest eligible")
    # The reservation and launch share the native counted build, exact tree and
    # current builder/toolchain identity; a copied sidecar cannot choose an arm.
    verify_build_binding(root, root / prefix / "result.json", commit, config_id)
    validate_final(config_id, root / prefix / "output/.config",
                   "correctness" if case else "timing", protocol_revision=9)
    role = "baseline" if commit == protocol.get("baseline_commit") else "candidate"
    if role == "candidate":
        campaign = protocol.get("campaign")
        _need(isinstance(campaign, str) and NAME.fullmatch(campaign), "invalid C2 campaign source")
        candidates = root / "campaigns" / campaign / "candidates"
        matches = []
        for path in candidates.glob("*/static.json"):
            record = read_bound(path.relative_to(root))
            if record.get("status") == "SCOPE_PASS" and record.get("candidate_commit") == commit:
                matches.append(record)
        _need(len(matches) == 1 and matches[0].get("parent") == protocol["baseline_commit"],
              "C2 build has no unique current native candidate source")
    if case is not None:
        _need(case.get("role") == role, "C2 runtime source differs from frozen correctness role")
    frontend = (case["frontend"] if case is not None else
                ("legacy" if role == "baseline" else "independent") if backend == "compressed"
                else "physical")
    observer = C2_OBSERVER["arms"][role]
    return {"contract_id": C2_CONTRACT, "source_role": role, "source_commit": commit,
            "source_tree": tree, "frontend": frontend, "observer_id": C2_OBSERVER["id"],
            "observer_symbol": observer["symbol"]}


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


def verify_build_binding(root, manifest_path, commit, config_id, current_environment=None, require_counted=True, expected_status="BUILD_VERIFIED"):
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
    _need(expected_status in ("BUILD_VERIFIED", "EXPECTED_UNSUPPORTED_CONFIG"),
          "unknown configured build outcome")
    if expected_status == "EXPECTED_UNSUPPORTED_CONFIG":
        _need(binding.get("guest_eligible") is False
              and binding.get("outcome") == expected_status,
              "expected-negative build lacks its typed disposition")
    else:
        _need(binding.get("guest_eligible", True) is True
              and binding.get("outcome", "BUILD_VERIFIED") == "BUILD_VERIFIED",
              "negative build cannot satisfy positive build provenance")
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
        _need(record.get("action") == "build-coverage" and record.get("status") == expected_status
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
