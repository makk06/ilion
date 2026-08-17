import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote

from .exceptions import ExternalAPIConfigurationError, ExternalAPIError
from .http import DEFAULT_TIMEOUT_SECONDS, build_retrying_session, get_json


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

    def fetch_places_page(
        self,
        *,
        page_number=1,
        page_size=100,
        modified_since=None,
        region_code=None,
    ):
        params = {
            'serviceKey': self.service_key,
            'MobileOS': 'ETC',
            'MobileApp': 'ILION',
            '_type': 'json',
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

    @staticmethod
    def _parse_page(payload):
        response = payload.get('response')
        if not isinstance(response, dict):
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
