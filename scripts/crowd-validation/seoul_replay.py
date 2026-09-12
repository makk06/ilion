"""Replay captured provider population to inspect delayed-evidence state handling.

This is an area-scope diagnostic with unknown profile, not a verified POI model.
No historical distribution, invented transit baseline, or forecast labels are used.
"""
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
from places.services.crowd_estimator import estimate

folder = ROOT / '.integration-artifacts/crowd-validation'
data = json.loads((folder/'seoul.json').read_text(encoding='utf-8'))
states = {}
rows = []
for row in data['observations']:
    p = row.get('population')
    if not p:
        continue
    area = row['external_id']
    at = datetime.fromisoformat(row['fetched_at'])
    inputs = {'place_id': area, 'latitude': 0, 'longitude': 0, 'profile': 'unknown',
        'mapping': {'area_id': area, 'match_quality': 1, 'representativeness': 1},
        'population': {'observed_at': datetime.fromisoformat(p['observed_at']),
            'value': (p['population_min']+p['population_max'])/2,
            'min': p['population_min'], 'max': p['population_max'],
            'level': p['crowd_level'], 'is_replaced': p['is_replaced']}}
    estimate_result, state = estimate(inputs, at, states.get(area))
    states[area] = state
    rows.append({'area_id': area, 'fetched_at': row['fetched_at'],
        'source_at': p['observed_at'], 'source_age_minutes': p['age_minutes'],
        'retained_ewma_history': len(state['history']),
        'trend_age_gate_passed': p['age_minutes'] <= 10,
        'normalization': estimate_result['normalization'],
        'tier': estimate_result['tier'], 'confidence': estimate_result['confidence'],
        'is_stale': estimate_result['is_stale']})
out = {'scope': 'area diagnostic, unknown profile; not verified POI output',
    'transit_excluded_reason': 'no comparable historical baseline',
    'population_replays': rows}
(folder/'seoul-replay.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=True))
