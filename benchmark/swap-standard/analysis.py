# SPDX-License-Identifier: GPL-2.0-only
"""Paired descriptive performance analysis; never promotes a kernel candidate.

A pair is {"a": {"case.metric": number}, "b": {"case.metric": number}}.
Directions maps every scored metric to "higher" or "lower". Both arms must
contain exactly those metrics. The caller owns provenance, tier sample counts,
AB/BA ordering, and correctness gates. Primary selects one metric per scored
case. Advisory metrics are reported and do not reject a revision 3 screen.
Omit noisy descriptive metadata from this input.
"""
import math
import random
import statistics

FLOOR = math.log(1.03)
MAX_NOISE = math.log(1.20)
RESAMPLES = 10000


def _need_pairs(count, minimum):
    need = max(2, minimum)
    if not isinstance(count, int) or count < need:
        raise ValueError("at least %d independent pairs required" % need)
    return need


def _ratio_log(relative):
    if isinstance(relative, bool) or not isinstance(relative, (int, float)):
        raise ValueError("relative threshold")
    if not math.isfinite(relative) or relative <= 0:
        raise ValueError("relative threshold")
    return math.log(1 + relative)


def _nearest_rank(values, fraction):
    """Ceiling nearest-rank percentile. p90 of 10 values is the 9th, index 8."""
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _advisory(key, suffixes):
    return any(key.endswith(suffix) for suffix in suffixes)


def _logs(pairs, directions, min_pairs=2):
    if not isinstance(directions, dict) or not directions:
        raise ValueError("nonempty directions required")
    if any(not isinstance(k, str) or not k or v not in ("higher", "lower")
           for k, v in directions.items()):
        raise ValueError("invalid metric direction")
    if not isinstance(pairs, list):
        raise ValueError("pairs must be a list")
    _need_pairs(len(pairs), min_pairs)
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


def calibrate(pairs, directions, primary=None, *, envelope="max", min_pairs=2,
              noise_ceiling=0.20, noise_floor=0.03, advisory_suffixes=()):
    """A/A envelope. The default is the revision 1/2 maximum, with a 20% ceiling.

    envelope="p90" uses the nearest-rank 90th percentile of absolute pair
    ratios and requires at least 10 pairs. Advisory metrics are reported and
    do not reject the calibration.
    """
    if envelope not in ("max", "p90"):
        raise ValueError("invalid noise envelope")
    if envelope == "p90" and min_pairs < 10:
        raise ValueError("p90 envelope requires at least 10 pairs")
    if not isinstance(advisory_suffixes, (list, tuple)) or any(
            not isinstance(item, str) or not item for item in advisory_suffixes):
        raise ValueError("advisory suffixes")
    floor = _ratio_log(noise_floor)
    ceiling = _ratio_log(noise_ceiling)
    if floor >= ceiling:
        raise ValueError("noise floor must be below the ceiling")
    rows = _logs(pairs, directions, min_pairs)
    primary = _primary(primary, directions)
    if any(_advisory(key, advisory_suffixes) for key in primary):
        raise ValueError("primary metric cannot be advisory")
    absolute = {key: [abs(row[key]) for row in rows] for key in directions}
    if envelope == "max":
        noise = {key: max(floor, max(values)) for key, values in absolute.items()}
    else:
        noise = {key: max(floor, _nearest_rank(values, 0.90)) for key, values in absolute.items()}
    advisory = [key for key in directions if _advisory(key, advisory_suffixes)]
    rejected = [key for key, value in noise.items()
                if value > ceiling + 1e-12 and key not in advisory]
    return {"schema_version": 1, "status": "CALIBRATION_NOISY" if rejected else "CALIBRATED",
            "passed": not rejected, "directions": dict(directions), "primary": primary, "pair_count": len(rows),
            "envelope": envelope, "noise_ceiling": noise_ceiling, "noise_floor": noise_floor,
            "noise_log": noise, "noise_relative": {k: _exp(v) - 1 for k, v in noise.items()},
            "advisory_metrics": advisory, "rejected_metrics": rejected,
            "performance_accepted": False, "auto_promote": False}


def _interval(values):
    ordered = sorted(values)
    # Empirical percentile interval with conservative outward rounding.
    return [_exp(ordered[math.floor(.025 * (len(ordered) - 1))]),
            _exp(ordered[math.ceil(.975 * (len(ordered) - 1))])]


def compare(pairs, directions, calibration, tier, reference=False, primary=None, *,
            decision="legacy", min_pairs=None):
    """Return fast admission or slow review evidence, never acceptance.

    decision="legacy" keeps the revision 1/2 rule: fast guards use the median
    and slow guards use paired-vector bootstrap intervals. decision="median"
    judges every tier on the median of pair deltas and requires at least four
    pairs. Slow legacy intervals resample entire paired metric vectors
    together. These are descriptive intervals, not a multiple-comparison
    correction or a correctness claim.
    """
    if tier not in ("fast", "slow") or not isinstance(reference, bool):
        raise ValueError("invalid tier/reference")
    if decision not in ("legacy", "median"):
        raise ValueError("invalid decision")
    if decision == "median":
        if min_pairs is None:
            min_pairs = 4
        if min_pairs < 4:
            raise ValueError("median comparison requires at least 4 independent pairs")
    elif min_pairs is None:
        min_pairs = 10 if tier == "slow" else 2
    rows = _logs(pairs, directions, min_pairs)
    primary = _primary(primary, directions)
    if decision == "legacy" and tier == "slow" and len(rows) < 10:
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
    advisory = set(calibration.get("advisory_metrics", []))
    if any(key not in directions for key in advisory):
        raise ValueError("advisory metric is not scored")
    floor = _ratio_log(calibration["noise_floor"]) if "noise_floor" in calibration else FLOOR
    ceiling = _ratio_log(calibration["noise_ceiling"]) if "noise_ceiling" in calibration else MAX_NOISE
    for key, value in noise.items():
        limit = ceiling if key not in advisory else math.inf
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or value < floor - 1e-12 or value > limit + 1e-12):
            raise ValueError("invalid calibration envelope")
    metrics = {}
    for key in directions:
        values = [row[key] for row in rows]
        metrics[key] = {"pair_ratios": [_exp(v) for v in values],
                        "geomean_ratio": _exp(statistics.mean(values)),
                        "median_ratio": _exp(statistics.median(values)),
                        "noise_relative": _exp(noise[key]) - 1,
                        "guard_pass": statistics.median(values) >= -noise[key] - 1e-12}
        if key in advisory:
            metrics[key]["advisory"] = True
    overall = [statistics.mean(row[key] for key in primary) for row in rows]

    def scored_pass():
        return all(metrics[key]["guard_pass"] for key in directions if key not in advisory)

    result = {"tier": tier, "pair_count": len(rows), "metrics": metrics,
              "overall_geomean_ratio": _exp(statistics.mean(overall)),
              "combined_score": _exp(statistics.mean(overall)), "primary": primary,
              "reference": reference, "performance_accepted": False,
              "auto_promote": False, "eligible_for_slow": False,
              "needs_review": False}
    if decision == "median" or tier == "fast":
        admitted = scored_pass()
        if decision == "median":
            result["decision"] = "median"
            result["combined_score"] = _exp(statistics.median(overall))
            result["overall_median_ratio"] = result["combined_score"]
        # A median screen does not open the slow tier. KVM confirmation stays an owner decision.
        eligible = admitted and not reference and decision == "legacy"
        result.update(status="FAST_PASS" if admitted else "REGRESSION",
                      eligible_for_slow=eligible)
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
        needs_review = interval[0] > _exp(envelope) and scored_pass()
        result.update(status="NEEDS_REVIEW" if needs_review else "INCONCLUSIVE",
                      overall_ci95=interval, overall_noise_relative=_exp(envelope) - 1,
                      bootstrap_resamples=RESAMPLES, bootstrap_seed=42,
                      needs_review=needs_review and not reference)
    if reference:
        result["underlying_status"] = result["status"]
        result["status"] = "REFERENCE_COMPLETE"
    return result
