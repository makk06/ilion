"""Forward-only evaluation against later real area observations, never own outputs."""
from datetime import timedelta
from statistics import mean

from django.utils import timezone
from places.models import CollectorState, CrowdData, ForecastEvaluation
from .crowd_estimator import percentile


def record_forecast(place, inputs, payload, now):
    # One hourly representative per area. Freeze the distribution at issue time.
    area = inputs.get('mapping', {}).get('area_id')
    dist = inputs.get('distribution')
    pop = inputs.get('population')
    if not area or not dist or not pop or pop.get('is_replaced') or payload['is_demo']:
        return
    if payload['normalization'] != 'empirical_percentile' or payload['is_stale']:
        return
    if ForecastEvaluation.objects.filter(crowd_area_id=area, issued_at__gte=now.replace(minute=0,second=0,microsecond=0)).exists():
        return
    persistence = percentile(dist, pop['value'])
    ForecastEvaluation.objects.bulk_create([ForecastEvaluation(place=place, crowd_area_id=area,
        issued_at=now, valid_at=now+timedelta(hours=f['hours_ahead']), hours_ahead=f['hours_ahead'],
        predicted_score=f['crowd_score'], baseline_score=f['baseline_score'], persistence_score=persistence,
        distribution=dist, model_version=payload['model_version']) for f in payload['forecast']])


def evaluate_forecasts(now=None):
    now = now or timezone.now()
    for row in ForecastEvaluation.objects.filter(actual_score=None, valid_at__lt=now-timedelta(minutes=10),
                                                 valid_at__gte=now-timedelta(days=30)).iterator():
        # Observe the horizon, not a provider forecast. A 5-minute tolerance handles collection jitter.
        observations = CrowdData.objects.filter(crowd_area_id=row.crowd_area_id, is_replaced=False,
            observed_at__gte=row.valid_at, observed_at__lte=row.valid_at+timedelta(minutes=5),
            fetched_at__lte=now).order_by('observed_at')
        for obs in observations:
            if any(obs.raw_data.get(k) for k in ('is_demo','_is_demo','dev_seed')):
                continue
            if obs.population_min is None or obs.population_max is None or not 0 <= obs.population_min <= obs.population_max:
                continue
            row.actual_score = percentile(row.distribution, (obs.population_min+obs.population_max)/2)
            row.save(update_fields=['actual_score'])
            break
    report, disabled = {}, []
    for h in (1,2,3):
        rows = list(ForecastEvaluation.objects.filter(hours_ahead=h, actual_score__isnull=False,
                                                      issued_at__gte=now-timedelta(days=84)))
        days = len({r.issued_at.date() for r in rows})
        metrics = {'samples':len(rows), 'days':days, 'sufficient':len(rows)>=100 and days>=7}
        if rows:
            metrics.update(model_mae=mean(abs(r.predicted_score-r.actual_score) for r in rows),
                baseline_mae=mean(abs(r.baseline_score-r.actual_score) for r in rows),
                persistence_mae=mean(abs(r.persistence_score-r.actual_score) for r in rows))
            if metrics['sufficient'] and metrics['model_mae'] > 1.1*metrics['baseline_mae']:
                disabled.append(h)
        report[str(h)] = metrics
    # Once a horizon fails, retain baseline fallback until explicitly reset after review.
    state, _ = CollectorState.objects.get_or_create(provider='system',key='evaluation')
    disabled = sorted(set(disabled) | set(state.cursor.get('disabled_horizons',[])))
    state.cursor={'metrics':report,'disabled_horizons':disabled}; state.last_success_at=now
    state.save()
    return state.cursor
