"""Offline SQLite retention-scale benchmark. Writes only a fresh --output directory."""
import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
args = parser.parse_args()
out = Path(args.output).resolve()
out.mkdir(parents=True, exist_ok=True)
db = out / 'hourly-benchmark.sqlite3'
if db.exists():
    raise SystemExit('Use a fresh output directory; existing database is never overwritten')
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tourist_congestion_backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DJANGO_DB_PATH'] = str(db)
import django
django.setup()
from django.conf import settings
settings.DEBUG = False
from django.core.management import call_command
from django.db import connection
from places.hourly_models import HourlyStudy, HourlyTarget, HourlyObservation, HourlyRun, HourlyForecast
from places.services.hourly_forecast import dt, METRICS
from places.services.hourly_store import issue, dataset, digest

call_command('migrate', verbosity=0, interactive=False)
now = dt('2026-09-13T12:00:00+09:00')
targets = []
for provider in ('seoul', 'tmap'):
    study = HourlyStudy.objects.create(provider=provider, started_at=now-timedelta(days=400))
    for i in range(10):
        targets.append(HourlyTarget.objects.create(study=study, external_id=str(i), name=f'{provider}-{i}',
                       metric=METRICS[provider][0], scope=METRICS[provider][2], active=True, selected=True))
started = time.perf_counter()
for target in targets:
    batch = []
    for hour in range(400*24):
        at = now-timedelta(hours=hour, minutes=10)
        scale = 10000 if target.study.provider == 'seoul' else .03
        value = scale*(1+.2*math.sin(at.hour/24*2*math.pi))
        fingerprint = digest([target.pk, at.isoformat(), value])
        batch.append(HourlyObservation(target=target, observed_at=at, received_at=at+timedelta(minutes=8), value=value,
            fingerprint=fingerprint, raw_path=f'{at.date()}/{fingerprint}.json.gz', raw_hash=fingerprint, details={'synthetic': True}))
        if len(batch) == 1000:
            HourlyObservation.objects.bulk_create(batch, batch_size=100)
            batch = []
    HourlyObservation.objects.bulk_create(batch, batch_size=100)
    current = issue(target, now, {'tau': 3})
    template = list(current.forecasts.all())
    # Shared input includes an 85-day compact calendar, not a growing observation-ID list.
    metadata = {**current.inputs, 'calendar': {(now-timedelta(days=d)).date().isoformat(): False for d in range(85)}}
    for start in range(1, 300*24, 100):
        runs = [HourlyRun(target=target, issued_at=now-timedelta(hours=h), inputs=metadata,
                          parameters=current.parameters) for h in range(start, min(start+100, 300*24))]
        HourlyRun.objects.bulk_create(runs, batch_size=50)
        HourlyForecast.objects.bulk_create([HourlyForecast(run=r, valid_at=r.issued_at+timedelta(hours=f.payload['hours_ahead']),
            payload={**f.payload, 'issued_at': r.issued_at.isoformat(), 'valid_at': (r.issued_at+timedelta(hours=f.payload['hours_ahead'])).isoformat()},
            actual=f.payload['value'], status='matched') for r in runs for f in template], batch_size=100)
    print('seeded', target.pk, flush=True)
seed_seconds = time.perf_counter()-started
next_hour = now+timedelta(hours=1)
started = time.perf_counter()
for target in targets:
    issue(target, next_hour, {'tau': 3})
forecast_seconds = time.perf_counter()-started
latencies = []
for _ in range(100):
    started = time.perf_counter()
    latest = list(HourlyRun.objects.filter(target__in=targets, issued_at=next_hour).prefetch_related('forecasts'))
    assert sum(len(r.forecasts.all()) for r in latest) == 60
    latencies.append((time.perf_counter()-started)*1000)
latencies.sort()
result = {'kind': 'SYNTHETIC_LOAD_ONLY', 'targets': 20, 'observation_rows': HourlyObservation.objects.count(),
          'run_rows': HourlyRun.objects.count(), 'forecast_rows': HourlyForecast.objects.count(),
          'database_bytes': db.stat().st_size, 'raw_archives_included': False,
          'seed_seconds': seed_seconds, 'hourly_20_target_seconds': forecast_seconds,
          'latest_20_target_p95_ms': latencies[94], 'lock_errors': 0,
          'passed': forecast_seconds < 60 and latencies[94] < 200,
          'limits': 'Single SQLite writer, sequential readers; no multi-process stress. Synthetic forecasts are storage-size fixtures, not backtest evidence.'}
(out/'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
