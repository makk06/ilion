"""Django adapter for the isolated mean experiment."""
import hashlib
import json
import math
from datetime import timedelta
from statistics import mean
from django.utils import timezone
from places.models import MeanEvidence, MeanPrediction, MeanStudy
from .mean_forecast import dt, predict, population, hourly, DEFAULTS, calendar, weather, events


def dataset(area, grid, cutoff):
    result = {'area_id': area, 'population': [], 'weather': [], 'calendar': [], 'event_checks': [], 'evidence_ids': []}
    from django.db.models import Q
    rows = MeanEvidence.objects.filter(received_at__lte=cutoff, received_at__gte=cutoff-timedelta(days=400)).filter(
        Q(kind='population', key=str(area)) | Q(kind='weather', key=grid) | Q(kind='calendar') |
        Q(kind='event_check', key=str(area))).order_by('received_at', 'id')
    for row in rows:
        result['evidence_ids'].append(row.pk)
        if row.kind == 'population' and row.key == str(area):
            result['population'].append(row.payload)
        elif row.kind == 'weather' and row.key == grid:
            result['weather'].append(row.payload)
        elif row.kind == 'calendar':
            result['calendar'].append(row.payload)
        elif row.kind == 'event_check' and row.key == str(area):
            result['event_checks'].append(row.payload)
    return result


def audit(now=None):
    now = now or timezone.now()
    groups = {}
    for key in MeanEvidence.objects.filter(kind='population').values_list('key', flat=True).distinct():
        rows = population([r.payload for r in MeanEvidence.objects.filter(kind='population', key=key)], now)
        groups[key] = {'valid_observations': len(rows), 'hourly_labels': len(hourly(rows)),
                       'first': rows[0]['at'].isoformat() if rows else None,
                       'last': rows[-1]['at'].isoformat() if rows else None}
    return {'areas': groups, 'evidence_rows': MeanEvidence.objects.count(),
            'status': 'DATA_AUDIT_ONLY', 'accuracy_validated': False}


def reproduce(prediction):
    snapshot = MeanEvidence.objects.get(pk=prediction.payload['input_snapshot_id']).payload
    ids = snapshot['evidence_ids']
    sources = list(MeanEvidence.objects.filter(pk__in=ids).order_by('received_at', 'id'))
    if len(sources) != len(ids):
        raise ValueError('Input evidence expired or missing')
    data = {'area_id': prediction.area_id, 'population': [], 'weather': [], 'calendar': [],
            'event_checks': [], 'evidence_ids': []}
    for source in sources:
        data['evidence_ids'].append(source.pk)
        key = 'event_checks' if source.kind == 'event_check' else source.kind
        data[key].append(source.payload)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if digest != prediction.payload['input_hash']:
        raise ValueError('Input evidence hash mismatch')
    return predict(data, prediction.issued_at, prediction.payload['parameters'])


def select_areas(study, now):
    end = study.started_at + timedelta(days=7)
    if now < end:
        return False
    scores = []
    for area in study.config['candidates']:
        rows = population(dataset(area, study.config['grids'][str(area)], end)['population'], end)
        seconds = study.config.get('interval_minutes', 5)*60
        bins = {int((r['at']-study.started_at).total_seconds()//seconds) for r in rows if study.started_at <= r['at'] < end}
        scores.append((len(bins)/math.ceil(7*86400/seconds), area))
    selected = [area for rate, area in sorted(scores, key=lambda r: (-r[0], r[1]))[:3] if rate >= .9]
    study.state.update(selection_rates={str(a): s for s, a in scores}, areas=selected,
                       selection_complete=True, selection_at=end.isoformat())
    study.save(update_fields=['state'])
    return len(selected) == 3


def label(data, target, now):
    rows = population(data['population'], min(now, target+timedelta(hours=24)))
    row = next((r for r in rows if target <= r['at'] <= target+timedelta(minutes=5)), None)
    return row


def annotate(row, data, now):
    target = dt(row['valid_at'])
    tags = ['weekend' if target.weekday() >= 5 else 'weekday']
    if calendar(data, target, now):
        tags.append('holiday')
    w = weather(data, target, now, forecast=True)
    if w and w[1] != 'none':
        tags.append('rain')
    es, _ = events(data, target, now)
    if es:
        tags.append('event')
    row['tags'] = tags
    row['target_editions'] = [e['edition'] for e in es] if es else []
    row['target_families'] = [e['family'] for e in es] if es else []
    return row


def tick(now=None):
    now = dt(now or timezone.now())
    study = MeanStudy.objects.filter(name='area-mean-v1').first()
    if not study:
        return {'status': 'not_initialized'}
    if not study.state.get('selection_complete'):
        select_areas(study, now)
    areas = study.state.get('areas', [])
    caches = {a: dataset(a, study.config['grids'][str(a)], now) for a in areas}
    matched = 0
    for stored in MeanPrediction.objects.filter(study=study, status='pending', valid_at__lte=now):
        actual = label(caches[stored.area_id], dt(stored.valid_at), now)
        if actual:
            stored.actual, stored.actual_received_at, stored.status = actual['value'], actual['received_at'], 'matched'
            matched += 1
        elif now >= stored.valid_at+timedelta(hours=24):
            stored.status = 'missing'
        stored.save(update_fields=['actual', 'actual_received_at', 'status'])
    # Never backdate a forecast after seeing post-issue observations.
    hour = now.replace(minute=0, second=0, microsecond=0)
    if now-hour > timedelta(minutes=1):
        return {'status': 'awaiting_next_hour', 'matched': matched}
    issued = 0
    params = study.state.get('parameters', DEFAULTS)
    for area, data in caches.items():
        # Freeze only evidence available at the advertised issue time, even if the job runs seconds late.
        data = dataset(area, study.config['grids'][str(area)], hour)
        encoded = json.dumps(data, sort_keys=True).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        from .mean_archive import append
        snapshot = append('input_snapshot', f'{area}:{hour.isoformat()}', hour,
                          {'area_id': area, 'evidence_ids': data['evidence_ids'], 'input_hash': digest})
        for row in predict(data, hour, params):
            annotate(row, data, hour)
            row['input_hash'] = digest
            row['input_snapshot_id'] = snapshot.pk
            row['baseline_policy'] = '84d-hour-first-5min-v1'
            row['phase'] = 'shadow'
            _, created = MeanPrediction.objects.get_or_create(study=study, area_id=area, issued_at=hour,
                valid_at=dt(row['valid_at']), defaults={'payload': row})
            issued += created
    return {'status': 'shadow', 'issued': issued, 'matched': matched, 'areas': areas}


def frozen_scales(datasets, train_end):
    scales, peaks = {}, {}
    for area, data in datasets.items():
        values = sorted(r['value'] for r in hourly(population(data['population'], train_end)))
        scales[str(area)] = max(1, mean(values)) if values else 1
        peaks[str(area)] = values[max(0, math.ceil(.9*len(values))-1)] if values else 0
    return scales, peaks


def validation_rows(study, start=None, end=None):
    query = MeanPrediction.objects.filter(study=study)
    if start:
        query = query.filter(issued_at__gte=start)
    if end:
        query = query.filter(issued_at__lt=end)
    found = {(r.area_id, dt(r.issued_at), r.payload['hours_ahead']):
             {**r.payload, **r.payload['comparisons'], 'actual': r.actual} for r in query}
    if start is not None and end is not None:
        at = dt(start).replace(minute=0, second=0, microsecond=0)
        if at < dt(start):
            at += timedelta(hours=1)
        while at < dt(end):
            for area in study.state.get('areas', []):
                for h in (1, 2, 3):
                    found.setdefault((area, at, h), {'area_id': area, 'issued_at': at.isoformat(), 'hours_ahead': h,
                        'valid_at': (at+timedelta(hours=h)).isoformat(), 'population': None, 'actual': None,
                        'parameters': study.state.get('parameters', {}), 'status': 'not_issued'})
            at += timedelta(hours=1)
    return list(found.values())


def validate_shadow(study, now):
    from .mean_validation import assess
    from .mean_replay import event_support
    validation = study.state.get('validation', {})
    if not study.state.get('shadow_start') or validation.get('status') != 'PASS':
        return {'status': 'NEEDS_MORE_DATA', 'reasons': ['backtest_must_pass_before_locked_shadow']}
    start = dt(study.state['shadow_start'])
    end = start+timedelta(days=14)
    if now < end+timedelta(hours=27):
        return {'status': 'NEEDS_MORE_DATA', 'reasons': ['requires_14_days_of_locked_shadow_plus_label_delay']}
    rows = validation_rows(study, start, end)
    for row in rows:
        if row['parameters'] != validation['parameters']:
            row['population'] = None
    datasets = {a: dataset(a, study.config['grids'][str(a)], now) for a in study.state['areas']}
    return assess(rows, study.state['areas'], validation['scales'], validation['peaks'],
                  validation['reference'], event_support(datasets, start, end, rows))


def adapter(payload, area_id, now):
    """Only a gate-approved version can replace the forecast section."""
    study = MeanStudy.objects.filter(name='area-mean-v1').first()
    if not study or study.state.get('deployment') not in ('mean', 'arithmetic') or area_id not in study.state.get('areas', []):
        return payload
    deployment = study.state['deployment']
    if study.state.get('promotion', {}).get('status') != 'PASS':
        return payload
    hour = dt(now).replace(minute=0, second=0, microsecond=0)
    rows = list(MeanPrediction.objects.filter(study=study, area_id=area_id, issued_at=hour).order_by('valid_at'))
    forecasts = []
    for h in (1, 2, 3):
        stored = next((r for r in rows if r.payload['hours_ahead'] == h), None)
        row = stored.payload if stored else {}
        if row and row.get('parameters') != study.state.get('parameters'):
            row = {}
        value = row.get('population') if deployment == 'mean' else row.get('comparisons', {}).get('arithmetic')
        score = row.get('crowd_score') if deployment == 'mean' else row.get('arithmetic_score')
        from .crowd_estimator import level
        forecasts.append({'hours_ahead': h, 'valid_at': (hour+timedelta(hours=h)).isoformat(),
            'crowd_score': round(score) if score is not None else None,
            'crowd_level': level(score)[0] if score is not None else None,
            'confidence': 0, 'confidence_status': 'not_calibrated', 'scope': 'area_population',
            'area_id': area_id, 'area_population': value, 'model_version': 'area-mean-v1:'+deployment,
            'status': row.get('status', 'unavailable'), 'reasons': row.get('reasons', ['forecast_missing']),
            'normalization': 'empirical_percentile', 'baseline_score': None,
            'weather_available': 'weather_unavailable' not in row.get('reasons', []) and bool(row),
            'baseline_fallback': deployment == 'arithmetic'})
    return {**payload, 'forecast': forecasts}
