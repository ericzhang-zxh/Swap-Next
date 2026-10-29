# SPDX-License-Identifier: GPL-2.0-only
"""Run-validity rules for approved swap-standard revisions. No guest is started here.

From revision 3 on, a run is invalid, and the adapter reruns it, when the guest
reports a TSC-unstable clocksource fallback, the wall time exceeds 1.5 times
the running median of prior valid runs of the same case, or more than 60
seconds elapse before QEMU is launched. Invalid attempts stay in the report.
Revision 6 is the TCG kbench screen and additionally excludes the build workload.
"""
import math
import statistics


CLOCKSOURCE_FALLBACK_MARKERS = (
    "marking tsc unstable",
    "clocksource 'tsc' as unstable",
    "switched to clocksource hpet",
    "switched to clocksource acpi_pm",
    "switched to clocksource jiffies",
    "switched to clocksource refined-jiffies",
)


def clocksource_invalid(serial_text):
    """True when the guest log shows TSC unstable or a non-TSC fallback."""
    if not isinstance(serial_text, str):
        raise ValueError("serial log must be text")
    lowered = serial_text.lower()
    return any(marker in lowered for marker in CLOCKSOURCE_FALLBACK_MARKERS)


def launch_blocked(protocol_revision, pre_qemu_seconds, limit=60):
    """Revisions from 3 on do not launch QEMU after a pre-launch stall over the limit."""
    if isinstance(protocol_revision, bool) or not isinstance(protocol_revision, int):
        raise ValueError("protocol revision")
    if (isinstance(pre_qemu_seconds, bool) or not isinstance(pre_qemu_seconds, (int, float))
            or not math.isfinite(pre_qemu_seconds) or pre_qemu_seconds < 0):
        raise ValueError("pre_qemu_seconds")
    return protocol_revision >= 3 and pre_qemu_seconds > limit


def wall_outlier(wall, prior, factor, min_samples):
    """True when wall exceeds factor times the median of enough prior samples."""
    if (isinstance(wall, bool) or not isinstance(wall, (int, float))
            or not math.isfinite(wall) or wall < 0):
        raise ValueError("wall_seconds")
    if (isinstance(factor, bool) or not isinstance(factor, (int, float))
            or not math.isfinite(factor) or factor <= 1):
        raise ValueError("wall factor")
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 1:
        raise ValueError("wall sample count")
    samples = []
    for value in prior:
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            continue
        samples.append(value)
    if len(samples) < min_samples:
        return False
    return wall > factor * statistics.median(samples)


def parse_loadavg(text):
    parts = text.split()
    if len(parts) < 3:
        raise ValueError("loadavg")
    values = []
    for part in parts[:3]:
        value = float(part)
        if not math.isfinite(value) or value < 0:
            raise ValueError("loadavg")
        values.append(value)
    return {"loadavg_1m": values[0], "loadavg_5m": values[1], "loadavg_15m": values[2]}


def parse_psi(text):
    """Parse /proc/pressure text. Unrecognized lines are kept raw."""
    parsed = {}
    for line in text.splitlines():
        bits = line.split()
        if len(bits) < 2:
            continue
        kind, values = bits[0], {}
        raw = False
        for item in bits[1:]:
            if "=" not in item:
                raw = True
                break
            key, value = item.split("=", 1)
            values[key] = float(value)
        parsed[kind] = {"raw": line} if raw else values
    return parsed


def read_host_load(loadavg_path, pressure_root):
    """Snapshot loadavg and PSI. Missing PSI is omitted; loadavg is required."""
    data = parse_loadavg(loadavg_path.read_text())
    psi = {}
    if pressure_root.is_dir():
        for kind in ("cpu", "memory", "io"):
            path = pressure_root / kind
            if path.is_file():
                psi[kind] = parse_psi(path.read_text())
    if psi:
        data["psi"] = psi
    return data


def classify_attempt(result, prior_walls, rules):
    """Return (valid, reason). Missing validity fields fail closed, no retry."""
    if not isinstance(result, dict):
        raise ValueError("result")
    for key in ("clocksource_invalid", "pre_qemu_seconds", "wall_seconds", "host_load"):
        if key not in result:
            raise ValueError("missing validity evidence: " + key)
    if result["clocksource_invalid"] is not True and result["clocksource_invalid"] is not False:
        raise ValueError("clocksource_invalid must be boolean")
    pre = result["pre_qemu_seconds"]
    if (isinstance(pre, bool) or not isinstance(pre, (int, float))
            or not math.isfinite(pre) or pre < 0):
        raise ValueError("pre_qemu_seconds")
    wall = result["wall_seconds"]
    if (isinstance(wall, bool) or not isinstance(wall, (int, float))
            or not math.isfinite(wall) or wall < 0):
        raise ValueError("wall_seconds")
    host = result["host_load"]
    before = host.get("before_launch") if isinstance(host, dict) else None
    if not isinstance(before, dict) or "loadavg_1m" not in before:
        raise ValueError("host_load")
    load = before["loadavg_1m"]
    if isinstance(load, bool) or not isinstance(load, (int, float)) or not math.isfinite(load) or load < 0:
        raise ValueError("host_load")
    reasons = []
    if result["clocksource_invalid"]:
        reasons.append("clocksource_fallback")
    if pre > rules["pre_qemu_seconds_max"]:
        reasons.append("pre_qemu_delay")
    if wall_outlier(wall, prior_walls, rules["wall_factor"], rules["wall_min_samples"]):
        reasons.append("wall_time_outlier")
    if reasons:
        return False, "+".join(reasons)
    return True, None


# Guest shape and accelerator for revisions whose measurement parameters are approved.
# Revision 5 is the closed kbench smoke and stays unapproved here.
_APPROVED_SHAPE = {
    3: {"vcpus": 4, "mem_mib": 4096, "accel": "tcg"},
    4: {"vcpus": 8, "mem_mib": 8192, "accel": "kvm"},
    6: {"vcpus": 4, "mem_mib": 4096, "accel": "tcg"},
}
_TCG_QEMU = ["-accel", "tcg,thread=multi,tb-size=256", "-machine", "pc", "-cpu", "max"]


def _revision6(protocol, rules, validity, accelerator):
    """The TCG kbench screen: 25% ceiling, xswap probe and fast, build excluded."""
    if protocol.get("template_only"):
        raise ValueError("revision 6 protocol is executable")
    if rules["noise_ceiling"] != 0.25:
        raise ValueError("revision 6 noise ceiling is 25%")
    if rules["max_reruns"] != 2:
        raise ValueError("revision 6 allows two validity reruns")
    if ".p99_ns" not in rules["advisory_suffixes"]:
        raise ValueError("revision 6 keeps p99 advisory")
    if protocol.get("preallocate_swap") is not True:
        raise ValueError("revision 6 preallocates swap")
    if accelerator.get("qemu") != _TCG_QEMU:
        raise ValueError("revision 6 QEMU accelerator options")
    if validity.get("clocksource_fallback") != "invalid_and_rerun":
        raise ValueError("revision 6 clocksource gate")
    if not isinstance(validity.get("host_load"), str) or not validity["host_load"].strip():
        raise ValueError("revision 6 records host load")
    excluded = protocol.get("excluded")
    if not isinstance(excluded, dict) or not isinstance(excluded.get("build"), str) or not excluded["build"].strip():
        raise ValueError("revision 6 excludes the build workload")
    tiers = protocol.get("tiers", {})
    if "slow" in tiers or "probe" not in tiers:
        raise ValueError("revision 6 requires a probe tier and has no slow tier")
    if protocol.get("baseline_build") != "kb-xs-desc-v1":
        raise ValueError("revision 6 baseline build is kb-xs-desc-v1")
    if protocol.get("baseline_commit") != "5e84ca928deeacb4eee656806a003f27d1eca82f":
        raise ValueError("revision 6 baseline commit")
    if protocol.get("page_cluster", {}).get("value") != 3:
        raise ValueError("revision 6 page-cluster is the kernel default 3")
    if tiers.get("fast", {}).get("cases") != ["swapin-disk", "swapin-zram-64k"]:
        raise ValueError("revision 6 fast cases")
    if tiers.get("probe", {}).get("cases") != ["swapin-disk", "swapin-zram-64k", "metadata-brd"]:
        raise ValueError("revision 6 probe cases")
    cases = protocol.get("cases", {})
    if set(cases) != {"swapin-disk", "swapin-zram-64k", "metadata-brd"}:
        raise ValueError("revision 6 case set")
    for name, backend in (("swapin-disk", "disk"), ("swapin-zram-64k", "zram-64k")):
        spec = cases[name]
        if (spec.get("workload") != "swapin" or spec.get("mode") != "xswap" or
                spec.get("backend") != backend or spec.get("primary") != "swapin_seq.mean_ns"):
            raise ValueError("revision 6 swap-in cases are xswap")
        if spec.get("metrics", {}).get("swapin_rand.mean_ns") != "lower":
            raise ValueError("revision 6 keeps swapin_rand as a guard")
    firing = {"swapin_vmstat_delta.swap_ra", "swapin_vmstat_delta.swap_ra_hit",
              "swapin_vmstat_delta.pgmajfault"}
    if not firing <= set(cases["swapin-zram-64k"].get("probe_signals", [])):
        raise ValueError("revision 6 zram-64k probe keys the swap-in count signals")
    meta = cases["metadata-brd"]
    # Plain brd: the metadata gate requires the brd SwapTotal delta alone.
    # xswap create adds a swap device and that guest cannot pass swap_capacity.
    if (meta.get("workload") != "metadata" or meta.get("backend") != "brd" or
            meta.get("mode") != "plain" or meta.get("primary") is not None):
        raise ValueError("revision 6 brd metadata probe is plain mode")
    config_hash = protocol.get("input_config_sha256")
    if not isinstance(config_hash, str) or len(config_hash) != 64:
        raise ValueError("revision 6 kernel config hash")


def protocol_rules(protocol):
    """Measurement rules for approved revisions. Revision 6 is the TCG kbench screen."""
    if not isinstance(protocol, dict):
        raise ValueError("protocol")
    revision = protocol.get("protocol_revision", 1)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("protocol_revision")
    validity = protocol.get("validity") if isinstance(protocol.get("validity"), dict) else {}
    suffixes = protocol.get("advisory_metric_suffixes", [])
    if not isinstance(suffixes, list) or any(not isinstance(item, str) or not item for item in suffixes):
        raise ValueError("advisory_metric_suffixes")
    ceiling = protocol.get("noise_ceiling", 0.20)
    floor = protocol.get("noise_floor", 0.03)
    for name, value in (("noise_ceiling", ceiling), ("noise_floor", floor)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(name)
    rules = {
        "protocol_revision": revision,
        "envelope": protocol.get("noise_envelope", "max"),
        "noise_ceiling": float(ceiling),
        "noise_floor": float(floor),
        "advisory_suffixes": tuple(suffixes),
        "decision": protocol.get("comparison_decision", "legacy"),
        "enforce_validity": revision >= 3,
        "pre_qemu_seconds_max": float(validity.get("pre_qemu_seconds_max", 60)),
        "wall_factor": float(validity.get("wall_time_factor", 1.5)),
        "wall_min_samples": int(validity.get("wall_median_min_samples", 3)),
        "max_reruns": int(validity.get("reruns_per_arm", 2 if revision >= 3 else 0)),
    }
    if rules["envelope"] not in ("max", "p90") or rules["decision"] not in ("legacy", "median"):
        raise ValueError("unknown envelope or decision")
    if revision >= 3:
        if revision not in _APPROVED_SHAPE:
            raise ValueError("unapproved protocol revision")
        if rules["envelope"] != "p90" or rules["decision"] != "median":
            raise ValueError("approved revision uses a p90 envelope and a median comparison")
        if not 0.25 - 1e-12 <= rules["noise_ceiling"] <= 0.30 + 1e-12:
            raise ValueError("approved revision noise ceiling must be between 25% and 30%")
        if rules["max_reruns"] < 1 or rules["pre_qemu_seconds_max"] != 60 or rules["wall_factor"] != 1.5:
            raise ValueError("approved revision validity gates")
        guest = protocol.get("guest") if isinstance(protocol.get("guest"), dict) else {}
        accelerator = protocol.get("accelerator") if isinstance(protocol.get("accelerator"), dict) else {}
        shape = _APPROVED_SHAPE[revision]
        if (guest.get("vcpus") != shape["vcpus"] or guest.get("mem_mib") != shape["mem_mib"] or
                guest.get("swap_gib") != 16):
            raise ValueError(
                f"revision {revision} guest is {shape['vcpus']} vCPU, {shape['mem_mib']} MiB, 16 GiB swap")
        if accelerator.get("require") != shape["accel"]:
            raise ValueError(f"revision {revision} requires {shape['accel'].upper()}")
        excluded = protocol.get("excluded") if isinstance(protocol.get("excluded"), dict) else {}
        for spec in protocol.get("tiers", {}).values():
            if not isinstance(spec, dict):
                continue
            for case_name in spec.get("cases", []):
                workload = protocol.get("cases", {}).get(case_name, {}).get("workload")
                if workload in excluded:
                    raise ValueError("excluded workload is in a tier: " + str(workload))
        if revision == 4 and (protocol.get("preallocate_swap") is not True or
                              any(c.get("mode", "plain") != "plain" for c in protocol.get("cases", {}).values())):
            raise ValueError("revision 4 requires plain mode and preallocated swap")
        if revision == 6:
            _revision6(protocol, rules, validity, accelerator)
        for name, spec in protocol.get("tiers", {}).items():
            if spec.get("kind") == "probe":
                if name != "probe":
                    raise ValueError("probe run counts apply only to the probe tier")
                if (type(spec.get("calibration_runs")) is not int or type(spec.get("candidate_runs")) is not int or
                        spec.get("calibration_runs") != 3 or spec.get("candidate_runs") != 1):
                    raise ValueError("probe tier requires three calibration runs and one candidate run")
                continue
            if spec.get("calibration_pairs", 0) < 10 or spec.get("comparison_pairs", 0) < 4:
                raise ValueError(f"revision {revision} needs >=10 A/A pairs and >=4 comparison pairs")
    return rules
