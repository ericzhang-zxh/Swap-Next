# SPDX-License-Identifier: GPL-2.0-only
"""Descriptive regime counts; intervals never trigger acceptance."""
import math


def wilson(high, total):
    if total == 0:
        return None
    z = 1.959963984540054
    rate = high / total
    denominator = 1 + z*z/total
    center = (rate + z*z/(2*total)) / denominator
    radius = z * math.sqrt(rate*(1-rate)/total + z*z/(4*total*total)) / denominator
    return [max(0.0, center-radius), min(1.0, center+radius)]


def summarize_regimes(runs, threshold):
    groups = {}
    for run in runs:
        key = run['backend'] + '/' + run['side']
        group = groups.setdefault(key, dict(attempted=0, valid=0, high=0, low=0, invalid=0, runs=[]))
        group['attempted'] += 1
        value = run.get('metrics', {}).get('mapped_clusters_after_settle')
        valid = (run.get('pilot_pass') is True and run.get('evidence_verified') is True
                 and isinstance(value, (int, float))
                 and not isinstance(value, bool) and math.isfinite(value) and value > 0)
        regime = ('high' if value > threshold else 'low') if valid else 'invalid'
        group[regime] += 1
        group['valid'] += int(valid)
        group['runs'].append(dict(pair=run['pair'], boot_id=run.get('boot_id'),
                                  mapped_clusters_after_settle=value, regime=regime))
    for group in groups.values():
        group['high_rate'] = group['high']/group['valid'] if group['valid'] else None
        group['high_rate_wilson_95'] = wilson(group['high'], group['valid'])
    return dict(threshold_clusters=threshold, high_rule='strictly greater than threshold',
                interval='descriptive Wilson 95%; valid boots only; failures retained separately',
                groups=groups, performance_accepted=False, auto_promote=False)
