import math
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import unquote

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from places.integrations.exceptions import ExternalAPIAuthError, ExternalAPIConfigurationError, ExternalAPIError, ExternalAPIQuotaError
from places.integrations.http import get_json
from places.models import WeatherForecast


KST = dt_timezone(timedelta(hours=9))
ISSUE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
SUPPORTED_CATEGORIES = {'PTY', 'TMP', 'WSD'}


def grid_for(latitude, longitude):
    """KMA 5 km Lambert grid; reject coordinates outside the published converter range."""
    lat, lon = float(latitude), float(longitude)
    if not 31.651814 <= lat <= 43.393490 or not 123.310165 <= lon <= 132.774963:
        return None
    rad = math.pi / 180
    slat1, slat2, olat, olon = [v * rad for v in (30, 60, 38, 126)]
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(
        math.tan(math.pi / 4 + slat2 / 2) / math.tan(math.pi / 4 + slat1 / 2))
    sf = math.tan(math.pi / 4 + slat1 / 2) ** sn * math.cos(slat1) / sn
    ro = 6371.00877 / 5 * sf / math.tan(math.pi / 4 + olat / 2) ** sn
    ra = 6371.00877 / 5 * sf / math.tan(math.pi / 4 + lat * rad / 2) ** sn
    theta = (lon * rad - olon) * sn
    x = int(math.floor(ra * math.sin(theta) + 43 + 0.5))
    y = int(math.floor(ro - ra * math.cos(theta) + 136 + 0.5))
    return (x, y) if 1 <= x <= 149 and 1 <= y <= 253 else None


def latest_available_issue(now, target_at=None):
    local = now.astimezone(KST)
    target_hour = (target_at.replace(minute=0, second=0, microsecond=0)
                   if target_at is not None else None)
    for day_offset in (0, -1):
        date = (local + timedelta(days=day_offset)).date()
        for hour in reversed(ISSUE_HOURS):
            issue = datetime.combine(date, datetime.min.time(), KST).replace(hour=hour)
            if issue + timedelta(minutes=10) <= local and (
                target_hour is None or issue + timedelta(hours=1) <= target_hour
            ):
                return issue.astimezone(dt_timezone.utc)
    raise ValueError('No available forecast issuance covers the target hour')


def parse_forecast_page(payload, grid, issue):
    response = payload.get('response')
    if not isinstance(response, dict):
        raise ExternalAPIError('KMA returned an error or invalid response')
    result_code = str((response.get('header') or {}).get('resultCode'))
    if result_code in {'20', '30', '31', '32'}:
        raise ExternalAPIAuthError(f'KMA rejected credentials (code {result_code})')
    if result_code == '22':
        raise ExternalAPIQuotaError('KMA call quota exceeded')
    if result_code != '00':
        raise ExternalAPIError('KMA returned an error or invalid response')
    body = response.get('body') or {}
    items = (body.get('items') or {}).get('item') or []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise ExternalAPIError('KMA returned invalid forecast items')
    checked = []
    for item in items:
        if not isinstance(item, dict):
            raise ExternalAPIError('KMA returned invalid forecast item')
        if (str(item.get('baseDate')), str(item.get('baseTime'))) != (
            issue.astimezone(KST).strftime('%Y%m%d'), issue.astimezone(KST).strftime('%H%M')):
            raise ExternalAPIError('KMA issuance does not match request')
        try:
            response_grid = (int(item.get('nx', -1)), int(item.get('ny', -1)))
        except (TypeError, ValueError):
            raise ExternalAPIError('KMA grid is invalid') from None
        if response_grid != grid:
            raise ExternalAPIError('KMA grid does not match request')
        try:
            target = datetime.strptime(str(item['fcstDate']) + str(item['fcstTime']), '%Y%m%d%H%M').replace(tzinfo=KST)
        except (KeyError, ValueError):
            raise ExternalAPIError('KMA target time is invalid') from None
        checked.append((target.astimezone(dt_timezone.utc), str(item.get('category')), item.get('fcstValue')))
    return checked, int(body.get('totalCount') or len(items))


class KMAForecastClient:
    url = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst'

    def __init__(self, service_key=None, session=None):
        self.service_key = unquote(service_key or os.environ.get('KMA_SERVICE_KEY', ''))
        if not self.service_key:
            raise ExternalAPIConfigurationError('KMA_SERVICE_KEY is not configured')
        if session is None:
            import requests
            session = requests.Session()
        self.session = session

    def fetch(self, grid, issue, before_call):
        rows = []
        page = 1
        while True:
            before_call()
            payload = get_json(self.session, self.url, params={
                'serviceKey': self.service_key, 'pageNo': page, 'numOfRows': 1000,
                'dataType': 'JSON', 'base_date': issue.astimezone(KST).strftime('%Y%m%d'),
                'base_time': issue.astimezone(KST).strftime('%H%M'),
                'nx': grid[0], 'ny': grid[1],
            }, provider='KMA')
            batch, total = parse_forecast_page(payload, grid, issue)
            if not batch:
                raise ExternalAPIError('KMA returned an empty forecast page')
            rows.extend(batch)
            if len(rows) >= total:
                return rows
            page += 1


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


@transaction.atomic
def save_forecast(grid, issue, rows):
    grouped = defaultdict(dict)
    for target, category, value in rows:
        if category in SUPPORTED_CATEGORIES:
            grouped[target][category] = value
    if not grouped:
        raise ExternalAPIError('KMA forecast contains no supported categories')
    for target, values in grouped.items():
        pty = _number(values.get('PTY'))
        WeatherForecast.objects.update_or_create(
            source='kma_vilage', grid_x=grid[0], grid_y=grid[1],
            issued_at=issue, target_at=target,
            defaults={
                'precipitation_type': int(pty) if pty is not None and 0 <= pty <= 7 else None,
                'temperature_c': _number(values.get('TMP')),
                'wind_mps': _number(values.get('WSD')),
                'raw_data': values,
            },
        )
    return len(grouped)


def forecast_for(grid, visit_at, now=None):
    if grid is None:
        return None
    now = now or timezone.now()
    # A target timestamp represents the forecast hour; never stretch it across a long gap.
    lower = visit_at.replace(minute=0, second=0, microsecond=0)
    return WeatherForecast.objects.filter(
        source='kma_vilage', grid_x=grid[0], grid_y=grid[1], target_at=lower,
        issued_at__lte=now,
        issued_at__gte=now - timedelta(hours=settings.WEATHER_MAX_ISSUE_AGE_HOURS),
    ).order_by('-issued_at', '-id').first()


def forecasts_for(grids, visit_at, now=None):
    """Return the same latest forecast as ``forecast_for`` for every grid in one query."""
    requested = {tuple(grid) for grid in grids if grid is not None}
    if not requested:
        return {}
    now = now or timezone.now()
    lower = visit_at.replace(minute=0, second=0, microsecond=0)
    rows = WeatherForecast.objects.filter(
        source='kma_vilage',
        grid_x__in={grid[0] for grid in requested},
        grid_y__in={grid[1] for grid in requested},
        target_at=lower,
        issued_at__lte=now,
        issued_at__gte=now - timedelta(hours=settings.WEATHER_MAX_ISSUE_AGE_HOURS),
    ).defer('raw_data').order_by('grid_x', 'grid_y', '-issued_at', '-id')
    result = {}
    for forecast in rows:
        grid = (forecast.grid_x, forecast.grid_y)
        if grid in requested:
            result.setdefault(grid, forecast)
    return result
