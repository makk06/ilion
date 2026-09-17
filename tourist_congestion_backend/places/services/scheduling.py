"""Durable production schedules. Only the single data worker calls this module."""
import os
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from places.catalog import load_seoul_crowd_catalog
from places.models import DataJob, ExternalSource, PlaceSource
from places.services.jobs import enqueue
from places.services.seoul_mapping import SeoulPlaceMappingService
from places.services.weather import grid_for, latest_available_issue

ACTIVE = ('pending', 'running')
# Public city centres, not user location history. Ensure a fresh DB has weather.
CITY_CENTRES = ((37.5665, 126.9780), (35.1796, 129.0756), (33.4996, 126.5312),
                (36.3504, 127.3845), (35.8714, 128.6014), (35.1595, 126.8526),
                (37.7519, 128.8761))


def integer(name, default, minimum, maximum):
    value = int(os.environ.get(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(name + ' is outside its supported range')
    return value


def enabled(key, limit):
    return bool(os.environ.get(key, '').strip()) and int(os.environ.get(limit, '0')) != 0


def schedule(now=None):
    now = timezone.localtime(now or timezone.now())
    catalog = load_seoul_crowd_catalog()
    if enabled('TOUR_API_SERVICE_KEY', 'TOUR_API_DAILY_LIMIT'):
        schedule_tour(now)
    if enabled('SEOUL_OPEN_API_KEY', 'SEOUL_DAILY_LIMIT'):
        window = now.strftime('%Y%m%d%H') + str(now.minute // 15)
        for area in catalog.areas:
            enqueue('seoul_crowd', area.external_id, window=window)
    # Pure DB/catalog operation: also repairs mappings after either initial sync.
    SeoulPlaceMappingService().apply(catalog.mappings)
    if enabled('KMA_SERVICE_KEY', 'KMA_DAILY_LIMIT'):
        maximum = integer('WEATHER_REGULAR_GRIDS', 35, 7, 100)
        grids = {grid_for(*point) for point in CITY_CENTRES}
        recent = DataJob.objects.filter(kind='weather', created_at__gte=now - timedelta(days=7))
        # Exclude scheduler-generated rows so popular/requested grids don't starve.
        recent = recent.exclude(target_key__startswith='scheduled:').order_by('-created_at')[:1000]
        for job in recent:
            grid = tuple(job.payload.get('grid') or ())
            if len(grid) == 2:
                grids.add(grid)
            if len(grids) >= maximum:
                break
        issue = latest_available_issue(now)
        for x, y in sorted(grids):
            enqueue('weather', f'scheduled:{x}:{y}',
                    payload={'grid': [x, y], 'issued_at': issue.isoformat()},
                    window=issue.strftime('%Y%m%d%H'))


def schedule_tour(now):
    today = now.strftime('%Y%m%d')
    maximum = integer('TOUR_SYNC_MAX_PAGES', 100, 1, 1000)
    lists = DataJob.objects.filter(kind='tour_places')
    last_success = lists.filter(status='succeeded').order_by('-finished_at').first()
    if not lists.filter(status__in=ACTIVE).exists():
        # First full load, then recover missed daily changes with an overlap.
        if last_success is None or (now.hour >= 3 and not lists.filter(created_at__date=now.date()).exists()):
            payload = {'page_size': 1000, 'max_pages': maximum}
            last_full = lists.filter(status='succeeded', payload__modified_since__isnull=True).order_by('-finished_at').first()
            full_due = last_full is None or (now.weekday() == 6 and now.hour >= 4 and
                                            last_full.finished_at < now - timedelta(days=6))
            if last_success is not None and not full_due:
                payload['modified_since'] = (timezone.localtime(last_success.created_at) - timedelta(days=1)).strftime('%Y%m%d')
            enqueue('tour_places', 'scheduled:full' if full_due else 'scheduled:changes',
                    payload=payload, window=today)
        # Sunday's daily incremental must not suppress the 04:00 full scan.
        if now.weekday() == 6 and now.hour >= 4 and not lists.filter(status__in=ACTIVE).exists():
            enqueue('tour_places', 'scheduled:full', payload={'page_size': 1000, 'max_pages': maximum}, window=today)
    # Do not compete with the very first catalogue load.
    if last_success is None or (now.hour, now.minute) < (4, 30):
        return
    cap = integer('TOUR_DETAIL_DAILY_PLACES', 150, 0, 200)
    details = DataJob.objects.filter(kind='tour_detail')
    used = details.filter(created_at__date=now.date()).count()
    pending = details.filter(status__in=ACTIVE).count()
    remaining = min(max(0, cap - used), max(0, cap - pending))
    if not remaining:
        return
    excluded = details.filter(Q(status__in=ACTIVE) | Q(created_at__date=now.date())).values_list('target_key', flat=True)
    sources = PlaceSource.objects.filter(source=ExternalSource.TOUR_API, match_status='matched').filter(
        Q(place__info__isnull=True) | Q(place__info__updated_at__lt=now - timedelta(days=7))
    ).exclude(pk__in=excluded).filter(
        Q(raw_data__has_key='contenttypeid') | Q(raw_data__has_key='contentTypeId')
    ).select_related('place').order_by('place__info__updated_at', 'id')[:remaining]
    for source in sources:
        enqueue('tour_detail', str(source.pk), payload={'source_id': source.pk}, window=today)
