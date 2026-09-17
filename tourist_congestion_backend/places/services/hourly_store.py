"""Bounded reads and reproducible source-version watermarks; no per-input ID arrays."""
import gzip
import hashlib
import json
import os
from pathlib import Path
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from places.hourly_models import HourlyObservation, HourlyRun, HourlyForecast, HourlyDaily
from places.mean_models import MeanEvidence
from .hourly_forecast import VERSION, METRICS, predict, samples, dt, finite


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def raw_root():
    return Path(os.environ.get('HOURLY_RAW_DIR', str(settings.BASE_DIR / 'hourly_raw')))


def record(target, reading, raw, received_at=None):
    received = dt(received_at or timezone.now())
    at, value = dt(reading['observed_at']), reading['value']
    if not finite(value) or value < 0 or at > received or target.metric != METRICS[target.study.provider][0]:
        raise ValueError('Invalid typed observation')
    fingerprint = digest([target.pk, at.isoformat(), value])
    previous = HourlyObservation.objects.filter(fingerprint=fingerprint).first()
    if previous:
        return previous
    raw_hash = digest(raw)
    relative = f'{received.date().isoformat()}/{raw_hash}.json.gz'
    path = raw_root() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with gzip.open(path, 'wt', encoding='utf-8') as output:
            json.dump(raw, output, ensure_ascii=False, allow_nan=False)
    return HourlyObservation.objects.get_or_create(fingerprint=fingerprint, defaults={
        'target': target, 'observed_at': at, 'received_at': received, 'value': value,
        'raw_path': relative, 'raw_hash': raw_hash, 'details': reading.get('details', {})})[0]


def calendar(cutoff, start):
    # Freeze the small calendar projection in the shared run. Never use a later revision.
    found = {}
    for row in MeanEvidence.objects.filter(kind='calendar', received_at__lte=cutoff,
            key__gte=start.date().isoformat(), key__lte=(cutoff+timedelta(hours=3)).date().isoformat()).order_by('received_at', 'id'):
        found[row.key] = bool(row.payload['is_holiday'])
    return found


def dataset(target, cutoff, frozen=None):
    cutoff = dt(cutoff)
    start = cutoff.replace(hour=0)-timedelta(days=84, minutes=15)
    if frozen and frozen['model_version'] != VERSION:
        raise ValueError('Unsupported historical model version')
    watermark = frozen['watermark'] if frozen else (HourlyObservation.objects.aggregate(value=Max('id'))['value'] or 0)
    query = HourlyObservation.objects.filter(target=target, id__lte=watermark,
        observed_at__gte=start, observed_at__lte=cutoff, received_at__lte=cutoff).order_by('received_at', 'id')
    data = {'provider': target.study.provider, 'external_id': target.external_id, 'metric': target.metric,
            'calendar': frozen['calendar'] if frozen else calendar(cutoff, start),
            'observations': [{'id': row.id, 'observed_at': dt(row.observed_at).isoformat(),
                              'received_at': dt(row.received_at).isoformat(), 'value': row.value} for row in query]}
    metadata = {'model_version': VERSION, 'watermark': watermark, 'start': start.isoformat(),
                'cutoff': cutoff.isoformat(), 'provider': target.study.provider, 'external_id': target.external_id,
                'metric': target.metric, 'calendar': data['calendar'], 'hash': digest(data),
                'sampling_policy': 'latest-before-hour-15min-v2'}
    if frozen and metadata != frozen:
        raise ValueError('Input evidence expired, changed, or identity mismatch')
    return data, metadata


def analysis_context(target, cutoff):
    """Known forecast weather / verified event context for descriptive slices only."""
    from .mean_forecast import weather, events
    grid = target.mapping.get('grid')
    source = {'weather': [], 'event_checks': []}
    if grid:
        source['weather'] = [r.payload for r in MeanEvidence.objects.filter(kind='weather', key=grid,
            received_at__lte=cutoff, received_at__gte=cutoff-timedelta(hours=6))]
    if target.study.provider == 'seoul' and target.mapping.get('area_id'):
        source['event_checks'] = [r.payload for r in MeanEvidence.objects.filter(kind='event_check',
            key=str(target.mapping['area_id']), received_at__lte=cutoff,
            received_at__gte=cutoff-timedelta(days=84))]
    context = {}
    for h in (1, 2, 3):
        at = dt(cutoff)+timedelta(hours=h)
        w = weather(source, at, dt(cutoff), forecast=True)
        es, reasons = events(source, at, dt(cutoff))
        context[h] = {'rain_forecast': w[1] != 'none' if w else None,
                      'verified_event': bool(es) if es is not None else None,
                      'event_reasons': reasons}
    return context


def issue(target, hour, parameters=None, phase='shadow'):
    existing = HourlyRun.objects.filter(target=target, issued_at=hour).first()
    if existing:
        return existing
    data, inputs = dataset(target, hour)
    results = predict(data, hour, parameters)
    context = analysis_context(target, hour)
    for result in results:
        result['analysis'] = context[result['hours_ahead']]
    with transaction.atomic():
        run, created = HourlyRun.objects.get_or_create(target=target, issued_at=hour,
            defaults={'inputs': inputs, 'parameters': results[0]['parameters'], 'phase': phase})
        if created:
            HourlyForecast.objects.bulk_create([HourlyForecast(run=run, valid_at=dt(r['valid_at']), payload=r) for r in results])
    return run


def reproduce(run):
    data, _ = dataset(run.target, run.issued_at, run.inputs)
    results = predict(data, run.issued_at, run.parameters)
    annotations = {f.payload['hours_ahead']: f.payload.get('analysis') for f in run.forecasts.all()}
    for r in results:
        r['analysis'] = annotations.get(r['hours_ahead'])
    return results


def match_truth(now):
    for forecast in HourlyForecast.objects.filter(status='pending', valid_at__lte=now).select_related('run__target'):
        target, at = forecast.run.target, dt(forecast.valid_at)
        observations = HourlyObservation.objects.filter(target=target, observed_at__gte=at-timedelta(minutes=15),
            observed_at__lte=at, received_at__lte=at).order_by('received_at', 'id')
        point = samples({'observations': [{'id': r.id, 'observed_at': r.observed_at,
                                          'received_at': r.received_at, 'value': r.value} for r in observations]}, at).get(at)
        if point:
            forecast.actual = point['value']
            forecast.actual_observed_at = point['observed_at']
            forecast.actual_received_at = point['received_at']
            forecast.status = 'matched'
        else:
            forecast.status = 'missing'
        forecast.save(update_fields=['actual', 'actual_observed_at', 'actual_received_at', 'status'])


def prune(now=None):
    now = now or timezone.now()
    HourlyRun.objects.filter(issued_at__lt=now-timedelta(days=300)).delete()
    expired = HourlyObservation.objects.filter(received_at__lt=now-timedelta(days=400))
    # Chunk deletion keeps the single writer from holding a large SQLite transaction.
    while ids := list(expired.values_list('id', flat=True)[:1000]):
        HourlyObservation.objects.filter(id__in=ids).delete()
    HourlyDaily.objects.filter(date__lt=(now-timedelta(days=400)).date()).delete()
    root = raw_root().resolve()
    if root.exists():
        for directory in root.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                day = dt(directory.name+'T00:00:00+09:00')
            except ValueError:
                continue
            if day >= dt(now)-timedelta(days=400):
                continue
            for path in directory.glob('*.json.gz'):
                if path.is_symlink() or root not in path.resolve().parents:
                    continue
                relative = path.relative_to(root).as_posix()
                if not HourlyObservation.objects.filter(raw_path=relative).exists():
                    path.unlink()
            if not any(directory.iterdir()):
                directory.rmdir()
