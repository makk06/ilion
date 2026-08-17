import os
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from places.models import CrowdData

from .exceptions import ExternalAPIConfigurationError, ExternalAPIError
from .http import DEFAULT_TIMEOUT_SECONDS, build_retrying_session, get_json


CROWD_LEVELS = {
    '여유': CrowdData.CrowdLevel.RELAXED,
    '보통': CrowdData.CrowdLevel.NORMAL,
    '약간 붐빔': CrowdData.CrowdLevel.BUSY,
    '붐빔': CrowdData.CrowdLevel.CROWDED,
    'relaxed': CrowdData.CrowdLevel.RELAXED,
    'normal': CrowdData.CrowdLevel.NORMAL,
    'busy': CrowdData.CrowdLevel.BUSY,
    'crowded': CrowdData.CrowdLevel.CROWDED,
}


def _to_int(value):
    if value in (None, ''):
        return None
    try:
        return int(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _to_bool(value):
    return str(value).strip().upper() in {'Y', 'YES', 'TRUE', '1'}


def _parse_observed_at(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        for pattern in ('%Y-%m-%d %H:%M', '%Y%m%d%H%M', '%Y%m%d%H%M%S'):
            try:
                parsed = datetime.strptime(str(value), pattern)
                break
            except ValueError:
                continue
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _find_population_record(value):
    if isinstance(value, dict):
        if 'AREA_NM' in value and (
            'AREA_CD' in value or 'AREA_CONGEST_LVL' in value
        ):
            return value
        for child in value.values():
            result = _find_population_record(child)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = _find_population_record(child)
            if result is not None:
                return result
    return None


@dataclass(frozen=True)
class SeoulPopulationRecord:
    external_id: str
    name: str
    observed_at: datetime
    crowd_level: str
    crowd_message: str
    population_min: int | None
    population_max: int | None
    is_replaced: bool
    raw_data: dict


def normalize_seoul_population(payload, *, fallback_area):
    record = _find_population_record(payload)
    if record is None:
        result = payload.get('RESULT') or payload.get('result') or {}
        code = (
            result.get('RESULT.CODE')
            or result.get('CODE')
            or result.get('code')
            or 'unknown'
        )
        message = (
            result.get('RESULT.MESSAGE')
            or result.get('MESSAGE')
            or result.get('message')
            or 'no population data'
        )
        raise ExternalAPIError(f'Seoul API error {code}: {message}')

    observed_at = _parse_observed_at(record.get('PPLTN_TIME'))
    if observed_at is None:
        raise ExternalAPIError('Seoul API response is missing a valid PPLTN_TIME')

    raw_level = str(record.get('AREA_CONGEST_LVL') or '').strip()
    return SeoulPopulationRecord(
        external_id=str(record.get('AREA_CD') or fallback_area).strip(),
        name=str(record.get('AREA_NM') or fallback_area).strip(),
        observed_at=observed_at,
        crowd_level=CROWD_LEVELS.get(raw_level, CrowdData.CrowdLevel.UNKNOWN),
        crowd_message=str(record.get('AREA_CONGEST_MSG') or '').strip(),
        population_min=_to_int(record.get('AREA_PPLTN_MIN')),
        population_max=_to_int(record.get('AREA_PPLTN_MAX')),
        is_replaced=_to_bool(record.get('REPLACE_YN')),
        raw_data=record,
    )


class SeoulRealtimeClient:
    # The official service currently exposes port 8088 over HTTP only.
    base_url = 'http://openapi.seoul.go.kr:8088'

    def __init__(self, api_key=None, *, session=None, timeout=None):
        self.api_key = api_key or os.environ.get('SEOUL_OPEN_API_KEY', '')
        if not self.api_key:
            raise ExternalAPIConfigurationError('SEOUL_OPEN_API_KEY is not configured')
        self.session = session or build_retrying_session()
        self.timeout = timeout or DEFAULT_TIMEOUT_SECONDS

    def fetch_population(self, area):
        encoded_key = quote(self.api_key, safe='')
        encoded_area = quote(area, safe='')
        url = (
            f'{self.base_url}/{encoded_key}/json/citydata_ppltn/1/5/'
            f'{encoded_area}'
        )
        payload = get_json(
            self.session,
            url,
            timeout=self.timeout,
            provider='Seoul real-time population API',
        )
        return normalize_seoul_population(payload, fallback_area=area)
