"""Population metrics and conservative promotion gates, shared by replay and shadow."""
import math
import random
from collections import defaultdict
from statistics import mean
from .mean_forecast import dt


def metrics(rows, field, scales, peaks, relative_peak_threshold=None):
    groups = defaultdict(list)
    for row in rows:
        pred = row.get(field)
        if pred is not None and row.get('actual') is not None:
            groups[(row['area_id'], row['hours_ahead'])].append(row)
    cells = {}
    for (area, horizon), values in groups.items():
        errors = [r[field] - r['actual'] for r in values]
        high = [r for r in values if (r.get('decision_scores', {}).get('actual') is not None
                and r['decision_scores']['actual'] > relative_peak_threshold)] if relative_peak_threshold is not None else [r for r in values if r['actual'] >= peaks.get(str(area), math.inf)]
        misses = ([r['decision_scores'][field] <= relative_peak_threshold for r in high
                   if r.get('decision_scores', {}).get(field) is not None] if relative_peak_threshold is not None
                  else [r[field] < peaks[str(area)] for r in high])
        cells[f'{area}:{horizon}'] = {
            'count': len(values), 'mae': mean(abs(e) for e in errors),
            'nmae': mean(abs(e) for e in errors) / scales[str(area)],
            'rmse': math.sqrt(mean(e * e for e in errors)), 'bias': mean(errors),
            'peak_mae': mean(abs(r[field]-r['actual']) for r in high) if high else None,
            'peak_miss_rate': mean(misses) if misses else None}
    errors = [r[field]-r['actual'] for values in groups.values() for r in values]
    return {'cells': cells, 'nmae': mean(c['nmae'] for c in cells.values()) if cells else None,
            'mae': mean(abs(e) for e in errors) if errors else None,
            'rmse': math.sqrt(mean(e*e for e in errors)) if errors else None,
            'bias': mean(errors) if errors else None}


def improvement_interval(rows, reference, scales, date_field='issued_at'):
    # Each date is a complete cluster shared across all areas and horizons.
    days = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if all(r.get(k) is not None for k in ('population', reference, 'actual')):
            delta = (abs(r['population']-r['actual'])-abs(r[reference]-r['actual'])) / scales[str(r['area_id'])]
            days[dt(r.get(date_field, r['issued_at'])).date().isoformat()][(r['area_id'], r['hours_ahead'])].append(delta)
    if len(days) < 2:
        return None
    summaries = [{k: (sum(v), len(v)) for k, v in cells.items()} for cells in days.values()]
    rng, draws = random.Random(20260913), []
    for _ in range(2000):
        sums, counts = defaultdict(float), defaultdict(int)
        for day in rng.choices(summaries, k=len(summaries)):
            for key, (total, count) in day.items():
                sums[key] += total
                counts[key] += count
        draws.append(mean(sums[k]/counts[k] for k in sums))
    draws.sort()
    return [draws[49], draws[1949]]


def assess(rows, areas, scales, peaks, reference='arithmetic', event_verified=False, required_areas=3,
           date_field='issued_at', strict_coverage=False, relative_peak_threshold=None):
    fields = ('population', 'weekly', 'persistence', 'arithmetic', 'recent', 'conditional', 'reference')
    report = {'status': 'NEEDS_MORE_DATA', 'reasons': [], 'metrics': {}, 'scope': 'provider_area_population',
              'event_verified': event_verified, 'reference': reference}
    report['provided_rate'] = mean(r.get('population') is not None for r in rows) if rows else 0
    report['label_rate'] = mean(r.get('actual') is not None for r in rows) if rows else 0
    # Gate models on the same rows; publish missingness separately.
    pair_fields = ('population', 'arithmetic', reference, 'actual') + (('weekly', 'persistence') if strict_coverage else ())
    paired = [r for r in rows if all(r.get(k) is not None for k in pair_fields)]
    report['paired_count'] = len(paired)
    report['peak_basis'] = ('issuance_time_within_target_percentile' if relative_peak_threshold is not None else 'fixed_training_population')
    report['relative_peak_threshold'] = relative_peak_threshold
    report['paired_rate'] = len(paired)/len(rows) if rows else 0
    report['coverage_cells'] = {}
    report['bootstrap'] = {'date_field': date_field, 'timezone': 'Asia/Seoul', 'draws': 2000, 'seed': 20260913}
    for field in fields:
        report['metrics'][field] = metrics(paired, field, scales, peaks, relative_peak_threshold)
    sufficient = bool(areas) and (required_areas is None or len(areas) == required_areas) and report['provided_rate'] >= .9 and report['label_rate'] >= .9
    for area in areas:
        for h in (1, 2, 3):
            cell = [r for r in paired if r['area_id'] == area and r['hours_ahead'] == h]
            dates = {dt(r.get(date_field, r['issued_at'])).date() for r in cell}
            scheduled = [r for r in rows if r['area_id'] == area and r['hours_ahead'] == h]
            coverage = {'scheduled': len(scheduled), 'paired': len(cell), 'days': len(dates),
                        'provided_rate': mean(r.get('population') is not None for r in scheduled) if scheduled else 0,
                        'label_rate': mean(r.get('actual') is not None for r in scheduled) if scheduled else 0,
                        'paired_rate': len(cell)/len(scheduled) if scheduled else 0}
            report['coverage_cells'][f'{area}:{h}'] = coverage
            if strict_coverage:
                sufficient &= all(coverage[k] >= .9 for k in ('provided_rate', 'label_rate', 'paired_rate'))
            sufficient &= len(cell) >= 100 and len(dates) >= 14 and any(d.weekday() < 5 for d in dates) and any(d.weekday() >= 5 for d in dates)
    if not sufficient:
        report['reasons'].append('insufficient_paired_days_or_coverage')
        return report
    model, base, ref = (report['metrics'][k] for k in ('population', 'arithmetic', reference))
    failures = []
    if not model['nmae'] < base['nmae'] or model['nmae'] > .95 * base['nmae']:
        failures.append('mean_improvement_below_5_percent')
    if model['nmae'] >= ref['nmae']:
        failures.append('reference_not_improved')
    peak_missing = False
    for key, cell in model['cells'].items():
        if cell['mae'] > 1.05 * base['cells'][key]['mae']:
            failures.append('cell_regression:' + key)
        if cell['peak_mae'] is None:
            peak_missing = True
        elif cell['peak_mae'] > 1.05 * base['cells'][key]['peak_mae']:
            failures.append('peak_regression:' + key)
    intervals = {key: improvement_interval(paired, key, scales, date_field) for key in sorted(set(('arithmetic', reference)))}
    report['improvement_intervals'] = intervals
    if failures:
        report.update(status='FAIL', reasons=failures)
    elif peak_missing or any(v is None or v[1] >= 0 for v in intervals.values()):
        report['reasons'].append('uncertain_improvement_or_missing_peaks')
    elif not event_verified and any(r.get('parameters', {}).get('events') for r in rows):
        report['reasons'].append('event_editions_not_verified')
    else:
        report['status'] = 'PASS'
    # Descriptive slices do not replace the overall, paired promotion test.
    report['slices'] = {}
    for flag in ('weekday', 'weekend', 'holiday', 'rain', 'rain_forecast', 'rain_observed', 'event'):
        report['slices'][flag] = metrics([r for r in paired if flag in r.get('tags', [])], 'population', scales, peaks, relative_peak_threshold)
    return report
