"""Read-only stage 2 assessment. Paired day-cluster bootstrap, never changes forecasts."""
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

KST = ZoneInfo('Asia/Seoul')


def paired_mae(rows):
    areas = defaultdict(list)
    for row in rows:
        areas[row['crowd_area_id']].append(row)
    return {name: float(np.mean([np.mean([abs(r[column]-r['actual_score']) for r in group])
                                for group in areas.values()]))
            for name, column in [('model', 'predicted_score'), ('baseline', 'baseline_score'), ('persistence', 'persistence_score')]}


def assess(rows, now, iterations=2000):
    groups = defaultdict(list)
    excluded = defaultdict(int)
    for row in rows:
        issued = datetime.fromisoformat(row['issued_at'])
        valid = datetime.fromisoformat(row['valid_at'])
        if row['scope'] != 'area_core':
            excluded['legacy_or_non_area_scope'] += 1
            continue
        if not now-timedelta(days=84) <= issued <= now or valid > now:
            excluded['outside_evaluation_window'] += 1
            continue
        snapshot = row['input_snapshot']
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        key = (row['model_version'], snapshot.get('baseline_policy', '84d-median-v1'), row['hours_ahead'])
        groups[key].append(row)
    result = []
    for (version, policy, horizon), cohort in sorted(groups.items()):
        matched = []
        for row in cohort:
            if row['status'] != 'matched':
                continue
            valid = datetime.fromisoformat(row['valid_at'])
            observed = datetime.fromisoformat(row['actual_observed_at']) if row.get('actual_observed_at') else None
            received = datetime.fromisoformat(row['actual_received_at']) if row.get('actual_received_at') else None
            values = [row.get(k) for k in ('predicted_score', 'actual_score', 'baseline_score', 'persistence_score')]
            if (not observed or not received or not valid <= observed <= min(now, valid+timedelta(minutes=5))
                    or not observed <= received <= min(now, valid+timedelta(hours=24))
                    or any(not isinstance(v, (int, float)) or not np.isfinite(v) for v in values)):
                excluded['invalid_matched_record'] += 1
                continue
            matched.append(row)
        by_day = defaultdict(list)
        for row in matched:
            by_day[datetime.fromisoformat(row['issued_at']).astimezone(KST).date()].append(row)
        days = sorted(by_day)
        areas = {r['crowd_area_id'] for r in matched}
        sufficient = len(matched) >= 100 and len(days) >= 7 and len(areas) >= 2 and any(d.weekday() < 5 for d in days) and any(d.weekday() >= 5 for d in days)
        metrics = paired_mae(matched) if matched else None
        item = {'model_version': version, 'baseline_policy': policy, 'scope': 'area_core', 'horizon': horizon,
                'samples': len(matched), 'days': len(days), 'areas': len(areas), 'eligible_issued': len(cohort),
                'missing': sum(r['status'] == 'missing' for r in cohort),
                'pending': sum(r['status'] == 'pending' for r in cohort),
                'unmatched_rate': 1-len(matched)/len(cohort), 'macro_area_mae': metrics,
                'per_area_mae': {str(a): paired_mae([r for r in matched if r['crowd_area_id'] == a]) for a in sorted(areas)},
                'evaluation_complete': sufficient, 'status': 'BLOCKED', 'performance_pass': None,
                'difference_95_ci': None}
        if sufficient:
            rng = np.random.default_rng(20260913)
            differences = {'baseline': [], 'persistence': []}
            for _ in range(iterations):
                sample = [r for index in rng.integers(0, len(days), len(days)) for r in by_day[days[index]]]
                errors = paired_mae(sample)
                for comparator in differences:
                    differences[comparator].append(errors['model']-errors[comparator])
            intervals = {k: [float(v) for v in np.percentile(values, [2.5, 97.5])] for k, values in differences.items()}
            passed = all(metrics['model'] < metrics[k] and intervals[k][1] < 0 for k in intervals)
            item.update(status='PASS' if passed else 'FAIL', performance_pass=passed, difference_95_ci=intervals)
        result.append(item)
    return {'stage': 2, 'status': 'BLOCKED' if not result or any(r['status'] == 'BLOCKED' for r in result)
            or {r['horizon'] for r in result} != {1, 2, 3} else 'PASS' if all(r['status'] == 'PASS' for r in result) else 'FAIL',
            'cohorts': result, 'excluded': dict(excluded), 'seed': 20260913, 'bootstrap_iterations': iterations,
            'resampling_unit': 'KST issue date, all paired rows; area-macro MAE recomputed',
            'reason': 'No adequate prospective labels or horizons' if not result else 'See version-specific cohorts',
            'changes_production': False}


def read_assessment(path, now):
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute('SELECT * FROM places_forecastevaluation')]
    # Django SQLite stores aware datetimes as UTC without a suffix.
    for row in rows:
        for key in ('issued_at', 'valid_at', 'actual_observed_at', 'actual_received_at'):
            if row.get(key) and datetime.fromisoformat(row[key]).tzinfo is None:
                row[key] += '+00:00'
    return assess(rows, now)
