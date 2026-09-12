import math
from datetime import datetime, timedelta
from urllib.parse import unquote

from .crowd_http import required_key
from .http import get_json
from .exceptions import ExternalAPIError
from places.services.crowd_estimator import KST

BASE_URL = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0'
FIELDS = {'T1H': 'temperature', 'TMP': 'temperature', 'PTY': 'precipitation_type',
          'REH': 'humidity', 'WSD': 'wind_speed', 'SKY': 'sky', 'POP': 'precipitation_probability',
          'RN1': 'precipitation_mm'}


def weather_grid(latitude, longitude):
    """KMA DFS Lambert conformal grid (official constants), WGS84 input."""
    re = 6371.00877 / 5
    rad = math.pi / 180
    slat1, slat2 = 30*rad, 60*rad
    sn = math.log(math.cos(slat1)/math.cos(slat2)) / math.log(math.tan(math.pi/4+slat2/2)/math.tan(math.pi/4+slat1/2))
    sf = math.tan(math.pi/4+slat1/2)**sn * math.cos(slat1)/sn
    ro = re*sf/math.tan(math.pi/4+38*rad/2)**sn
    ra = re*sf/math.tan(math.pi/4+latitude*rad/2)**sn
    theta = ((longitude-126+180) % 360 - 180)*rad*sn
    return math.floor(ra*math.sin(theta)+43+.5), math.floor(ro-ra*math.cos(theta)+136+.5)


def latest_issue(product, now):
    local = now.astimezone(KST)
    if product == 'getUltraSrtNcst':
        return (local-timedelta(minutes=12)).replace(minute=0, second=0, microsecond=0)
    if product == 'getUltraSrtFcst':
        return (local-timedelta(minutes=47)).replace(minute=30, second=0, microsecond=0)
    if product != 'getVilageFcst':
        raise ValueError('Unsupported weather product')
    available = local-timedelta(minutes=15)
    candidates = [available.replace(hour=h, minute=0, second=0, microsecond=0) for h in (2, 5, 8, 11, 14, 17, 20, 23)]
    return max([c for c in candidates if c <= available] or [(available-timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0)])


def parse_weather(items, product, issue):
    grouped = {}
    for item in items:
        try:
            at = issue if product == 'getUltraSrtNcst' else datetime.strptime(str(item['fcstDate'])+str(item['fcstTime']), '%Y%m%d%H%M').replace(tzinfo=KST)
            code = item['category']
            raw = item.get('obsrValue', item.get('fcstValue'))
            if code not in FIELDS:
                continue
            value = float(raw)
            if not math.isfinite(value) or value <= -900:
                continue
            if code in ('PTY', 'SKY') and value < 0:
                continue
            if code == 'PTY' and value not in (0,1,2,3,4,5,6,7):
                continue
            if code == 'SKY' and value not in (1,3,4):
                continue
            if code in ('REH','POP') and not 0 <= value <= 100:
                continue
            if code in ('WSD','RN1') and value < 0:
                continue
            if code in ('T1H','TMP') and not -60 <= value <= 60:
                continue
            grouped.setdefault(at, {})[FIELDS[code]] = value
        except (ValueError, TypeError, KeyError):
            continue
    return grouped


class WeatherClient:
    def __init__(self, session, service_key=None):
        self.session = session
        self.key = unquote(service_key or required_key('KMA_SERVICE_KEY'))

    def fetch(self, product, grid, issue):
        items, page = [], 1
        while True:
            payload = get_json(self.session, f'{BASE_URL}/{product}', provider='KMA', params={
                'serviceKey': self.key, 'dataType': 'JSON', 'numOfRows': 1000, 'pageNo': page,
                'base_date': issue.strftime('%Y%m%d'), 'base_time': issue.strftime('%H%M'), 'nx': grid[0], 'ny': grid[1]})
            response = payload.get('response', {})
            if str(response.get('header', {}).get('resultCode')) not in ('0', '00', '0000'):
                raise ExternalAPIError('KMA application error')
            body = response.get('body', {})
            batch = (body.get('items') or {}).get('item', [])
            if isinstance(batch, dict):
                batch = [batch]
            items.extend(batch)
            if len(items) >= int(body.get('totalCount', 0)):
                break
            if not batch or page >= 10:
                raise ExternalAPIError('Incomplete KMA pagination')
            page += 1
        result = parse_weather(items, product, issue)
        if not result:
            raise ExternalAPIError('KMA returned no usable weather')
        return result
