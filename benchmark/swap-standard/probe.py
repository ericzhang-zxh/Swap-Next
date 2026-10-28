# SPDX-License-Identifier: GPL-2.0-only
"""Categorical mechanism and metadata probes. No processes or files are changed."""
import math
import re
import statistics

METADATA = "metadata_delta_bytes_per_capacity_slot"
VMSTAT = {"pswpin", "pswpout", "zswpin", "zswpout", "swap_ra", "swap_ra_hit", "pgmajfault", "swpin_zero", "zswpwb"}
MECHANISM = re.compile(r"([a-z][a-z0-9-]{0,47}):(metadata_delta_bytes_per_capacity_slot|swapin_vmstat_delta\.[a-z][a-z0-9_]*|xswap\.[a-z][a-z0-9_]*):(up|down)")
DEFAULT_CONSTANTS = {"relative_padding": 0.01, "integer_padding_floor": 1, "metadata_spread_fraction": 0.01}


def numeric(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("missing or non-finite probe signal: " + what)
    return value


def parse_mechanism(text):
    match = MECHANISM.fullmatch(text) if isinstance(text, str) else None
    if not match:
        raise ValueError("mechanism must be CASE:KEY:up|down")
    return match.groups()


def signals(protocol, case):
    spec = protocol["cases"][case]
    keys = spec.get("probe_signals")
    if not isinstance(keys, list) or not keys or len(set(keys)) != len(keys):
        raise ValueError(case + ": probe_signals must be a non-empty unique list")
    for key in keys:
        if not isinstance(key, str):
            raise ValueError(case + ": invalid probe signal")
        if key == METADATA:
            if spec.get("workload") != "metadata" or spec.get("backend") != "brd":
                raise ValueError(case + ": metadata signal needs the brd metadata workload")
        elif key.startswith("swapin_vmstat_delta."):
            if spec.get("workload") != "swapin" or key.split(".", 1)[1] not in VMSTAT:
                raise ValueError(case + ": unknown swap-in vmstat signal " + key)
        elif key.startswith("xswap."):
            if spec.get("workload") != "swapin" or spec.get("mode", "plain") != "xswap" or not re.fullmatch(r"xswap\.[a-z][a-z0-9_]*", key):
                raise ValueError(case + ": xswap signal needs an xswap swap-in case")
        else:
            raise ValueError(case + ": unknown probe signal " + key)
    return keys


def validate_mechanism(protocol, text):
    case, key, direction = parse_mechanism(text)
    if case not in protocol.get("tiers", {}).get("probe", {}).get("cases", []):
        raise ValueError("mechanism case is absent from the probe tier")
    if key not in signals(protocol, case):
        raise ValueError("mechanism key is absent from the case probe_signals")
    return case, key, direction


def constants(protocol):
    frozen = protocol.get("probe_band")
    if (not isinstance(frozen, dict) or frozen != DEFAULT_CONSTANTS or
            any(isinstance(v, bool) for v in frozen.values())):
        raise ValueError("probe_band must freeze the approved 1% padding, integer floor 1 and metadata spread 1%")
    return frozen


def signal(metrics, key):
    if key == METADATA:
        value = numeric(metrics[key], key)
        if value < 0:
            raise ValueError("negative metadata bytes per slot")
        return float(value)
    prefix, counter = key.split(".", 1)
    if prefix == "xswap":
        snapshots = metrics["swapin_xswap_snapshots"]
        value = numeric(snapshots["swapin_end"][counter], key) - numeric(snapshots["swapin_start"][counter], key)
    else:
        value = numeric(metrics[prefix][counter], key)
    if not isinstance(value, int) or (prefix != "xswap" and value < 0):
        raise ValueError("probe counter has an invalid integer value: " + key)
    return value


def band(values, *, integer, settings):
    if not values:
        raise ValueError("missing probe calibration samples")
    values = [numeric(v, "calibration") for v in values]
    median = statistics.median(values)
    pad = settings["relative_padding"] * abs(median)
    if integer:
        pad = max(pad, settings["integer_padding_floor"])
    return {"low": min(values) - pad, "high": max(values) + pad, "median": median,
            "minimum": min(values), "maximum": max(values), "padding": pad, "n": len(values)}


def calibrate(protocol, samples):
    settings = constants(protocol)
    tier = protocol["tiers"]["probe"]
    bands, reasons = {}, []
    for case in tier["cases"]:
        rows = samples.get(case, [])
        if len(rows) != tier["calibration_runs"]:
            raise ValueError(case + ": incomplete probe calibration")
        bands[case] = {}
        for key in signals(protocol, case):
            values = [signal(metrics, key) for metrics in rows]
            b = band(values, integer=key != METADATA, settings=settings)
            bands[case][key] = b
            if key == METADATA and b["maximum"] - b["minimum"] > settings["metadata_spread_fraction"] * abs(b["median"]):
                reasons.append(case + ": METADATA_CALIBRATION_NOISY")
    return {"status": "CALIBRATION_NOISY" if reasons else "CALIBRATED", "passed": not reasons,
            "bands": bands, "reasons": reasons, "performance_accepted": False, "auto_promote": False}


def compare(protocol, calibration, samples, mechanism):
    case, key, direction = validate_mechanism(protocol, mechanism)
    if calibration.get("passed") is not True:
        raise ValueError("probe calibration has not passed")
    settings = constants(protocol)
    reasons, observed = [], {}
    tier = protocol["tiers"]["probe"]
    for name in tier["cases"]:
        rows = samples.get(name, [])
        if len(rows) != tier["candidate_runs"]:
            raise ValueError(name + ": incomplete probe candidate samples")
        observed[name] = {}
        for counter in signals(protocol, name):
            values = [signal(metrics, counter) for metrics in rows]
            observed[name][counter] = values
            b = calibration["bands"][name][counter]
            for boundary in ("low", "high"):
                numeric(b[boundary], name + ":" + counter + ":" + boundary)
            if b["low"] > b["high"]:
                raise ValueError("invalid probe band")
            if counter == METADATA and any(v > b["high"] for v in values):
                reasons.append(name + ": METADATA_REGRESSION")
    b, values = calibration["bands"][case][key], observed[case][key]
    for value in values:
        if b["low"] <= value <= b["high"]:
            reasons.append("MECHANISM_NOT_ENGAGED")
        elif (direction == "up" and value < b["low"]) or (direction == "down" and value > b["high"]):
            reasons.append("MECHANISM_REVERSED")
    reasons = list(dict.fromkeys(reasons))
    return {"status": "PROBE_REJECT" if reasons else "PROBE_PASS", "passed": not reasons,
            "reasons": reasons, "probe_signals": observed, "mechanism": mechanism,
            "performance_accepted": False, "auto_promote": False}
