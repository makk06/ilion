"""Hourly pilot jobs run inside the existing global collector lease."""
import os
import re
import time
from datetime import timedelta
from django.db.models import Count, Q
from django.utils import timezone
from places.models import CrowdArea, Place, CollectorState
from places.hourly_models import HourlyStudy, HourlyTarget, HourlyObservation
from places.integrations.crowd_http import BudgetSession
from places.integrations.exceptions import ExternalAPIError
from places.integrations.seoul_realtime import SeoulRealtimeClient
from places.integrations.tmap_density import TmapDensityClient
from .hourly_forecast import METRICS, dt, samples
from .hourly_store import record, dataset, issue, match_truth


def capacity(provider):
    from .crowd_collector import daily_limit
    try:
        shared = max(0, int(os.environ.get(f'{provider.upper()}_OTHER_DAILY_CALLS', '0')))
    except ValueError:
        return 0
    return min(10, max(0, int(.8*daily_limit(provider))-shared)//24)


def configured(provider):
    from .crowd_collector import KEY_ENV
    return bool(os.environ.get(KEY_ENV[provider])) and capacity(provider) > 0


def create_study(provider, now=None):
    # Explicit command creates a new study; no silent replacement of a frozen cohort.
    if provider not in METRICS:
        raise ValueError('Unknown provider')
    if HourlyStudy.objects.filter(provider=provider).exists():
        raise ValueError('Study already exists; use a new database/explicit migration for a new cohort')
    study = HourlyStudy.objects.create(provider=provider, started_at=now or timezone.now(), config={'max_targets': 10}, state={})
    if provider == 'seoul':
        areas = CrowdArea.objects.filter(source='seoul_realtime').annotate(
            linked=Count('place_mappings', filter=Q(place_mappings__verified=True))).filter(linked__gt=0).order_by('-linked', 'external_id')[:10]
        for area in areas:
            grid = None
            if area.geometry:
                from shapely.geometry import shape
                from places.integrations.weather import weather_grid
                center = shape(area.geometry).representative_point()
                gx, gy = weather_grid(center.y, center.x)
                grid = f'{gx},{gy}'
            HourlyTarget.objects.create(study=study, external_id=area.external_id, name=area.name,
                metric=METRICS[provider][0], scope=METRICS[provider][2], priority=area.linked,
                mapping={'area_id': area.pk, 'grid': grid, 'place_ids': list(area.place_mappings.filter(verified=True).values_list('place_id', flat=True))})
    return study


def compact(text):
    return re.sub(r'\s+', '', str(text or '')).casefold()


def discover_tmap(study):
    """Conservative exact name/address match; unmatched places stay outside the pilot."""
    from .crowd_collector import charge, daily_limit, BudgetExhausted
    from django.db import transaction
    if study.provider != 'tmap' or study.state.get('selection_complete') or study.state.get('collection_start'):
        raise ValueError('Discovery is only allowed before collection starts')
    if not configured('tmap'):
        return {'status': 'awaiting_configuration'}
    def discovery_charge(retry=False):
        day = dt(timezone.now()).date()
        with transaction.atomic():
            budget, _ = CollectorState.objects.get_or_create(provider='tmap', key='_hourly_discovery')
            if budget.budget_date != day:
                budget.calls, budget.budget_date = 0, day
            if budget.calls >= daily_limit('tmap')-int(.8*daily_limit('tmap')):
                raise BudgetExhausted('Discovery reserve exhausted')
            charge('tmap', retry=True)
            budget.calls += 1
            budget.save(update_fields=['calls', 'budget_date'])
    session = BudgetSession(discovery_charge)
    client = TmapDensityClient(session)
    cursor = study.state.get('discovery_cursor', 0)
    scanned = 0
    try:
        # Stable scan order persisted across quota-limited command runs.
        places = Place.objects.annotate(linked=Count('crowd_area_mappings', filter=Q(crowd_area_mappings__verified=True))).order_by('-linked', 'id')
        for place in places[cursor:cursor+100]:
            if study.targets.count() >= 10:
                break
            try:
                hits = client.search(place.name)
                matches = []
                for hit in hits:
                    addresses = [hit.get('roadAddress'), hit.get('address')]
                    for address in hit.get('newAddressList', {}).get('newAddress', []):
                        addresses.append(address.get('fullAddressRoad'))
                    if compact(hit.get('name')) == compact(place.name) and compact(place.address) and compact(place.address) in {compact(a) for a in addresses}:
                        matches.append(hit)
                if len(matches) == 1:
                    hit = matches[0]
                    reading, raw = client.fetch(hit['id'])
                    target, _ = HourlyTarget.objects.get_or_create(study=study, external_id=str(hit['id']), defaults={
                        'name': place.name, 'metric': METRICS['tmap'][0], 'scope': METRICS['tmap'][2], 'priority': 0,
                        'mapping': {'place_ids': [], 'name': place.name, 'address': place.address, 'verified_at': timezone.now().isoformat()}})
                    ids = sorted(set(target.mapping['place_ids']+[place.pk]))
                    target.mapping = {**target.mapping, 'place_ids': ids}
                    target.priority = len(ids)
                    from places.integrations.weather import weather_grid
                    gx, gy = weather_grid(float(place.latitude), float(place.longitude))
                    target.mapping['grid'] = f'{gx},{gy}'
                    target.save(update_fields=['mapping', 'priority'])
                    record(target, reading, raw)
            except ExternalAPIError:
                # Do not log provider bodies or key-bearing request URLs.
                study.state['discovery_status'] = 'provider_or_budget_unavailable'
                break
            scanned += 1
    finally:
        session.close()
        study.state['discovery_cursor'] = cursor+scanned
        study.save(update_fields=['state'])
    return {'candidates': study.targets.count(), 'scanned': scanned}


def activate(study, now):
    if not configured(study.provider):
        return False
    if not study.state.get('collection_start'):
        targets = list(study.targets.order_by('-priority', 'external_id')[:capacity(study.provider)])
        if not targets:
            return False
        study.targets.filter(pk__in=[t.pk for t in targets]).update(active=True)
        study.state.update(capacity=len(targets))
        study.save(update_fields=['state'])
    return True


def select(study, now):
    if study.state.get('selection_complete') or not study.state.get('collection_start'):
        return
    start = dt(study.state['collection_start'])
    end = start+timedelta(days=7)
    if dt(now) < end:
        return
    rates = {}
    for target in study.targets.filter(active=True):
        data, _ = dataset(target, end)
        points = samples(data, end)
        rate = sum(start <= t < end for t in points)/168
        rates[str(target.pk)] = rate
        target.selected = rate >= .9
        target.save(update_fields=['selected'])
    study.state.update(selection_complete=True, rates=rates, training_start=end.isoformat())
    study.save(update_fields=['state'])


def tick(now=None, max_seconds=40, provider_filter=None):
    from .crowd_collector import charge, BudgetExhausted
    now = dt(now or timezone.now())
    deadline = time.monotonic()+max_seconds
    report = {'collected': 0, 'issued': 0, 'failed': 0, 'waiting': []}
    match_truth(now)
    studies = HourlyStudy.objects.order_by('id')
    if provider_filter:
        studies = studies.filter(provider=provider_filter)
    for study in studies:
        ready = activate(study, now)
        select(study, now)
        if not ready:
            report['waiting'].append(study.provider)
        if now.minute < 2:
            for target in study.targets.filter(selected=True).select_related('study'):
                run = issue(target, now.replace(minute=0, second=0, microsecond=0), study.state.get('parameters'))
                report['issued'] += 1
        if not ready or now.minute < 58:
            continue
        session = BudgetSession(lambda retry=False, p=study.provider: charge(p, retry=retry))
        try:
            # A reduced quota pauses excess targets; never silently replace the cohort.
            for target in study.targets.filter(active=True).order_by('-priority', 'external_id')[:capacity(study.provider)]:
                if time.monotonic() >= deadline or dt(timezone.now()).replace(minute=0, second=0, microsecond=0) > now.replace(minute=0, second=0, microsecond=0):
                    break
                key = f'hourly:{target.pk}'
                state, _ = CollectorState.objects.get_or_create(provider=study.provider, key=key)
                slot = (now.replace(minute=0, second=0, microsecond=0)+timedelta(hours=1)).isoformat()
                if state.cursor.get('slot') == slot:
                    continue
                if not study.state.get('collection_start'):
                    study.state['collection_start'] = slot
                    study.save(update_fields=['state'])
                try:
                    if study.provider == 'tmap':
                        reading, raw = TmapDensityClient(session).fetch(target.external_id)
                    else:
                        r = SeoulRealtimeClient(session=session).fetch_population(target.external_id)
                        if r.external_id != target.external_id or r.is_replaced or r.population_min is None or r.population_max is None or not 0 <= r.population_min <= r.population_max or any(r.raw_data.get(k) for k in ('demo', 'is_demo', '_is_demo', 'dev_seed')):
                            raise ExternalAPIError('Invalid Seoul population')
                        reading = {'observed_at': r.observed_at, 'value': (r.population_min+r.population_max)/2,
                                   'details': {'min': r.population_min, 'max': r.population_max}}
                        raw = r.raw_data
                    record(target, reading, raw)
                    if study.provider == 'seoul':
                        from .input_sync import save_citydata
                        save_citydata(CrowdArea.objects.get(pk=target.mapping['area_id']), r, [], timezone.now())
                    report['collected'] += 1
                    state.cursor = {'slot': slot, 'status': 'ok'}
                except (ExternalAPIError, ValueError):
                    report['failed'] += 1
                    state.cursor = {'slot': slot, 'status': 'provider_or_budget_unavailable'}
                state.save(update_fields=['cursor'])
        finally:
            session.close()
    return report
