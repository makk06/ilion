import calendar
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from shapely.geometry import shape

from places.models import CalendarDay, CrowdArea, CrowdData, TourEvent, TransitObservation, WeatherSnapshot
from places.integrations.exceptions import ExternalAPIError
from places.integrations.weather import weather_grid
from .crowd_estimator import KST, event_effect, weather_effect


def observation_context(area, at):
    if not area.geometry:
        return {}
    center = shape(area.geometry).representative_point()
    gx, gy = weather_grid(center.y, center.x)
    weather = WeatherSnapshot.objects.filter(grid_x=gx, grid_y=gy, issued_at__lte=at,
        issued_at__gte=at-timedelta(hours=4), valid_at__lte=at, fetched_at__lte=at).order_by('-valid_at', '-issued_at').first()
    context = {}
    if weather:
        for profile in ('day_visit', 'park', 'beach', 'shopping', 'food', 'unknown'):
            context['weather_'+profile] = weather_effect(profile, 'indoor' if profile == 'shopping' else 'outdoor', weather.values)[0]
    # Event context is stored when observed, never reconstructed from future edits.
    events = list(TourEvent.objects.filter(active=True, start_date__lte=at.date(), end_date__gte=at.date(), fetched_at__lte=at).values())
    from places.models import CollectorState
    state = CollectorState.objects.filter(provider='tour_api', key='events', last_success_at__lte=at).first()
    if state and state.last_success_at:
        context['event'] = event_effect(events, center.y, center.x, at)
    return context


def save_citydata(area, population, transit, now):
    if population and (population.observed_at > now or population.population_min is None
            or population.population_max is None or not 0 <= population.population_min <= population.population_max):
        population = None
    if population:
        latest = CrowdData.objects.filter(crowd_area=area).order_by('-observed_at').first()
        if not latest or population.observed_at >= latest.observed_at:
            raw = {k: population.raw_data.get(k) for k in ('AREA_CD', 'AREA_NM', 'PPLTN_TIME', 'AREA_CONGEST_LVL', 'REPLACE_YN')}
            raw['_provider'] = population.raw_data.get('_provider', 'citydata')
            raw['_context'] = observation_context(area, population.observed_at)
            # Same source timestamp is one observation; refetch does not reset age.
            CrowdData.objects.get_or_create(crowd_area=area, observed_at=population.observed_at,
                defaults={'population_min': population.population_min, 'population_max': population.population_max,
                    'crowd_level': population.crowd_level, 'crowd_message': population.crowd_message,
                    'is_replaced': population.is_replaced, 'fetched_at': now, 'raw_data': raw})
    for data in transit:
        latest = TransitObservation.objects.filter(crowd_area=area, mode=data['mode']).order_by('-observed_at').first()
        if latest and (latest.observed_at >= data['observed_at'] or (
                data['timestamp_quality'] == 'collection_only' and latest.fingerprint == data['fingerprint'])):
            continue
        TransitObservation.objects.get_or_create(crowd_area=area, mode=data['mode'], window_minutes=30,
            observed_at=data['observed_at'], defaults={k: v for k, v in {**data, 'fetched_at': now}.items() if k not in ('mode', 'observed_at')})


def save_weather(grid, product, issue, rows, now):
    with transaction.atomic():
        for at, values in rows.items():
            WeatherSnapshot.objects.get_or_create(grid_x=grid[0], grid_y=grid[1], product=product,
                issued_at=issue, valid_at=at, defaults={'fetched_at': now, 'values': values})


def save_event(item, now):
    try:
        external_id = str(item['contentid'])
        start = datetime.strptime(str(item['eventstartdate']), '%Y%m%d').date()
        end = datetime.strptime(str(item['eventenddate']), '%Y%m%d').date()
        lat, lon = float(item['mapy']), float(item['mapx'])
        if start > end or not 33 <= lat <= 39 or not 124 <= lon <= 132:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        return False
    resets = {}
    old = TourEvent.objects.filter(external_id=external_id).first()
    if old and (old.start_date != start or old.end_date != end):
        resets = {'starts_at':None,'ends_at':None,'time_quality':'date_only'}
    TourEvent.objects.update_or_create(external_id=external_id, defaults={**resets, 'name': str(item.get('title', ''))[:255],
        'latitude': lat, 'longitude': lon, 'start_date': start, 'end_date': end,
        'raw_data': item, 'fetched_at': now, 'active': str(item.get('showflag', '1')) != '0'})
    return True


def save_calendar(year, month, holidays, now):
    with transaction.atomic():
        for day in range(1, calendar.monthrange(year, month)[1]+1):
            date = datetime(year, month, day).date()
            CalendarDay.objects.update_or_create(date=date, defaults={
                'is_holiday': date in holidays, 'name': holidays.get(date, ''), 'fetched_at': now})
        rows = list(CalendarDay.objects.order_by('date'))
        run = []
        for row in rows + [None]:
            free = row and (row.is_holiday or row.date.weekday() >= 5)
            contiguous = not run or (row and row.date-run[-1].date == timedelta(days=1))
            if run and (not free or not contiguous):
                for member in run:
                    member.holiday_run = len(run)
                CalendarDay.objects.bulk_update(run, ['holiday_run'])
                run = []
            if free:
                run.append(row)
            elif row and row.holiday_run:
                CalendarDay.objects.filter(pk=row.pk).update(holiday_run=0)
