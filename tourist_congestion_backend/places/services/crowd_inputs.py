"""Bounded bulk reads shared by API and scheduled estimation. No external calls."""
from datetime import timedelta
import math

from django.conf import settings
from django.db.models import Q, OuterRef, Subquery, Case, When, Value
from django.utils import timezone

from places.integrations.weather import weather_grid
from places.models import (CalendarDay, CollectorState, CrowdArea, CrowdData, CrowdEstimate,
    HistoricalBaseline, PlaceCrowdArea, PlaceCrowdProfile, PlaceSource, TourEvent,
    TransitObservation, WeatherSnapshot)
from .crowd_estimator import KST, MODEL_VERSION, estimate, profile_for, profiles as profile_config
from .crowd_confidence import freshness


def _source(provider, observed, fetched, role, **extra):
    return {'provider': provider, 'observed_at': observed.isoformat() if observed else None,
            'fetched_at': fetched.isoformat() if fetched else None, 'role': role, **extra}


def load_inputs(places, now):
    places = list(places)
    ids = [p.pk for p in places]
    if not ids:
        return {}
    profiles = {p.place_id: p for p in PlaceCrowdProfile.objects.filter(place_id__in=ids)}
    sources = {}
    for s in PlaceSource.objects.filter(place_id__in=ids, source='tour_api', match_status='matched').order_by('id'):
        sources.setdefault(s.place_id, s)
    mappings = {}
    for m in PlaceCrowdArea.objects.filter(place_id__in=ids, verified=True).filter(
            Q(valid_from__isnull=True)|Q(valid_from__lte=now)).filter(
            Q(valid_until__isnull=True)|Q(valid_until__gt=now)).select_related('crowd_area').annotate(
                mapping_priority=Case(When(match_method__in=('manual','source'),then=Value(0)),default=Value(1))
            ).order_by('mapping_priority','-is_primary', 'id'):
        mappings.setdefault(m.place_id, m)
    area_ids = {m.crowd_area_id for m in mappings.values()}
    population = {}
    latest_pop = CrowdData.objects.filter(crowd_area_id=OuterRef('pk'), observed_at__lte=now,
            observed_at__gte=now-timedelta(hours=24)).order_by('-observed_at','-id')
    latest_ids = CrowdArea.objects.filter(pk__in=area_ids).annotate(latest_id=Subquery(latest_pop.values('pk')[:1])).values('latest_id')
    for row in CrowdData.objects.filter(pk__in=Subquery(latest_ids)):
        population.setdefault(row.crowd_area_id, row)
    transit = {}
    latest_transit = TransitObservation.objects.filter(crowd_area_id=OuterRef('crowd_area_id'), mode=OuterRef('mode'),
            window_minutes=30, observed_at__lte=now, observed_at__gte=now-timedelta(minutes=30)).order_by('-observed_at','-id')
    for row in TransitObservation.objects.filter(crowd_area_id__in=area_ids, pk=Subquery(latest_transit.values('pk')[:1])):
        transit.setdefault((row.crowd_area_id, row.mode), row)
    base = {}
    versions = {}
    latest_version = HistoricalBaseline.objects.filter(crowd_area_id=OuterRef('crowd_area_id'), metric=OuterRef('metric'),
        period_end__lte=now, created_at__lte=now).order_by('-period_end','-id')
    for row in HistoricalBaseline.objects.filter(crowd_area_id__in=area_ids, version=Subquery(latest_version.values('version')[:1])):
        key = (row.crowd_area_id, row.metric)
        versions.setdefault(key, row.version)
        if row.version == versions[key]:
            base.setdefault((row.crowd_area_id, row.metric, row.weekday, row.hour), row)
    area_baselines = {}
    for (area, metric, weekday, hour), row in base.items():
        if metric == 'population' and weekday >= 0:
            area_baselines.setdefault(area, {})[weekday, hour] = {
                'median': row.median, 'sample_days': row.sample_days, 'coverage': row.coverage, 'context': row.context}
    calendars = {c.date: {'is_holiday': c.is_holiday, 'holiday_run': c.holiday_run, 'fetched_at': c.fetched_at}
                 for c in CalendarDay.objects.filter(date__gte=now.astimezone(KST).date(), date__lte=(now+timedelta(hours=3)).astimezone(KST).date())
                 if freshness(c.fetched_at, now, 'calendar') > 0}
    events = list(TourEvent.objects.filter(active=True, end_date__gte=(now-timedelta(days=1)).date(),
        start_date__lte=(now+timedelta(days=1)).date(), fetched_at__lte=now).values())
    event_state = CollectorState.objects.filter(provider='tour_api', key='events').first()
    grids = {}
    for p in places:
        profile = profiles.get(p.pk)
        grids[p.pk] = (profile.grid_x, profile.grid_y) if profile and profile.grid_x and profile.grid_y else weather_grid(float(p.latitude), float(p.longitude))
    grid_values = set(grids.values())
    weather_rows = []
    if grid_values:
        weather_rows = list(WeatherSnapshot.objects.filter(grid_x__in={g[0] for g in grid_values}, grid_y__in={g[1] for g in grid_values},
            issued_at__lte=now, issued_at__gte=now-timedelta(hours=4), fetched_at__lte=now,
            valid_at__gte=now-timedelta(hours=4), valid_at__lte=now+timedelta(hours=4)).order_by('-issued_at'))
    by_grid = {}
    for row in weather_rows:
        by_grid.setdefault((row.grid_x, row.grid_y), []).append(row)
    result = {}
    for p in places:
        profile, source, mapping = profiles.get(p.pk), sources.get(p.pk), mappings.get(p.pk)
        raw = source.raw_data if source else {}
        area_id = mapping.crowd_area_id if mapping else None
        baselines = area_baselines.get(area_id, {})
        distribution = base.get((area_id, 'population', -1, -1))
        inp = {'place_id': p.pk, 'latitude': float(p.latitude), 'longitude': float(p.longitude),
            'profile': profile.profile if profile else profile_for(raw, p.category),
            'profile_version': profile.version if profile else profile_config()['version'],
            'opening_schedule': profile.opening_schedule if profile else {},
            'indoor_outdoor': p.indoor_outdoor, 'open_status': p.open_status,
            'is_demo': bool(raw.get('is_demo') or raw.get('_is_demo') or raw.get('demo') or raw.get('dev_seed')),
            'calendars': calendars, 'baselines': baselines,
            'distribution': distribution.distribution if distribution and distribution.sample_days >= 28 and distribution.coverage >= .7 else [],
            'baseline_version': distribution.version if distribution else '',
            'mapping': {}, 'population': None, 'transit': [], 'events': events,
            'events_checked_at': event_state.last_success_at if event_state else None,
            'event_coverage': event_state.cursor.get('coverage', .5 if event_state.cursor.get('page') else 1) if event_state and event_state.last_success_at else 0,
            'weather': None, 'forecast_weather': {}, 'sources': []}
        if source:
            inp['sources'].append(_source('tour_api', None, source.last_synced_at, 'place_metadata', external_id=source.external_id))
        if mapping:
            inp['mapping'] = {'area_id': area_id, 'area_name': mapping.crowd_area.name,
                'match_method': mapping.match_method, 'match_quality': mapping.match_quality,
                'geometry_version': mapping.crowd_area.geometry_version,
                'representativeness': mapping.representativeness}
        pop = population.get(area_id)
        if pop and pop.population_min is not None and pop.population_max is not None and 0 <= pop.population_min <= pop.population_max:
            inp['population'] = {'value': (pop.population_min+pop.population_max)/2,
                'min': pop.population_min, 'max': pop.population_max, 'observed_at': pop.observed_at,
                'is_replaced': pop.is_replaced, 'level': pop.crowd_level}
            inp['is_demo'] |= bool(pop.raw_data.get('is_demo') or pop.raw_data.get('_is_demo') or pop.raw_data.get('dev_seed'))
            inp['sources'].append(_source('seoul_citydata' if pop.raw_data.get('_provider') == 'citydata' else 'seoul_population',
                pop.observed_at, pop.fetched_at or pop.created_at, 'area_population', timestamp_quality='source', is_replaced=pop.is_replaced))
        local = now.astimezone(KST)
        for mode in ('subway', 'bus'):
            row = transit.get((area_id, mode))
            baseline = base.get((area_id, mode, local.weekday(), local.hour))
            if row and baseline:
                inp['transit'].append({'mode': mode, 'value': (row.arrivals_min+row.arrivals_max)/2,
                    'baseline': baseline.median, 'sample_days': baseline.sample_days,
                    'observed_at': row.observed_at, 'timestamp_quality': row.timestamp_quality})
                inp['sources'].append(_source('seoul_citydata', row.observed_at, row.fetched_at, 'transit_'+mode, timestamp_quality=row.timestamp_quality))
        grid_weather = by_grid.get(grids[p.pk], [])
        for h in range(4):
            target = now+timedelta(hours=h)
            if h == 0:
                row = next((w for w in grid_weather if w.product == 'getUltraSrtNcst' and w.valid_at <= target), None)
            else:
                row = None
            if row is None:
                target_hour = target.replace(minute=0, second=0, microsecond=0)
                row = next((w for w in grid_weather if w.product != 'getUltraSrtNcst' and w.valid_at == target_hour), None)
            if row:
                value = {'issued_at': row.issued_at, 'valid_at': row.valid_at, 'values': row.values}
                if h == 0:
                    inp['weather'] = value
                else:
                    inp['forecast_weather'][h] = value
                inp['sources'].append(_source('kma', row.valid_at, row.fetched_at, 'weather_now' if h == 0 else f'weather_forecast_{h}h',
                    issued_at=row.issued_at.isoformat(), product=row.product))
        if event_state and event_state.last_success_at:
            inp['sources'].append(_source('tour_api', None, event_state.last_success_at, 'nearby_events'))
        if calendars:
            inp['sources'].append(_source('kasi', None, min(c['fetched_at'] for c in calendars.values()), 'public_holidays'))
        result[p.pk] = inp
    return result


def estimates_for(places, now=None, *, persist=False):
    now = now or timezone.now()
    places = list(places)
    if not getattr(settings, 'CROWD_ESTIMATION_ENABLED', True):
        return {}
    usable = [p for p in places if math.isfinite(float(p.latitude)) and math.isfinite(float(p.longitude))
              and -85 < float(p.latitude) < 85 and -180 <= float(p.longitude) <= 180 and p.name.strip()]
    inputs = load_inputs(usable, now)
    previous = {r.place_id: r for r in CrowdEstimate.objects.filter(place_id__in=inputs)}
    result = {p.pk: {'place_id':p.pk,'status':'unavailable','crowd_score':None,'crowd_level':None,
        'confidence':0,'estimated_visitors':None,'forecast':[],'is_demo':False,
        'limitations':['INVALID_PLACE_METADATA']} for p in places if p.pk not in inputs}
    disabled = set(getattr(settings, 'CROWD_DISABLE_TREND_HORIZONS', []))
    evaluation = CollectorState.objects.filter(provider='system', key='evaluation').first()
    disabled.update(evaluation.cursor.get('disabled_horizons', []) if evaluation else [])
    for place in usable:
        old = previous.get(place.pk)
        if old and not persist and old.refresh_after > now and old.model_version == MODEL_VERSION:
            result[place.pk] = old.payload
            continue
        payload, state = estimate(inputs[place.pk], now, old.state if old else None,
                                  trend_enabled=tuple(h not in disabled for h in (1, 2, 3)))
        result[place.pk] = payload
        if persist:
            CrowdEstimate.objects.update_or_create(place=place, defaults={'payload': payload, 'state': state,
                'estimated_at': now, 'refresh_after': now+timedelta(minutes=5), 'model_version': MODEL_VERSION})
            from .crowd_evaluation import record_forecast
            record_forecast(place, inputs[place.pk], payload, now)
    return result


def summary(payload):
    return {k: v for k, v in payload.items() if k not in ('forecast', 'factors', 'source_population')}
