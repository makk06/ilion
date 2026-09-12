from collections import defaultdict
from datetime import timedelta
from statistics import median

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from places.models import CrowdData, HistoricalBaseline, HistoricalSample, TransitObservation
from .crowd_estimator import KST


def rebuild_baselines(now=None, heartbeat=None):
    now = now or timezone.now()
    end = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    # Rebuild recent immutable hourly buckets before raw data retention expires.
    start = end-timedelta(days=30)
    previous = HistoricalSample.objects.aggregate(last=Max('bucket_at'))['last']
    if previous:
        # Providers reject backward observations. Revisit a two-day overlap for late arrivals,
        # rather than loading a month of five-minute raw evidence every day.
        start = max(start, previous-timedelta(days=2))
    grouped = defaultdict(list)
    for index, row in enumerate(CrowdData.objects.filter(observed_at__gte=start, observed_at__lt=end, is_replaced=False).iterator()):
        if heartbeat and index % 10000 == 0:
            heartbeat()
        if row.raw_data.get('is_demo') or row.raw_data.get('_is_demo') or row.raw_data.get('dev_seed'):
            continue
        if (row.fetched_at or row.created_at) > now:
            continue
        if row.population_min is None or row.population_max is None or not 0 <= row.population_min <= row.population_max:
            continue
        bucket = row.observed_at.astimezone(KST).replace(minute=0, second=0, microsecond=0)
        grouped[row.crowd_area_id, 'population', bucket].append(((row.population_min+row.population_max)/2, row.raw_data.get('_context', {}), row.fetched_at or row.created_at))
    for row in TransitObservation.objects.filter(observed_at__gte=start, observed_at__lt=end, fetched_at__lte=now, window_minutes=30).iterator():
        bucket = row.observed_at.astimezone(KST).replace(minute=0, second=0, microsecond=0)
        grouped[row.crowd_area_id, row.mode, bucket].append(((row.arrivals_min+row.arrivals_max)/2, {}, row.fetched_at))
    for index, ((area, metric, bucket), samples) in enumerate(grouped.items()):
        if heartbeat and index % 1000 == 0:
            heartbeat()
        contexts = [s[1] for s in samples if s[1]]
        context = {}
        if contexts:
            keys = set.intersection(*(set(c) for c in contexts))
            context = {k: median(c[k] for c in contexts) for k in keys if all(isinstance(c[k], (int, float)) for c in contexts)}
        HistoricalSample.objects.update_or_create(crowd_area_id=area, metric=metric, bucket_at=bucket,
            defaults={'value': median(s[0] for s in samples), 'sample_count': len(samples),
                      'context': context, 'available_at': max(s[2] for s in samples)})
    period_start = end-timedelta(days=84)
    histories = defaultdict(list)
    for row in HistoricalSample.objects.filter(bucket_at__gte=period_start, bucket_at__lt=end, available_at__lte=now, quality__gt=0).iterator():
        histories[row.crowd_area_id, row.metric].append(row)
    version = end.strftime('%Y-%m-%d')
    count = 0
    for (area, metric), rows in histories.items():
        if heartbeat:
            heartbeat()
        buckets = defaultdict(list)
        for row in rows:
            at = row.bucket_at.astimezone(KST)
            buckets[at.weekday(), at.hour].append(row)
        buckets[-1, -1] = rows
        first_day = min(r.bucket_at for r in rows).astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        span_days = max(1, (end-first_day).days)
        coverage = min(1, len(rows)/(span_days*24))
        with transaction.atomic():
            for (weekday, hour), samples in buckets.items():
                vals = sorted(r.value for r in samples)
                mid = median(vals)
                days = len({r.bucket_at.astimezone(KST).date() for r in samples})
                contexts = [r.context for r in samples if r.context]
                context = {}
                if contexts:
                    keys = set.intersection(*(set(c) for c in contexts))
                    context = {k: median(c[k] for c in contexts) for k in keys}
                HistoricalBaseline.objects.update_or_create(crowd_area_id=area, metric=metric, weekday=weekday, hour=hour, version=version,
                    defaults={'median': mid, 'mad': median(abs(v-mid) for v in vals),
                        'distribution': vals if weekday == -1 else [], 'sample_days': days, 'coverage': coverage,
                        'context': context, 'period_start': period_start, 'period_end': end})
                count += 1
    return count


def prune_evidence(now=None):
    now = now or timezone.now()
    # Caller must successfully aggregate before pruning.
    CrowdData.objects.filter(observed_at__lt=now-timedelta(days=30)).delete()
    TransitObservation.objects.filter(observed_at__lt=now-timedelta(days=30)).delete()
    HistoricalSample.objects.filter(bucket_at__lt=now-timedelta(days=400)).delete()
    HistoricalBaseline.objects.filter(period_end__lt=now-timedelta(days=400)).delete()
    from places.models import WeatherSnapshot, ForecastEvaluation
    WeatherSnapshot.objects.filter(valid_at__lt=now-timedelta(days=30)).delete()
    ForecastEvaluation.objects.filter(issued_at__lt=now-timedelta(days=400)).delete()
