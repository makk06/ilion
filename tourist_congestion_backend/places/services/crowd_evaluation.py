"""Forward area-core evaluation; warnings never alter production forecasts."""
from collections import defaultdict
from copy import deepcopy
from datetime import timedelta
import json
import math
from statistics import mean
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from places.models import CollectorState, CrowdData, ForecastEvaluation
from .crowd_estimator import estimate, percentile, KST
from .crowd_confidence import freshness


def record_forecast(place, inputs, payload, now):
    area = inputs.get('mapping', {}).get('area_id')
    dist, pop = inputs.get('distribution'), inputs.get('population')
    if not area or not dist or not pop or pop.get('is_replaced') or inputs.get('is_demo'):
        return
    if pop['observed_at'] > now or pop.get('fetched_at', now) > now or not freshness(pop['observed_at'], now, 'population'):
        return
    if any(not isinstance(pop.get(k), (int, float)) or not math.isfinite(pop[k]) for k in ('min','max','value')) or not 0 <= pop['min'] <= pop['value'] <= pop['max']:
        return
    # The area experiment has no POI profile, environment or smoothing state.
    core = deepcopy(inputs)
    core.update(place_id=None, latitude=0, longitude=0, profile='unknown', profile_version='area-core-v1',
                events=[], event_coverage=0, events_checked_at=None, weather=None, forecast_weather={},
                calendars={}, opening_schedule={}, sources=[], indoor_outdoor=None)
    core['mapping'] = {'area_id': area, 'match_quality': 1, 'representativeness': 1}
    core.pop('open_status', None)
    core['transit'] = [t for t in core.get('transit', []) if t.get('fetched_at', now) <= now and t['observed_at'] <= now]
    for baseline in core.get('baselines', {}).values():
        baseline['context'] = {}
    # Daily data revisions remain frozen, while the baseline policy defines the cohort.
    eligible = []
    for h in range(4):
        at = (now+timedelta(hours=h)).astimezone(KST)
        baseline = core.get('baselines', {}).get((at.weekday(), at.hour), {})
        supported = baseline.get('sample_days', 0) >= 4 and baseline.get('coverage', 0) >= .7
        if h == 0 and not supported:
            return
        if h and supported:
            eligible.append(h)
    if not eligible:
        return
    result, _ = estimate(core, now)
    version = result['model_version'] + ':area-core-v1'
    hour = now.replace(minute=0, second=0, microsecond=0)
    if ForecastEvaluation.objects.filter(crowd_area_id=area, scope='area_core', model_version=version,
                                         issued_at__gte=hour, issued_at__lt=hour+timedelta(hours=1)).exists():
        return
    snapshot = deepcopy(core)
    snapshot['baseline_policy'] = '84d-median-v1'
    snapshot['baselines'] = {f'{d}:{h}': b for (d,h), b in snapshot.get('baselines', {}).items()}
    snapshot = json.loads(json.dumps(snapshot, cls=DjangoJSONEncoder))
    ForecastEvaluation.objects.bulk_create([ForecastEvaluation(place=None, crowd_area_id=area,
        scope='area_core', issued_at=now, valid_at=now+timedelta(hours=f['hours_ahead']),
        hours_ahead=f['hours_ahead'], predicted_score=f['crowd_score'], baseline_score=f['baseline_score'],
        persistence_score=percentile(dist, pop['value']), distribution=dist, input_snapshot=snapshot,
        baseline_version=inputs.get('baseline_version') or '', model_version=version)
        for f in result['forecast'] if f['hours_ahead'] in eligible])


def evaluate_forecasts(now=None):
    now = now or timezone.now()
    for row in ForecastEvaluation.objects.filter(scope='area_core', status='pending', valid_at__lte=now).iterator():
        deadline = row.valid_at+timedelta(hours=24)
        observations = CrowdData.objects.filter(crowd_area_id=row.crowd_area_id, is_replaced=False,
            observed_at__gte=row.valid_at, observed_at__lte=min(now, row.valid_at+timedelta(minutes=5)),
            fetched_at__lte=min(now, deadline)).order_by('observed_at', 'fetched_at', 'pk')
        for obs in observations:
            if any(obs.raw_data.get(k) for k in ('is_demo','_is_demo','dev_seed','demo')):
                continue
            lo, hi = obs.population_min, obs.population_max
            if lo is None or hi is None or not math.isfinite(lo) or not math.isfinite(hi) or not 0 <= lo <= hi:
                continue
            row.actual_score = percentile(row.distribution, (lo+hi)/2)
            row.actual_observed_at, row.actual_received_at = obs.observed_at, obs.fetched_at
            row.status = 'matched'
            break
        if row.status == 'pending' and now >= deadline:
            row.status = 'missing'
        row.save(update_fields=['actual_score','actual_observed_at','actual_received_at','status'])
    groups = defaultdict(list)
    for row in ForecastEvaluation.objects.filter(scope='area_core', status='matched', actual_score__isnull=False,
                                                  issued_at__gte=now-timedelta(days=84), issued_at__lte=now,
                                                  valid_at__lte=now, actual_received_at__lte=now):
        groups[row.model_version, row.scope, row.input_snapshot.get('baseline_policy', '84d-median-v1'), row.hours_ahead].append(row)
    report = []
    for (version, scope, baseline, horizon), rows in sorted(groups.items()):
        areas = defaultdict(list)
        for row in rows:
            areas[row.crowd_area_id].append(row)
        days = {r.issued_at.astimezone(KST).date() for r in rows}
        sufficient = len(rows)>=100 and len(days)>=7 and len(areas)>=2 and any(d.weekday()<5 for d in days) and any(d.weekday()>=5 for d in days)
        metrics = {key: mean(mean(abs(getattr(r, attr)-r.actual_score) for r in group) for group in areas.values())
                   for key, attr in [('model_mae','predicted_score'),('baseline_mae','baseline_score'),('persistence_mae','persistence_score')]}
        report.append(dict(model_version=version, scope=scope, baseline_policy=baseline, baseline_versions=sorted({r.baseline_version for r in rows}), hours_ahead=horizon,
                           samples=len(rows), days=len(days), areas=len(areas), sufficient=sufficient,
                           per_area={str(area): {'samples': len(group), 'model_mae': mean(abs(r.predicted_score-r.actual_score) for r in group)} for area, group in areas.items()},
                           warning=bool(sufficient and metrics['model_mae']>1.1*metrics['baseline_mae']), **metrics))
    state, _ = CollectorState.objects.get_or_create(provider='system', key='evaluation')
    state.cursor = {'metrics': report, 'warnings_only': True}
    state.last_success_at = now
    state.save(update_fields=['cursor','last_success_at'])
    return state.cursor
