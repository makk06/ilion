"""Single-worker scheduler with expiring DB lease and per-attempt quotas."""
import math
import os
import time
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from places.models import CollectorState, CrowdArea, Place, PlaceCrowdProfile, PlaceSource
from places.integrations.crowd_http import BudgetSession
from places.integrations.exceptions import ExternalAPIError, ExternalAPIConfigurationError
from places.integrations.seoul_citydata import SeoulCityClient
from places.integrations.seoul_realtime import SeoulRealtimeClient
from places.integrations.tour_api import TourAPIClient
from places.integrations.weather import WeatherClient, latest_issue
from places.integrations.holidays import HolidayClient
from .crowd_estimator import KST
from .input_sync import save_citydata, save_weather, save_event, save_calendar

LIMIT_ENV = {'seoul': 'SEOUL_DAILY_LIMIT', 'tour_api': 'TOUR_API_DAILY_LIMIT', 'kma': 'KMA_DAILY_LIMIT', 'kasi': 'HOLIDAY_DAILY_LIMIT'}
KEY_ENV = {'seoul': 'SEOUL_OPEN_API_KEY', 'tour_api': 'TOUR_API_SERVICE_KEY', 'kma': 'KMA_SERVICE_KEY', 'kasi': 'HOLIDAY_SERVICE_KEY'}


class BudgetExhausted(ExternalAPIError):
    pass


def daily_limit(provider):
    try:
        return max(0, int(os.environ.get(LIMIT_ENV[provider], '0')))
    except ValueError:
        return 0


def charge(provider, retry=False, now=None):
    now = now or timezone.now()
    limit = daily_limit(provider)
    if limit <= 0:
        raise ExternalAPIConfigurationError(f'{LIMIT_ENV[provider]} must be the approved account limit')
    day = now.astimezone(KST).date()
    with transaction.atomic():
        state, _ = CollectorState.objects.get_or_create(provider=provider, key='_budget')
        CollectorState.objects.filter(pk=state.pk).exclude(budget_date=day).update(budget_date=day, calls=0)
        cap = limit if retry else int(.8*limit)
        if not CollectorState.objects.filter(pk=state.pk, calls__lt=cap).update(calls=F('calls')+1):
            raise BudgetExhausted('Daily free API budget exhausted')


def seoul_interval(limit, count=121):
    if limit <= 0:
        raise ValueError('Approved Seoul daily limit is required')
    return 5*math.ceil(max(5, 1440*count/max(1, int(.8*limit)))/5)


def acquire_lease(now=None):
    now = now or timezone.now()
    owner = str(uuid.uuid4())
    state, _ = CollectorState.objects.get_or_create(provider='system', key='collector')
    changed = CollectorState.objects.filter(pk=state.pk).filter(Q(lease_until__isnull=True)|Q(lease_until__lte=now)).update(
        lease_until=now+timedelta(minutes=3), lease_owner=owner)
    return owner if changed else None


def release_lease(owner):
    CollectorState.objects.filter(provider='system', key='collector', lease_owner=owner).update(lease_until=None, lease_owner='')


def active_grids():
    """At least one registered grid per province, then most recently changed profiles."""
    maximum = min(100, max(0, int(os.environ.get('CROWD_WEATHER_MAX_GRIDS', '100'))), int(.8*daily_limit('kma')/56))
    if maximum <= 0:
        return []
    rows = list(PlaceCrowdProfile.objects.exclude(grid_x=None).exclude(grid_y=None).select_related('place').order_by('-last_requested_at', '-updated_at'))
    selected, provinces = [], set()
    for row in rows:
        province = row.place.region_code.split('-')[0]
        grid = (row.grid_x, row.grid_y)
        if province not in provinces:
            provinces.add(province)
            if grid not in selected:
                selected.append(grid)
    for row in rows:
        grid = (row.grid_x, row.grid_y)
        if grid not in selected:
            selected.append(grid)
        if len(selected) >= maximum:
            break
    return selected[:maximum]


def _due(provider, key, now):
    state, _ = CollectorState.objects.get_or_create(provider=provider, key=key)
    if state.next_run_at and state.next_run_at > now:
        return None
    return state


def run_once(*, max_seconds=45, provider_filter=None):
    now = timezone.now()
    owner = acquire_lease(now)
    if not owner:
        return {'status': 'already_running', 'completed': 0, 'failed': 0}
    report = {'status': 'ok', 'completed': 0, 'failed': 0, 'skipped': []}
    deadline = time.monotonic()+max_seconds
    sessions = {}
    try:
        for provider in LIMIT_ENV:
            if provider_filter and provider != provider_filter:
                continue
            if not os.environ.get(KEY_ENV[provider]) or daily_limit(provider) <= 0:
                report['skipped'].append(provider+': key or approved quota missing')
                continue
            sessions[provider] = BudgetSession(lambda retry=False, p=provider: charge(p, retry))
        jobs = [('system', 'refresh', 300, None), ('system', 'baseline', 86400, None)]
        if 'seoul' in sessions:
            areas = list(CrowdArea.objects.filter(source='seoul_realtime').order_by('external_id'))
            interval = seoul_interval(daily_limit('seoul'), len(areas))
            for i, area in enumerate(areas):
                state, created = CollectorState.objects.get_or_create(provider='seoul', key=area.external_id,
                    defaults={'next_run_at': now+timedelta(seconds=i*interval*60/max(1,len(areas)))})
                jobs.append(('seoul', area.external_id, interval*60, area))
        if 'tour_api' in sessions:
            jobs.extend([('tour_api', 'poi', 86400, None), ('tour_api', 'events', 21600, None),
                         ('tour_api', 'full_poi', 604800, None), ('tour_api', 'details', 3600, None),
                         ('tour_api', 'event_details', 3600, None)])
        if 'kma' in sessions:
            for grid in active_grids():
                for product in ('getUltraSrtNcst', 'getUltraSrtFcst', 'getVilageFcst'):
                    issue = latest_issue(product, now)
                    jobs.append(('kma', f'{grid[0]},{grid[1]}:{product}', 60, (grid, product, issue)))
        if 'kasi' in sessions:
            for year in (now.astimezone(KST).year, now.astimezone(KST).year+1):
                for month in range(1,13):
                    jobs.append(('kasi', f'{year}-{month:02}', 86400 if month in (now.month, now.month%12+1) else 604800, (year, month)))
        # Oldest due work first, so one provider cannot starve all others.
        states = {(s.provider, s.key): s for s in CollectorState.objects.exclude(key__startswith='_')}
        jobs.sort(key=lambda j: (states.get((j[0],j[1])).next_run_at or now-timedelta(days=1)) if states.get((j[0],j[1])) else now-timedelta(days=1))
        blocked = set()
        for provider, key, interval, arg in jobs:
            if time.monotonic() >= deadline:
                break
            if provider in blocked:
                continue
            state = _due(provider, key, now)
            if not state:
                continue
            health, _ = CollectorState.objects.get_or_create(provider=provider, key='_health')
            if health.next_run_at and health.next_run_at > now:
                continue
            state.next_run_at = now+timedelta(seconds=interval)
            try:
                complete = _execute(provider, key, arg, sessions.get(provider), state, now, lease_owner=owner)
                state.failures, state.last_error = 0, ''
                if complete:
                    state.last_success_at = now
                else:
                    state.next_run_at = now+timedelta(seconds=1)
                health.failures, health.next_run_at = 0, None
                report['completed'] += 1
            except BudgetExhausted:
                blocked.add(provider)
                state.next_run_at = (now.astimezone(KST)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
                state.last_error = 'budget_exhausted'
            except (ExternalAPIError, ValueError, KeyError, TypeError) as error:
                state.failures += 1
                state.last_error = type(error).__name__  # Never persist key-bearing provider messages.
                state.next_run_at = now+timedelta(seconds=min(900, 60*2**min(4,state.failures-1)))
                if getattr(error, 'retry_after', 0):
                    state.next_run_at = max(state.next_run_at, now+timedelta(seconds=error.retry_after))
                    health.next_run_at = state.next_run_at
                    blocked.add(provider)
                health.failures += 1
                if health.failures >= 5:
                    health.next_run_at = max(health.next_run_at or now, now+timedelta(minutes=15))
                    blocked.add(provider)
                report['failed'] += 1
            state.save()
            health.save()
            CollectorState.objects.filter(provider='system', key='collector', lease_owner=owner).update(lease_until=timezone.now()+timedelta(minutes=3))
    finally:
        for session in sessions.values():
            session.close()
        release_lease(owner)
    return report


def _execute(provider, key, arg, session, state, now, *, lease_owner=None):
    if provider == 'system' and key == 'baseline':
        from .crowd_baseline import rebuild_baselines, prune_evidence
        from .crowd_evaluation import evaluate_forecasts
        at = now.astimezone(KST).replace(hour=4, minute=10, second=0, microsecond=0)
        if now >= at:
            rebuild_baselines(now, heartbeat=lambda: CollectorState.objects.filter(provider='system', key='collector', lease_owner=lease_owner).update(
                lease_until=timezone.now()+timedelta(minutes=3)))
            evaluate_forecasts(now)
            prune_evidence(now)
            at += timedelta(days=1)
        state.next_run_at = at
    elif provider == 'system' and key == 'refresh':
        from .crowd_inputs import estimates_for
        batch = list(Place.objects.filter(Q(crowd_area_mappings__verified=True) |
            Q(crowd_profile__last_requested_at__gte=now-timedelta(days=7))).filter(pk__gt=state.cursor.get('last_id',0)).distinct().order_by('id')[:100])
        estimates_for(batch, now, persist=True)
        if len(batch) == 100:
            state.cursor = {'last_id':batch[-1].pk}
            return False
        state.cursor = {}
    elif provider == 'seoul':
        population, transit = SeoulCityClient(session).fetch(arg.external_id, now)
        if population is None:
            try:
                session.use_reserve = True
                population = SeoulRealtimeClient(session=session).fetch_population(arg.external_id)
                population.raw_data['_provider'] = 'seoul_population'
            except ExternalAPIError:
                pass
            finally:
                session.use_reserve = False
        save_citydata(arg, population, transit, now)
    elif provider == 'kma':
        grid, product, issue = arg
        if state.cursor.get('issue') == issue.isoformat():
            return True
        rows = WeatherClient(session).fetch(product, grid, issue)
        save_weather(grid, product, issue, rows, now)
        state.cursor = {'issue': issue.isoformat()}
    elif provider == 'kasi':
        holidays = HolidayClient(session).fetch(*arg)
        save_calendar(*arg, holidays, now)
    elif key == 'events':
        page = state.cursor.get('page', 1)
        items, total = TourAPIClient(session=session).fetch_events_page(page_number=page)
        expected = min(100, max(0,total-(page-1)*100))
        if len(items) < expected:
            raise ExternalAPIError('Incomplete event page')
        invalid = state.cursor.get('invalid', 0)
        for item in items:
            invalid += int(not save_event(item, now))
        if page*100 < total:
            if not items:
                raise ExternalAPIError('Incomplete event pagination')
            state.cursor = {'page': page+1, 'invalid':invalid, 'seen':state.cursor.get('seen',0)+len(items)}
            return False
        state.cursor = {'coverage': max(0, 1-invalid/max(1,total))}
    elif key in ('poi', 'full_poi'):
        from .tour_sync import TourPlaceSyncService
        from .place_resolver import resolve_places
        page_no = state.cursor.get('page', 1)
        started = state.cursor.get('started_at', now.isoformat())
        since = state.cursor.get('since')
        if page_no == 1 and key == 'poi' and state.last_success_at:
            from django.utils.dateparse import parse_datetime
            watermark = parse_datetime(state.cursor.get('watermark','')) or state.last_success_at
            since = (watermark-timedelta(days=1)).strftime('%Y%m%d')
        client = TourAPIClient(session=session)
        page = client.fetch_places_page(page_number=page_no, modified_since=since if key=='poi' else None)
        if page.page_number != page_no or len(page.records) < min(page.page_size,max(0,page.total_count-(page_no-1)*page.page_size)):
            raise ExternalAPIError('Incomplete POI page')
        service = TourPlaceSyncService(client)
        for record in page.records:
            service._sync_record(record)
        changed = Place.objects.filter(sources__source='tour_api', sources__external_id__in=[r.external_id for r in page.records]).prefetch_related('sources')
        resolve_places(changed)
        if page.has_next:
            if not page.records:
                raise ExternalAPIError('Incomplete POI pagination')
            state.cursor = {'page': page_no+1, 'since': since, 'started_at': started}
            return False
        state.cursor = {'watermark':started}
    elif key == 'event_details':
        # Sync-listed events also receive detail enrichment, including long-running events.
        sources = list(PlaceSource.objects.filter(source='tour_api', match_status='matched', pk__gt=state.cursor.get('last_id',0)).filter(
            Q(raw_data__contenttypeid='15')|Q(raw_data__contenttypeid=15)).order_by('id')[:5])
        client = TourAPIClient(session=session)
        for source in sources:
            record = client.fetch_place_detail(source.external_id,'15')
            save_event({**source.raw_data, **record.raw_data.get('common',{}), **record.raw_data.get('intro',{}),
                        'contentid':source.external_id}, now)
        state.cursor = {'last_id':sources[-1].pk} if len(sources)==5 else {}
    elif key == 'details':
        from .tour_detail_sync import TourPlaceDetailSyncService
        # Small progressive enrichment; run through the existing verified service.
        client = TourAPIClient(session=session)
        sources = PlaceSource.objects.filter(source='tour_api', match_status='matched', place__info__isnull=True).order_by('id')[:5]
        TourPlaceDetailSyncService(client).sync(sources)
    return True
