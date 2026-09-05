import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import unescape
from urllib.parse import unquote, urlparse

from .exceptions import ExternalAPIConfigurationError, ExternalAPIError
from .http import (
    DEFAULT_TIMEOUT_SECONDS,
    build_retrying_session,
    extract_error_detail,
    get_json,
)


CONTENT_TYPE_NAMES = {
    '12': '관광지',
    '14': '문화시설',
    '15': '축제/공연/행사',
    '25': '여행코스',
    '28': '레포츠',
    '32': '숙박',
    '38': '쇼핑',
    '39': '음식점',
}

OPENING_HOUR_KEYS = (
    'usetime',
    'usetimeculture',
    'usetimefestival',
    'usetimeleports',
    'opentime',
    'opentimefood',
    'checkintime',
)
HOLIDAY_INFO_KEYS = (
    'restdate',
    'restdateculture',
    'restdateleports',
    'restdateshopping',
    'restdatefood',
)
INFO_CENTER_KEYS = (
    'infocenter',
    'infocenterculture',
    'infocenterleports',
    'infocentershopping',
    'infocenterfood',
    'infocenterlodging',
)


def _value(data, *keys, default=''):
    for key in keys:
        value = data.get(key)
        if value not in (None, ''):
            return value
    return default


def _text(data, *keys):
    value = _value(data, *keys)
    return str(value).strip() if value not in (None, '') else ''


def _decimal(data, *keys):
    value = _value(data, *keys, default=None)
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _plain_text(value):
    if value in (None, ''):
        return ''
    text = str(value)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</p\s*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text).replace('\r', '')
    return '\n'.join(line.strip() for line in text.split('\n') if line.strip())


def _http_url(value):
    if value in (None, ''):
        return ''
    raw = unescape(str(value)).strip()
    match = re.search(r'''(?i)href=["']([^"']+)["']''', raw)
    candidate = match.group(1).strip() if match else _plain_text(raw)
    parsed = urlparse(candidate)
    return candidate if parsed.scheme in {'http', 'https'} and parsed.netloc else ''


def _first_text(data, keys):
    return next((_plain_text(data.get(key)) for key in keys if data.get(key)), '')


@dataclass(frozen=True)
class TourPlaceRecord:
    external_id: str
    name: str
    category: str
    subcategory: str
    region_code: str
    address: str
    latitude: Decimal | None
    longitude: Decimal | None
    source_category: str
    is_active: bool
    raw_data: dict

    @property
    def can_create_place(self):
        return all(
            (
                self.external_id,
                self.name,
                self.category,
                self.region_code,
                self.address,
                self.latitude is not None,
                self.longitude is not None,
            )
        ) and -90 <= self.latitude <= 90 and -180 <= self.longitude <= 180


@dataclass(frozen=True)
class TourAPIPage:
    records: list[TourPlaceRecord]
    page_number: int
    page_size: int
    total_count: int

    @property
    def has_next(self):
        return self.page_number * self.page_size < self.total_count


@dataclass(frozen=True)
class TourPlaceDetailRecord:
    external_id: str
    content_type_id: str
    description: str
    phone: str
    homepage_url: str
    first_image_url: str
    opening_hours: str
    holiday_info: str
    raw_data: dict


def normalize_tour_place_detail(common_item, intro_item=None):
    intro_item = intro_item or {}
    return TourPlaceDetailRecord(
        external_id=_text(common_item, 'contentid', 'contentId')
        or _text(intro_item, 'contentid', 'contentId'),
        content_type_id=_text(common_item, 'contenttypeid', 'contentTypeId')
        or _text(intro_item, 'contenttypeid', 'contentTypeId'),
        description=_plain_text(_value(common_item, 'overview')),
        phone=_plain_text(_value(common_item, 'tel'))
        or _first_text(intro_item, INFO_CENTER_KEYS),
        homepage_url=_http_url(_value(common_item, 'homepage')),
        first_image_url=_http_url(
            _value(common_item, 'firstimage', 'firstImage')
        ),
        opening_hours=_first_text(intro_item, OPENING_HOUR_KEYS),
        holiday_info=_first_text(intro_item, HOLIDAY_INFO_KEYS),
        raw_data={'common': common_item, 'intro': intro_item},
    )


def _response_items(payload):
    response = payload.get('response')
    if not isinstance(response, dict):
        detail = extract_error_detail(payload)
        if detail:
            raise ExternalAPIError(f'TourAPI error response: {detail}')
        raise ExternalAPIError('TourAPI returned an invalid response structure')

    header = response.get('header') or {}
    result_code = str(header.get('resultCode', ''))
    if result_code != '0000':
        message = str(header.get('resultMsg') or 'unknown error')
        raise ExternalAPIError(f'TourAPI error {result_code}: {message}')

    body = response.get('body') or {}
    item_container = body.get('items') or {}
    items = item_container.get('item', []) if isinstance(item_container, dict) else []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []
    return body, [item for item in items if isinstance(item, dict)]


def normalize_tour_place(item):
    content_type_id = _text(item, 'contentid', 'contentId')
    type_id = _text(item, 'contenttypeid', 'contentTypeId')
    region = _text(item, 'lDongRegnCd', 'ldongregncd', 'areaCode', 'areacode')
    district = _text(
        item,
        'lDongSignguCd',
        'ldongsigungucd',
        'sigunguCode',
        'sigungucode',
    )
    region_code = '-'.join(part for part in (region, district) if part)
    class_codes = [
        _text(item, 'lclsSystm1', 'lclssystm1', 'cat1'),
        _text(item, 'lclsSystm2', 'lclssystm2', 'cat2'),
        _text(item, 'lclsSystm3', 'lclssystm3', 'cat3'),
    ]
    source_category = '/'.join(code for code in class_codes if code) or type_id
    address = ' '.join(
        part for part in (_text(item, 'addr1'), _text(item, 'addr2')) if part
    )
    show_flag = _text(item, 'showflag', 'showFlag')

    return TourPlaceRecord(
        external_id=content_type_id,
        name=_text(item, 'title'),
        category=CONTENT_TYPE_NAMES.get(type_id, '기타'),
        subcategory=class_codes[-1] or class_codes[-2] or '',
        region_code=region_code,
        address=address,
        latitude=_decimal(item, 'mapy', 'mapY'),
        longitude=_decimal(item, 'mapx', 'mapX'),
        source_category=source_category,
        is_active=show_flag not in {'0', 'N', 'n', 'false', 'False'},
        raw_data=item,
    )


class TourAPIClient:
    base_url = 'https://apis.data.go.kr/B551011/KorService2'

    def __init__(self, service_key=None, *, session=None, timeout=None):
        configured_key = service_key or os.environ.get('TOUR_API_SERVICE_KEY', '')
        self.service_key = unquote(configured_key)
        if not self.service_key:
            raise ExternalAPIConfigurationError(
                'TOUR_API_SERVICE_KEY is not configured'
            )
        self.session = session or build_retrying_session()
        self.timeout = timeout or DEFAULT_TIMEOUT_SECONDS

    def _base_params(self):
        return {
            'serviceKey': self.service_key,
            'MobileOS': 'ETC',
            'MobileApp': 'ILION',
            '_type': 'json',
        }

    def fetch_places_page(
        self,
        *,
        page_number=1,
        page_size=100,
        modified_since=None,
        region_code=None,
    ):
        params = {
            **self._base_params(),
            'arrange': 'C',
            'pageNo': page_number,
            'numOfRows': page_size,
        }
        if modified_since:
            params['modifiedtime'] = modified_since
        if region_code:
            params['lDongRegnCd'] = region_code

        payload = get_json(
            self.session,
            f'{self.base_url}/areaBasedSyncList2',
            params=params,
            timeout=self.timeout,
            provider='TourAPI',
        )
        return self._parse_page(payload)

    def fetch_place_detail(self, content_id, content_type_id, *, include_intro=True):
        common_params = {
            **self._base_params(),
            'contentId': content_id,
        }
        common_payload = get_json(
            self.session,
            f'{self.base_url}/detailCommon2',
            params=common_params,
            timeout=self.timeout,
            provider='TourAPI',
        )
        _, common_items = _response_items(common_payload)
        common_item = common_items[0] if common_items else {}

        intro_item = {}
        if include_intro:
            intro_payload = get_json(
                self.session,
                f'{self.base_url}/detailIntro2',
                params={
                    **self._base_params(),
                    'contentId': content_id,
                    'contentTypeId': content_type_id,
                },
                timeout=self.timeout,
                provider='TourAPI',
            )
            _, intro_items = _response_items(intro_payload)
            intro_item = intro_items[0] if intro_items else {}

        if not common_item and not intro_item:
            raise ExternalAPIError(
                f'TourAPI returned no detail for content {content_id}'
            )
        return normalize_tour_place_detail(common_item, intro_item)

    @staticmethod
    def _parse_page(payload):
        body, items = _response_items(payload)

        records = [
            normalize_tour_place(item)
            for item in items
            if isinstance(item, dict) and _text(item, 'contentid', 'contentId')
        ]
        return TourAPIPage(
            records=records,
            page_number=_integer(body.get('pageNo'), 1),
            page_size=_integer(body.get('numOfRows'), max(len(records), 1)),
            total_count=_integer(body.get('totalCount'), len(records)),
        )
