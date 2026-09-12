"""Small, budgeted live TourAPI probe; writes only allowlisted public fields."""
import json
import os
import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tourist_congestion_backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.utils import timezone
from shapely.geometry import shape, Point
from shapely.ops import transform
from places.integrations.crowd_http import BudgetSession
from places.integrations.http import get_json
from places.integrations.tour_api import TourAPIClient, _response_items
from places.services.crowd_collector import charge
from places.services.place_resolver import polygon_match
from places.models import CrowdArea

calls = 0
def charge_probe(retry=False):
    global calls
    if calls >= 30:
        raise RuntimeError('Probe limit reached')
    charge('tour_api', retry=retry)
    calls += 1

client = TourAPIClient(session=BudgetSession(charge_probe))
areas = [(area, shape(area.geometry)) for area in CrowdArea.objects.exclude(geometry={})]
FIELDS = ('contentid', 'contenttypeid', 'title', 'mapx', 'mapy', 'cat1', 'cat2', 'cat3',
          'lclssystm1', 'lclssystm2', 'lclssystm3', 'ldongregncd', 'ldongsigungucd',
          'lclsSystm1', 'lclsSystm2', 'lclsSystm3', 'lDongRegnCd', 'lDongSignguCd',
          'addr1', 'modifiedtime', 'eventstartdate', 'eventenddate')
def public(item):
    value = {key: item[key] for key in FIELDS if key in item}
    value['fetched_at'] = timezone.now().isoformat()
    try:
        lat, lon = float(item['mapy']), float(item['mapx'])
        area = polygon_match(lat, lon, areas)
        value['polygon_match'] = {'code': area.external_id, 'name': area.name} if area else None
        value['latitude'], value['longitude'] = lat, lon
    except (ValueError, KeyError, TypeError):
        value['coordinate_valid'] = False
    return value

target = ROOT / '.integration-artifacts/crowd-validation/kto.json'
if '--complete-events' in sys.argv:
    result = json.loads(target.read_text(encoding='utf-8'))
    selected = next(i for i in result['hongdae_page2'] if i['contentid'] == '781031')
    lat, lon = selected['latitude'], selected['longitude']
    selected['polygon_diagnostics'] = []
    for area, geo in areas:
        metric = transform(lambda x, y, z=None: ((x-lon)*111320*math.cos(math.radians(lat)), (y-lat)*111320), geo)
        distance = metric.boundary.distance(Point(0, 0))
        if geo.covers(Point(lon, lat)) or distance < 100:
            selected['polygon_diagnostics'].append({'code': area.external_id, 'name': area.name, 'covers': geo.covers(Point(lon, lat)), 'boundary_meters': round(distance, 2)})
    result['selected']['홍대'] = selected
    for page in (2, 3):
        items, total = client.fetch_events_page(page_number=page, start_date='20260901', end_date='20261031')
        result['events']['items'].extend(public(i) for i in items)
    result['events']['coverage'] = 'all_3_pages_of_requested_date_window'
    result['events']['unique_count'] = len({i['contentid'] for i in result['events']['items']})
    result['events']['limitations'] = ['Date range query is not the entire event registry; retain existing long-running events.', 'Free-text playtime is not verified opening hours.', 'No verified attendance or event-size evidence was obtained.']
    result['actual_http_attempts'] += calls
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'calls': calls, 'events': result['events']['unique_count'], 'hongdae': selected}, ensure_ascii=True))
    sys.exit(0)
if '--hongdae' in sys.argv:
    result = json.loads(target.read_text(encoding='utf-8'))
    payload = get_json(client.session, f'{client.base_url}/searchKeyword2', params={**client._base_params(), 'keyword': '홍대', 'numOfRows': 100, 'pageNo': 2, 'arrange': 'A'}, timeout=client.timeout, provider='TourAPI')
    _, items = _response_items(payload)
    result['hongdae_page2'] = [public(i) for i in items]
    result['actual_http_attempts'] += calls
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['hongdae_page2'], ensure_ascii=True))
    sys.exit(0)
if '--finish' in sys.argv:
    result = json.loads(target.read_text(encoding='utf-8'))
    for endpoint, params, label in [('searchKeyword2', {'keyword': '홍익대학교', 'contentTypeId': '12'}, 'hongik'), ('lclsSystmCode2', {'lclsSystm1': 'NA', 'lclsSystm2': 'NA02'}, 'natural_category_codes')]:
        try:
            payload = get_json(client.session, f'{client.base_url}/{endpoint}', params={**client._base_params(), **params, 'numOfRows': 100, 'pageNo': 1}, timeout=client.timeout, provider='TourAPI')
            _, items = _response_items(payload)
            result[label] = [public(i) for i in items] if label == 'hongik' else items
        except Exception as exc:
            result[label] = {'error_type': type(exc).__name__}
    hongik = result.get('hongik', [])
    if isinstance(hongik, list):
        exact = [i for i in hongik if '거리' in i.get('title', '')]
        if len(exact) == 1:
            result['selected']['홍대'] = exact[0]
    result['actual_http_attempts'] += calls
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'calls': calls, 'hongik': result.get('hongik'), 'natural_category_codes': result.get('natural_category_codes')}, ensure_ascii=True))
    sys.exit(0)
if '--canonical' in sys.argv:
    result = json.loads(target.read_text(encoding='utf-8'))
    selected = {}
    for name, cid in [('경복궁', '126508'), ('성수', '2930901'), ('해운대', '126081'), ('전주한옥마을', '264284')]:
        detail = client.fetch_place_detail(cid, '12', include_intro=False)
        selected[name] = public(detail.raw_data['common'])
    for keyword, name in [('홍대', '홍대'), ('롯데월드', '잠실')]:
        payload = get_json(client.session, f'{client.base_url}/searchKeyword2',
                           params={**client._base_params(), 'keyword': keyword, 'contentTypeId': '12', 'numOfRows': 100, 'pageNo': 1, 'arrange': 'A'},
                           timeout=client.timeout, provider='TourAPI')
        _, items = _response_items(payload)
        result['places'][keyword + '_tourism_only'] = {'status': 'success', 'candidates': [public(i) for i in items]}
        candidates = [i for i in items if (name == '잠실' and i.get('title') == '롯데월드 어드벤처') or (name == '홍대' and '거리' in i.get('title', ''))]
        if len(candidates) == 1:
            selected[name] = public(candidates[0])
    for value in selected.values():
        lat, lon = value['latitude'], value['longitude']
        point = Point(lon, lat)
        diagnostic = []
        for area, geo in areas:
            metric = transform(lambda x, y, z=None: ((x-lon)*111320*math.cos(math.radians(lat)), (y-lat)*111320), geo)
            distance = metric.boundary.distance(Point(0, 0))
            if geo.covers(point) or distance < 100:
                diagnostic.append({'code': area.external_id, 'name': area.name, 'covers': geo.covers(point), 'boundary_meters': round(distance, 2)})
        value['polygon_diagnostics'] = diagnostic
    result['selected'] = selected
    result['actual_http_attempts'] += calls
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'calls': calls, 'selected': selected}, ensure_ascii=True))
    sys.exit(0)
supplement = '--supplement' in sys.argv
result = json.loads(target.read_text(encoding='utf-8')) if supplement else {'source': 'KTO KorService2', 'started_at': timezone.now().isoformat(), 'places': {}, 'events': {}}
keywords = ('홍대거리', '전주 한옥마을') if supplement else ('경복궁', '홍대', '성수', '잠실', '해운대', '전주한옥마을')
for keyword in keywords:
    try:
        payload = get_json(client.session, f'{client.base_url}/searchKeyword2',
                           params={**client._base_params(), 'keyword': keyword, 'numOfRows': 100, 'pageNo': 1, 'arrange': 'A'},
                           timeout=client.timeout, provider='TourAPI')
        body, items = _response_items(payload)
        result['places'][keyword] = {'status': 'success', 'total': body.get('totalCount'), 'candidates': [public(i) for i in items]}
    except Exception as exc:
        result['places'][keyword] = {'status': 'error', 'error_type': type(exc).__name__}
try:
    if supplement:
        raise StopIteration
    items, total = client.fetch_events_page(start_date='20260901', end_date='20261031')
    result['events'] = {'status': 'success', 'total': total, 'coverage': 'first_page_only', 'items': [public(i) for i in items]}
    if items:
        detail = client.fetch_place_detail(items[0]['contentid'], '15')
        intro = detail.raw_data.get('intro', {})
        result['events']['detail_sample'] = {k: intro.get(k) for k in ('contentid', 'eventstartdate', 'eventenddate', 'playtime', 'eventplace')}
        result['events']['time_accuracy'] = 'unverified_free_text; not converted to confirmed hours'
except StopIteration:
    pass
except Exception as exc:
    result['events']['error_type'] = type(exc).__name__
result['actual_http_attempts'] = result.get('actual_http_attempts', 0) + calls
result['finished_at'] = timezone.now().isoformat()
target = ROOT / '.integration-artifacts/crowd-validation/kto.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'actual_http_attempts': calls, 'statuses': {k: v['status'] for k, v in result['places'].items()}, 'events_status': result['events'].get('status'), 'artifact': str(target)}, ensure_ascii=True))
