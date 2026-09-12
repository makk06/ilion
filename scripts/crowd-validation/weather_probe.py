"""Small authenticated weather/calendar check; outputs normalized values only."""
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
from places.integrations.holidays import HolidayClient
from places.services.crowd_collector import charge
from places.services.crowd_estimator import KST

now = timezone.now().astimezone(KST)
report = {'checked_at': now.isoformat(), 'coordinate_basis': 'representative coordinates, not verified KTO POI coordinates', 'places': [], 'calls': {}}
def charged(provider, retry=False):
    if sum(report['calls'].values()) >= 20:
        raise RuntimeError('Probe call ceiling reached')
    charge(provider, retry)
    report['calls'][provider] = report['calls'].get(provider, 0) + 1

for name, lat, lon in [('Seoul Gyeongbokgung', 37.5796, 126.9770), ('Busan Haeundae beach', 35.1587, 129.1604), ('Jeonju Hanok village', 35.8151, 127.1530)]:
    grid = weather_grid(lat, lon)
    place = {'name': name, 'latitude': lat, 'longitude': lon, 'grid': grid, 'products': []}
    with BudgetSession(lambda retry=False: charged('kma', retry)) as session:
        for product in ('getUltraSrtNcst', 'getUltraSrtFcst', 'getVilageFcst'):
            issue = latest_issue(product, now)
            row = {'product': product, 'issued_at': issue.isoformat()}
            try:
                values = WeatherClient(session).fetch(product, grid, issue)
                row.update(status='passed', valid_count=len(values), data=[{'valid_at': at.isoformat(), 'values': v} for at, v in sorted(values.items())], horizon_coverage={str(h): (now+timedelta(hours=h)).replace(minute=0, second=0, microsecond=0) in values for h in (1,2,3)})
            except Exception as exc:
                row.update(status='failed', error_type=type(exc).__name__)
            place['products'].append(row)
    report['places'].append(place)
with BudgetSession(lambda retry=False: charged('kasi', retry)) as session:
    try:
        days = HolidayClient(session).fetch(now.year, now.month)
        report['calendar'] = {'status': 'passed', 'year': now.year, 'month': now.month, 'holidays': {d.isoformat(): name for d, name in days.items()}}
    except Exception as exc:
        report['calendar'] = {'status': 'failed', 'error_type': type(exc).__name__}
output = ROOT / '.integration-artifacts/crowd-validation/weather.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'output': str(output), 'calls': report['calls'], 'products': [(p['name'], [(r['product'],r['status']) for r in p['products']]) for p in report['places']], 'calendar_status': report['calendar']['status']}))
