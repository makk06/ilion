"""Small authenticated Seoul probe; no secrets or full response payloads written."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tourist_congestion_backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.utils import timezone
from places.integrations.crowd_http import BudgetSession
from places.integrations.seoul_citydata import SeoulCityClient
from places.services.crowd_collector import charge

OUT = ROOT / '.integration-artifacts/crowd-validation/seoul.json'
catalog = json.loads((ROOT / 'tourist_congestion_backend/places/data/seoul_crowd_areas.json').read_text(encoding='utf-8'))
targets = [r for r in catalog['areas'] if r['external_id'] in ('POI008', 'POI007', 'POI068', 'POI005')]
result = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'provider': 'seoul_citydata', 'observations': [], 'http_attempts': 0}

def budget(retry=False):
    if result['http_attempts'] >= 20:
        raise RuntimeError('Probe attempt cap reached')
    charge('seoul', retry)
    result['http_attempts'] += 1

with BudgetSession(budget) as session:
    client = SeoulCityClient(session)
    for area in targets:
        fetched = timezone.now()
        row = dict(area, fetched_at=fetched.isoformat(), is_demo=False)
        try:
            pop, transit = client.fetch(area['external_id'], fetched)
            row['population'] = None if pop is None else {
                'population_min': pop.population_min, 'population_max': pop.population_max,
                'observed_at': pop.observed_at.isoformat(), 'crowd_level': pop.crowd_level,
                'provider_category': pop.raw_data.get('AREA_CONGEST_LVL'),
                'is_replaced': pop.is_replaced, 'age_minutes': round((fetched-pop.observed_at).total_seconds()/60, 2),
                'timestamp_quality': 'source', 'scope': 'source_area'}
            row['transit'] = [{k: (v.isoformat() if isinstance(v, datetime) else v) for k,v in t.items() if k != 'raw_data'} for t in transit]
            row['status'] = 'success'
        except Exception as exc:
            row.update(status='failed', error_type=type(exc).__name__)
        result['observations'].append(row)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(row, ensure_ascii=True))
print('HTTP attempts cumulative:', result['http_attempts'])
comparisons = []
for area in targets:
    rounds = [r for r in result['observations'] if r['external_id'] == area['external_id'] and r['status'] == 'success']
    for previous, current in zip(rounds, rounds[1:]):
        p0, p1 = previous['population'], current['population']
        previous_transit = {t['mode']: t for t in previous['transit']}
        comparisons.append({'external_id': area['external_id'],
            'from_fetched_at': previous['fetched_at'], 'to_fetched_at': current['fetched_at'],
            'source_advance_minutes': (datetime.fromisoformat(p1['observed_at'])-datetime.fromisoformat(p0['observed_at'])).total_seconds()/60 if p0 and p1 else None,
            'same_transit_fingerprint_modes': [t['mode'] for t in current['transit'] if t['mode'] in previous_transit and t['fingerprint'] == previous_transit[t['mode']]['fingerprint']]})
result['comparisons'] = comparisons
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
