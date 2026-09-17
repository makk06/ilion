"""Only TMAP type=1 place density is a valid observation. No level-to-count mapping."""
import math
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from .exceptions import ExternalAPIError, ExternalAPIConfigurationError


def normalize(payload, poi):
    try:
        contents = payload['contents']
        if str(payload['status']['code']) != '00' or str(contents['poiId']) != str(poi):
            raise ValueError()
        rows = [r for r in contents['rltm'] if r.get('type') == 1]
        if len(rows) != 1:
            raise ValueError()
        row = rows[0]
        value = row['congestion']
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError()
        at = datetime.strptime(row['datetime'], '%Y%m%d%H%M%S').replace(tzinfo=timezone(timedelta(hours=9)))
        return {'observed_at': at, 'value': value, 'details': {'type': 1, 'level': row.get('congestionLevel')}}
    except (KeyError, TypeError, ValueError):
        raise ExternalAPIError('Invalid TMAP place-density response') from None


class TmapDensityClient:
    def __init__(self, session):
        self.session = session
        self.key = os.environ.get('TMAP_APP_KEY')
        if not self.key:
            raise ExternalAPIConfigurationError('TMAP_APP_KEY not configured')

    def get(self, path, params=None):
        response = self.session.get('https://apis.openapi.sk.com/tmap/' + path,
                                    headers={'appKey': self.key, 'Accept': 'application/json'}, params=params)
        if response.status_code != 200:
            raise ExternalAPIError('TMAP request rejected')
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError()
            return payload
        except ValueError:
            raise ExternalAPIError('Invalid TMAP JSON') from None

    def fetch(self, poi):
        raw = self.get('puzzle/pois/' + quote(str(poi), safe=''))
        return normalize(raw, poi), raw

    def search(self, name):
        payload = self.get('pois', {'version': 1, 'searchKeyword': name, 'count': 100})
        return payload.get('searchPoiInfo', {}).get('pois', {}).get('poi', [])
