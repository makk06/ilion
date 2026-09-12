import hashlib
import json
from urllib.parse import quote

from .crowd_http import get_xml, required_key
from .exceptions import ExternalAPIError
from .seoul_realtime import normalize_seoul_population, _to_int, _parse_observed_at


def normalize_citydata(root, area, fetched_at):
    if root.findtext('.//AREA_CD') != area:
        raise ExternalAPIError('Seoul response area mismatch')
    population = None
    ppl = root.find('.//LIVE_PPLTN_STTS')
    if ppl is not None:
        # Some responses wrap the record in another LIVE_PPLTN_STTS element.
        record = {e.tag: e.text for e in ppl.iter() if not list(e)}
        record.update(AREA_CD=area, AREA_NM=root.findtext('.//AREA_NM') or area)
        try:
            population = normalize_seoul_population(record, fallback_area=area)
            if population.population_min is None or population.population_max is None or not 0 <= population.population_min <= population.population_max:
                population = None
            elif population.observed_at > fetched_at:
                population = None
        except ExternalAPIError:
            population = None
    transit = []
    for mode, prefix in (('subway', 'SUB'), ('bus', 'BUS')):
        node = root.find('.//LIVE_' + prefix + '_PPLTN')
        if node is None:
            continue
        data = {e.tag: e.text for e in node.iter() if not list(e)}
        low, high = (_to_int(data.get(f'{prefix}_30WTHN_GTOFF_PPLTN_{suffix}')) for suffix in ('MIN', 'MAX'))
        if low is None or high is None or not 0 <= low <= high:
            continue
        # STN_TIME is a reference date/month, NOT a minute-precision observation time.
        source_time = data.get(f'{prefix}_PPLTN_TIME', '')
        observed = _parse_observed_at(source_time) if len(source_time) >= 12 else None
        if observed and observed > fetched_at:
            continue
        selected = {k: v for k, v in data.items() if '30WTHN' in k or k == f'{prefix}_PPLTN_TIME'}
        departures = [_to_int(data.get(f'{prefix}_30WTHN_GTON_PPLTN_{suffix}')) for suffix in ('MIN','MAX')]
        if any(v is None or v < 0 for v in departures) or departures[0] > departures[1]:
            departures = [None,None]
        transit.append({'mode': mode, 'observed_at': observed or fetched_at,
            'timestamp_quality': 'source' if observed else 'collection_only',
            'arrivals_min': low, 'arrivals_max': high,
            'departures_min': departures[0],
            'departures_max': departures[1],
            'fingerprint': hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest(),
            'raw_data': selected})
    if population is None and not transit:
        raise ExternalAPIError('Seoul response contains no valid observations')
    return population, transit


class SeoulCityClient:
    def __init__(self, session, api_key=None):
        self.session = session
        self.api_key = api_key or required_key('SEOUL_OPEN_API_KEY')

    def fetch(self, area, fetched_at):
        url = f'http://openapi.seoul.go.kr:8088/{quote(self.api_key, safe="")}/xml/citydata/1/5/{quote(area, safe="")}'
        return normalize_citydata(get_xml(self.session, url), area, fetched_at)
