# SPDX-License-Identifier: GPL-2.0-only
"""Fail-closed parsing for the separate xswap pilot."""
import math
import re

PHASES = ("before", "after_pressure", "fork_shared", "after_children", "after_reads", "after_settle", "after_repressure", "after_resettle")
FIELDS = {"clusters_max", "clusters_mapped", "usage_pages", "tail_free", "grows", "shrinks",
          "clusters_nonempty", "clusters_free", "highest_nonempty_plus1", "highest_blocker_plus1",
          "cache_only_pages", "referenced_pages", "highest_cache_only_plus1",
          "highest_referenced_plus1", "cache_only_clusters"}

def parse(log):
    log = log.replace("\r\n", "\n")
    errors = []
    snapshots = {}
    blocks = list(re.finditer(r"^META_BEGIN (\w+)\n(.*?)^META_END$", log, re.M | re.S))
    for m in blocks:
        phase, body = m.groups()
        pairs = re.findall(r"^(\w+) (\d+)$", body, re.M)
        values = dict((k, int(v)) for k, v in pairs)
        if phase in snapshots or len(pairs) != len(values) or set(values) != FIELDS or len(body.splitlines()) != len(pairs):
            errors.append("invalid snapshot " + phase)
        if values.get("clusters_mapped", 0) > values.get("clusters_max", 0):
            errors.append("mapped clusters exceed maximum")
        mapped = values.get("clusters_mapped", 0)
        # Scan counters are sequential, not one globally atomic usage sample.
        for key in ("clusters_nonempty", "clusters_free", "highest_nonempty_plus1",
                    "highest_blocker_plus1", "highest_cache_only_plus1",
                    "highest_referenced_plus1", "cache_only_clusters"):
            if values.get(key, 0) > mapped:
                errors.append("scan bound exceeded: " + key)
        snapshots[phase] = values
    if [m[1] for m in blocks] != list(PHASES):
        errors.append("missing, repeated, or out-of-order snapshots")
    type_lines = re.findall(r"^XSWAP_TYPE (\d+)$", log, re.M)
    swap_type = int(type_lines[0]) if len(type_lines) == 1 else None
    if swap_type is None or not 0 <= swap_type < 32:
        errors.append("invalid xswap type")
    hdrs = list(re.finditer(r"^LATENCY_BEGIN samples=(\d+) skipped=(\d+) minor=(\d+) major=(\d+)$", log, re.M))
    latblocks = re.findall(r"^LATENCY_BEGIN [^\n]+\n(.*?)^LATENCY_END$", log, re.M | re.S)
    pairs = re.findall(r"^LATENCY_NS (\d+) TYPE (\d+)$", log, re.M)
    samples = [int(n) for n, _ in pairs]
    valid_samples = (len(hdrs) == len(latblocks) == 1 and len(samples) >= 1000
                     and len(samples) == int(hdrs[0][1])
                     and int(hdrs[0][1]) + int(hdrs[0][2]) == 16384
                     and len(latblocks[0].splitlines()) == len(samples)
                     and all(re.fullmatch(r"LATENCY_NS [0-9]+ TYPE [0-9]+", line) for line in latblocks[0].splitlines())
                     and all(n > 0 for n in samples))
    type_valid = bool(pairs) and all(int(t) == swap_type for _, t in pairs)
    counts = []
    disks = []
    for phase in ("BEFORE", "AFTER"):
        found = re.findall(r"^VMSTAT_" + phase + r"\n((?:(?:pswpin|pswpout|zswpin|zswpout) \d+\n)+)", log, re.M)
        entries = re.findall(r"(\w+) (\d+)", found[0]) if len(found) == 1 else []
        values = dict((k, int(v)) for k, v in entries)
        if set(values) != {"pswpin", "pswpout", "zswpin", "zswpout"} or len(entries) != 4:
            errors.append("missing or malformed vmstat " + phase)
        counts.append(values)
        disk = re.findall(r"^DISKSTAT_" + phase + r"\n([ 0-9]+)$", log, re.M)
        fields = [int(x) for x in disk[0].split()] if len(disk) == 1 else []
        if len(fields) < 11:
            errors.append("missing or malformed diskstat " + phase)
            fields = [0] * 11
        disks.append(fields)
    delta = {k: counts[1].get(k, 0)-v for k, v in counts[0].items()}
    disk_delta = {"sectors_read": disks[1][2]-disks[0][2], "sectors_written": disks[1][6]-disks[0][6]}
    if any(v < 0 for v in list(delta.values()) + list(disk_delta.values())):
        errors.append("decreasing activity counter")
    diagnostics = [line for line in log.splitlines() if re.search(
        r"WARNING:|BUG:|Oops:|Kernel panic|page allocation failure:|Out of memory:|Killed process|UBSAN:|KASAN:|KCSAN:|kernel BUG|possible circular locking|INFO: task .*blocked", line)]
    bootids = re.findall(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", log, re.M)
    def once(marker):
        return log.splitlines().count(marker) == 1
    swaps = re.findall(r"^SWAPS_BEGIN\n(.*?)^SWAPS_END$", log, re.M | re.S)
    empty = len(swaps) == 1 and len(swaps[0].splitlines()) == 1 and swaps[0].startswith("Filename")
    gates = {
        "evidence_complete": not errors, "data_roundtrip": once("KERNEL_WORKLOAD_PASS"),
        "repressure_data": once("REPRESSURE_DATA_PASS"),
        "fork_shared": once("FORK_SHARED_PASS"), "cow": once("COW_PASS"),
        "destroy_live_data": once("DESTROY_LIVE_PASS"), "swapoff_live_data": once("SWAPOFF_LIVE_PASS"),
        "empty_swaps": empty and once("EMPTY_SWAPS_PASS"),
        "runtime_xswap": once("XSWAP_RUNTIME_PASS"), "sample_count": valid_samples,
        "every_sample_xswap": type_valid, "swap_activity": delta.get("pswpin", 0)>0 and delta.get("pswpout", 0)>0,
        "no_kernel_warnings": not diagnostics,
        "kernel_log_complete": once("KERNEL_LOG_BEGIN") and once("KERNEL_LOG_END"),
        "boot_identity": len(bootids) == 1,
        "completed": once("XSWAP_PASS") and "XSWAP_FAIL" not in log,
    }
    metrics = {}
    if valid_samples and type_valid:
        metrics["swapped_first_access_p99_us"] = sorted(samples)[math.ceil(len(samples)*.99)-1]/1000
        metrics["samples"] = len(samples)
    if not errors:
        metrics["mapped_clusters_by_phase"] = {k: v["clusters_mapped"] for k, v in snapshots.items()}
        metrics["sampled_mapped_clusters_max"] = max(v["clusters_mapped"] for v in snapshots.values())
    live = re.findall(r"^DESTROY_LIVE_XSWAP_PTES (\d+)$", log, re.M)
    gates["destroy_live_xswap_ptes"] = len(live) == 1 and 0 < int(live[0]) <= 16384
    timing = re.findall(r"^WORKLOAD_NS (\d+)$", log, re.M)
    gates["workload_duration"] = len(timing) == 1 and int(timing[0]) > 0
    if gates["workload_duration"]:
        metrics["workload_wall_seconds"] = int(timing[0])/1e9
    if not errors:
        metrics["mapped_clusters_after_settle"] = snapshots["after_settle"]["clusters_mapped"]
        metrics["mapped_clusters_after_repressure"] = snapshots["after_repressure"]["clusters_mapped"]
        metrics["mapped_clusters_after_resettle"] = snapshots["after_resettle"]["clusters_mapped"]
        metrics["grows_after_settle"] = snapshots["after_settle"]["grows"]
        metrics["shrinks_after_settle"] = snapshots["after_settle"]["shrinks"]
    return dict(gates=gates, metrics=metrics, snapshots=snapshots, swap_delta=delta,
                disk_delta=disk_delta, diagnostics=diagnostics, evidence_errors=errors,
                boot_id=bootids[0] if len(bootids)==1 else None, xswap_type=swap_type)
