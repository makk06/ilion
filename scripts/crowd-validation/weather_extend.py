"""Reuse checked grids, probe only additional grids from live KTO selections."""
import json
import os
from pathlib import Path
import sys
from datetime import timedelta
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tourist_congestion_backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.utils import timezone
from places.integrations.crowd_http import BudgetSession
from places.integrations.weather import WeatherClient, latest_issue, weather_grid
from places.services.crowd_collector import charge
from places.services.crowd_estimator import KST

directory = ROOT / '.integration-artifacts/crowd-validation'
report = json.loads((directory/'weather.json').read_text(encoding='utf-8'))
selected = json.loads((directory/'kto.json').read_text(encoding='utf-8'))['selected']
known = {tuple(p['grid']) for p in report['places']}
report['kto_grid_matches'] = []
def charged(retry=False):
    if sum(report['calls'].values()) >= 30:
        raise RuntimeError('Probe cumulative call ceiling reached')
    charge('kma', retry)
    report['calls']['kma'] += 1
for label, poi in selected.items():
    grid = weather_grid(poi['latitude'], poi['longitude'])
    report['kto_grid_matches'].append({'label': label, 'contentid': poi['contentid'], 'latitude': poi['latitude'], 'longitude': poi['longitude'], 'grid': grid, 'coordinate_basis': 'live KTO selected record'})
    if grid in known:
        continue
    now = timezone.now().astimezone(KST)
    place = {'name': poi['title'], 'contentid': poi['contentid'], 'latitude': poi['latitude'], 'longitude': poi['longitude'], 'grid': grid, 'coordinate_basis': 'live KTO selected record', 'products': []}
    with BudgetSession(charged) as session:
        for product in ('getUltraSrtNcst', 'getUltraSrtFcst'):
            issue = latest_issue(product, now)
            row = {'product': product, 'issued_at': issue.isoformat(), 'requested_at': timezone.now().astimezone(KST).isoformat()}
            try:
                values = WeatherClient(session).fetch(product, grid, issue)
                row.update(status='passed', fetched_at=timezone.now().astimezone(KST).isoformat(), valid_count=len(values), data=[{'valid_at': at.isoformat(), 'values': v} for at,v in sorted(values.items())], horizon_coverage={str(h): (now+timedelta(hours=h)).replace(minute=0,second=0,microsecond=0) in values for h in (1,2,3)})
            except Exception as exc:
                row.update(status='failed', error_type=type(exc).__name__)
            place['products'].append(row)
    report['places'].append(place)
    known.add(grid)
report['extended_at'] = timezone.now().astimezone(KST).isoformat()
(directory/'weather.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'calls':report['calls'],'kto_grid_matches':report['kto_grid_matches']},ensure_ascii=True))
