"""Decision-quality contract. Percentiles always use the issuance-time distribution."""
import bisect
import math
import random
from collections import defaultdict
from datetime import timedelta
from itertools import combinations
from .hourly_forecast import samples, dt

CONTRACT = {'version': 'relative-choice-v2', 'boundaries': [20, 40, 65, 85],
            'peak_basis': 'issuance_time_within_target_percentile', 'very_busy_above': 85,
            'relaxed_max': 40, 'busy_above': 65, 'false_relaxed_max': .05, 'peak_miss_max': .10,
            'min_relaxed': 50, 'min_peaks': 20, 'min_pairs': 100, 'min_days': 14,
            'bootstrap_draws': 2000, 'bootstrap_seed': 20260913}
LABELS = ('평소보다 매우 한산', '평소보다 한산', '평소 수준', '평소보다 붐빔', '평소보다 매우 붐빔')


def relative_label(score):
    return LABELS[bisect.bisect_left(CONTRACT['boundaries'], score)] if score is not None else None


def distribution(data, issued_at):
    at = dt(issued_at)
    midnight = at.replace(hour=0)
    return sorted(r['value'] for t, r in samples(data, at).items()
                  if midnight-timedelta(days=84) <= t < midnight)


def percentile(values, value):
    if value is None or not values:
        return None
    return 50*(bisect.bisect_left(values, value)+bisect.bisect_right(values, value))/len(values)


def annotate(row, values):
    row['decision_scores'] = {k: percentile(values, row.get(k)) for k in ('population', 'arithmetic', 'actual')}
    row['decision_contract_version'] = CONTRACT['version']
    return row


def rate(errors, count):
    if not count:
        return {'errors': 0, 'count': 0, 'rate': None, 'interval95': None}
    p, z = errors/count, 1.959963984540054
    center = (p+z*z/(2*count))/(1+z*z/count)
    half = z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/(1+z*z/count)
    return {'errors': errors, 'count': count, 'rate': p, 'interval95': [max(0, center-half), min(1, center+half)]}


def difference_interval(days):
    """Cluster matched dates, retaining the separate prediction-dependent denominators."""
    if len(days) < 2:
        return None
    values = list(days.values())
    rng, draws = random.Random(CONTRACT['bootstrap_seed']), []
    for _ in range(CONTRACT['bootstrap_draws']):
        totals = [0]*4
        for v in rng.choices(values, k=len(values)):
            for i in range(4):
                totals[i] += v[i]
        if totals[1] and totals[3]:
            draws.append(totals[0]/totals[1]-totals[2]/totals[3])
    if len(draws) < .95*CONTRACT['bootstrap_draws']:
        return None
    draws.sort()
    return [draws[int(.025*(len(draws)-1))], draws[int(.975*(len(draws)-1))]]


def assess_decisions(rows, peaks=None, areas=None, min_days=None):
    # peaks remains accepted for existing callers; fixed population thresholds are not used.
    min_days = CONTRACT['min_days'] if min_days is None else min_days
    areas = list(areas) if areas is not None else sorted({r['area_id'] for r in rows}, key=str)
    cells, failures, missing = {}, [], []
    comparable = [r for r in rows if r.get('decision_contract_version') == CONTRACT['version']
                  and all(r.get('decision_scores', {}).get(k) is not None for k in ('population', 'arithmetic', 'actual'))]
    for area in areas:
        for horizon in (1, 2, 3):
            cell = [r for r in comparable if r['area_id'] == area and r['hours_ahead'] == horizon]
            key = f'{area}:{horizon}'
            dates = {dt(r['valid_at']).date() for r in cell}
            stats = {'days': len(dates)}
            for name in ('false_relaxed', 'peak_miss'):
                days = defaultdict(lambda: [0, 0, 0, 0])
                totals = [0]*4
                for r in cell:
                    scores = r['decision_scores']
                    for offset, field in ((0, 'population'), (2, 'arithmetic')):
                        if name == 'false_relaxed':
                            denominator = scores[field] <= CONTRACT['relaxed_max']
                            error = denominator and scores['actual'] > CONTRACT['busy_above']
                        else:
                            denominator = scores['actual'] > CONTRACT['very_busy_above']
                            error = denominator and scores[field] <= CONTRACT['very_busy_above']
                        day = dt(r['valid_at']).date().isoformat()
                        for idx, v in ((offset, error), (offset+1, denominator)):
                            totals[idx] += int(v)
                            days[day][idx] += int(v)
                model, base = rate(*totals[:2]), rate(*totals[2:])
                interval = difference_interval(days)
                stats[name] = {'model': model, 'arithmetic': base, 'difference_interval95': interval}
                minimum = CONTRACT['min_relaxed' if name == 'false_relaxed' else 'min_peaks']
                if len(dates) < min_days or model['count'] < minimum or base['count'] < minimum:
                    missing.append(f'{key}:{name}:insufficient_denominator_or_days')
                elif model['rate'] > CONTRACT[name+'_max'] or model['rate'] > base['rate']:
                    failures.append(f'{key}:{name}:error_limit_or_regression')
                elif interval is None or interval[1] > 0:
                    missing.append(f'{key}:{name}:uncertain_regression')
            cells[key] = stats
    guidance = {'status': 'FAIL' if failures else 'NEEDS_MORE_DATA' if missing or not areas else 'PASS',
                'reasons': failures+missing, 'cells': cells}
    ranking = assess_ranking(comparable, min_days)
    return {'contract': CONTRACT, 'guidance': guidance, 'ranking': ranking}


def assess_ranking(rows, min_days):
    groups = defaultdict(dict)
    for r in rows:
        # A provider's same observed area is one target, even if several places map to it.
        identity = r.get('external_id') or str(r['area_id'])
        group = (r.get('provider'), r.get('metric'), r.get('scope'), r['issued_at'], r['valid_at'])
        if not all(group[:3]):
            continue
        if identity in groups[group] and groups[group][identity]['decision_scores'] != r['decision_scores']:
            raise ValueError('Conflicting duplicate target decision scores')
        groups[group][identity] = r
    results = defaultdict(lambda: {'days': defaultdict(lambda: [0, 0, 0, 0]), 'targets': set(),
                                  'actual_ties': 0, 'both_ties': 0, 'prediction_ties': 0})
    for group, targets in groups.items():
        for (aid, a), (bid, b) in combinations(sorted(targets.items()), 2):
            out = results['|'.join(group[:3])]
            out['targets'].update((aid, bid))
            x, y = a['decision_scores'], b['decision_scores']
            actual = x['actual']-y['actual']
            predicted, baseline = x['population']-y['population'], x['arithmetic']-y['arithmetic']
            if actual == 0:
                out['actual_ties'] += 1
                out['both_ties'] += int(predicted == 0)
                continue
            if predicted == 0 or baseline == 0:
                out['prediction_ties'] += 1
                continue
            counts = out['days'][dt(a['valid_at']).date().isoformat()]
            counts[0] += int(predicted*actual < 0)
            counts[1] += 1
            counts[2] += int(baseline*actual < 0)
            counts[3] += 1
    reports = {}
    for group, out in results.items():
        days = out.pop('days')
        totals = [sum(v[i] for v in days.values()) for i in range(4)]
        model, base = rate(*totals[:2]), rate(*totals[2:])
        interval = difference_interval(days)
        status = 'NEEDS_MORE_DATA'
        if len(out['targets']) >= 2 and model['count'] >= CONTRACT['min_pairs'] and len(days) >= min_days:
            if model['rate'] > base['rate']:
                status = 'FAIL'
            elif interval is not None and interval[1] <= 0:
                status = 'PASS'
        reports[group] = {**out, 'targets': sorted(out['targets']), 'days': len(days), 'model': model,
                          'arithmetic': base, 'difference_interval95': interval, 'status': status}
    status = ('FAIL' if any(r['status'] == 'FAIL' for r in reports.values()) else
              'PASS' if reports and all(r['status'] == 'PASS' for r in reports.values()) else 'NEEDS_MORE_DATA')
    return {'status': status, 'groups': reports}
