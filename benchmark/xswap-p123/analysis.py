# SPDX-License-Identifier: GPL-2.0-only
"""Paired descriptive performance analysis; never promotes a kernel candidate.

A pair is {"a": {"case.metric": number}, "b": {"case.metric": number}}.
Directions maps every scored metric to "higher" or "lower". Both arms must
contain exactly those metrics. The caller owns provenance, tier sample counts,
AB/BA ordering, and correctness gates. Primary selects one metric per scored case; all metrics retain regression guards.
Omit noisy descriptive metadata from this input.
"""
import math
import random
import statistics

FLOOR = math.log(1.03)
MAX_NOISE = math.log(1.20)
RESAMPLES = 10000


def _logs(pairs, directions):
    if not isinstance(directions, dict) or not directions:
        raise ValueError("nonempty directions required")
    if any(not isinstance(k, str) or not k or v not in ("higher", "lower")
           for k, v in directions.items()):
        raise ValueError("invalid metric direction")
    if not isinstance(pairs, list) or len(pairs) < 2:
        raise ValueError("at least two independent pairs required")
    rows = []
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != {"a", "b"}:
            raise ValueError("invalid pair schema")
        for arm in ("a", "b"):
            if not isinstance(pair[arm], dict) or set(pair[arm]) != set(directions):
                raise ValueError("missing or unmatched metrics")
            for value in pair[arm].values():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("metric must be numeric")
                try:
                    valid = math.isfinite(value) and value > 0
                except OverflowError:
                    valid = False
                if not valid:
                    raise ValueError("metric must be finite and positive")
        rows.append({key: (math.log(pair["b"][key]) - math.log(pair["a"][key])) *
                     (1 if direction == "higher" else -1)
                     for key, direction in directions.items()})
    return rows


def _exp(value):
    try:
        result = math.exp(value)
    except OverflowError as error:
        raise ValueError("relative score overflow") from error
    if not math.isfinite(result) or result <= 0:
        raise ValueError("unrepresentable relative score")
    return result


def _primary(primary, directions):
    if primary is None:
        return sorted(directions)
    if (not isinstance(primary, (list, tuple)) or not primary or
            any(not isinstance(k, str) or k not in directions for k in primary) or
            len(set(primary)) != len(primary)):
        raise ValueError("primary must name distinct known metrics")
    return sorted(primary)


def calibrate(pairs, directions, primary=None):
    """Reject any scored A/A metric with >20% multiplicative pair noise."""
    rows = _logs(pairs, directions)
    primary = _primary(primary, directions)
    noise = {key: max(FLOOR, max(abs(row[key]) for row in rows))
             for key in directions}
    rejected = [key for key, value in noise.items() if value > MAX_NOISE + 1e-12]
    return {"schema_version": 1, "status": "CALIBRATION_NOISY" if rejected else "CALIBRATED",
            "passed": not rejected, "directions": dict(directions), "primary": primary, "pair_count": len(rows),
            "noise_log": noise, "noise_relative": {k: _exp(v) - 1 for k, v in noise.items()},
            "rejected_metrics": rejected, "performance_accepted": False,
            "auto_promote": False}


def _interval(values):
    ordered = sorted(values)
    # Empirical percentile interval with conservative outward rounding.
    return [_exp(ordered[math.floor(.025 * (len(ordered) - 1))]),
            _exp(ordered[math.ceil(.975 * (len(ordered) - 1))])]


def compare(pairs, directions, calibration, tier, reference=False, primary=None):
    """Return fast admission or slow review evidence, never acceptance.

    Slow intervals resample entire paired metric vectors together, preserving
    within-pair correlation. These are descriptive bootstrap intervals, not a
    multiple-comparison correction or a correctness claim.
    """
    if tier not in ("fast", "slow") or not isinstance(reference, bool):
        raise ValueError("invalid tier/reference")
    rows = _logs(pairs, directions)
    primary = _primary(primary, directions)
    if tier == "slow" and len(rows) < 10:
        raise ValueError("slow comparison requires at least ten independent pairs")
    if reference and tier != "fast":
        raise ValueError("reference measurements are fast-tier only")
    if (not isinstance(calibration, dict) or calibration.get("passed") is not True or
            calibration.get("status") != "CALIBRATED" or
            calibration.get("directions") != directions or
            calibration.get("primary") != primary):
        raise ValueError("missing, failed, or mismatched calibration")
    noise = calibration.get("noise_log")
    if not isinstance(noise, dict) or set(noise) != set(directions):
        raise ValueError("mismatched noise metrics")
    for value in noise.values():
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or value < FLOOR or value > MAX_NOISE + 1e-12):
            raise ValueError("invalid calibration envelope")
    metrics = {}
    for key in directions:
        values = [row[key] for row in rows]
        metrics[key] = {"pair_ratios": [_exp(v) for v in values],
                        "geomean_ratio": _exp(statistics.mean(values)),
                        "median_ratio": _exp(statistics.median(values)),
                        "noise_relative": _exp(noise[key]) - 1,
                        "guard_pass": statistics.median(values) >= -noise[key] - 1e-12}
    overall = [statistics.mean(row[key] for key in primary) for row in rows]
    result = {"tier": tier, "pair_count": len(rows), "metrics": metrics,
              "overall_geomean_ratio": _exp(statistics.mean(overall)),
              "combined_score": _exp(statistics.mean(overall)), "primary": primary,
              "reference": reference, "performance_accepted": False,
              "auto_promote": False, "eligible_for_slow": False,
              "needs_review": False}
    if tier == "fast":
        admitted = all(m["guard_pass"] for m in metrics.values())
        result.update(status="FAST_PASS" if admitted else "REGRESSION",
                      eligible_for_slow=admitted and not reference)
    else:
        rng = random.Random(42)
        samples = {key: [] for key in directions}
        combined = []
        for _ in range(RESAMPLES):
            indices = [rng.randrange(len(rows)) for _ in rows]
            combined.append(statistics.mean(overall[i] for i in indices))
            for key in directions:
                samples[key].append(statistics.mean(rows[i][key] for i in indices))
        for key in directions:
            interval = _interval(samples[key])
            metrics[key].update(ci95=interval,
                                guard_pass=interval[0] >= _exp(-noise[key]) - 1e-12)
        interval = _interval(combined)
        envelope = max(noise[key] for key in primary)
        needs_review = (interval[0] > _exp(envelope) and
                        all(m["guard_pass"] for m in metrics.values()))
        result.update(status="NEEDS_REVIEW" if needs_review else "INCONCLUSIVE",
                      overall_ci95=interval, overall_noise_relative=_exp(envelope) - 1,
                      bootstrap_resamples=RESAMPLES, bootstrap_seed=42,
                      needs_review=needs_review and not reference)
    if reference:
        result["underlying_status"] = result["status"]
        result["status"] = "REFERENCE_COMPLETE"
    return result
