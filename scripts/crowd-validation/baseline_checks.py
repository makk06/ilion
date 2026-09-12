"""Read-only baseline readiness and isolated quota/scope counterexamples."""
import json
import os
import sys
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tourist_congestion_backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from places.models import HistoricalBaseline, HistoricalSample, ForecastEvaluation
from places.services.crowd_estimator import estimate
from places.test_crowd_estimator import NOW, observed

interval = 220
minutes = 84 * 1440
observation_minutes = list(range(0, minutes, interval))
buckets = {m // 60 for m in observation_minutes}
label_matches = {}
for horizon in (60, 120, 180):
    # record_forecast rejects stale inputs: population is fresh only through minute 10.
    valid_times = [issued + age + horizon for issued in observation_minutes for age in (0, 5, 10)]
    obs = set(observation_minutes)
    label_matches[str(horizon // 60)] = sum(any(t + tolerance in obs for tolerance in range(6)) for t in valid_times)

data = observed()
same_scope = estimate(data, NOW)[0]
proxy = deepcopy(data)
proxy['mapping']['representativeness'] = .4
proxy_scope = estimate(proxy, NOW)[0]
result = {
    'db_counts': {model.__name__: model.objects.count() for model in (HistoricalSample, HistoricalBaseline, ForecastEvaluation)},
    'quota_simulation_not_real_observations': {
        'interval_minutes': interval, 'days': 84, 'hourly_bucket_coverage': len(buckets)/(84*24),
        'required_coverage': .7, 'eligible_forward_labels_by_horizon': label_matches,
        'assumptions': 'Stable 220-minute source observations; estimations at source time plus 0/5/10 minutes; no other source history.'},
    'synthetic_scope_counterexample': {
        'same_population_same_area_same_baseline': True,
        'representativeness_1_forecasts': [f['crowd_score'] for f in same_scope['forecast']],
        'representativeness_point4_forecasts': [f['crowd_score'] for f in proxy_scope['forecast']],
        'target_for_both': 'The same later source-area population percentile',
        'interpretation': 'First POI selected within an area/hour changes measured model error although area label is unchanged.'},
    'review_findings': [
        '220-minute all-area cadence cannot achieve the 70% hourly history gate; accumulating more days does not solve coverage.',
        'At that cadence, fresh-issued +1/+2/+3h horizons have no observation in the next five-minute label window.',
        'Evaluation mixes model versions and POI-specific predictions against area targets; a globally disabled horizon persists until manual reset.'
    ],
    'positive_controls': [
        'Forward evaluation freezes forecast scores and population distribution at issuance.',
        'Development and replaced population rows are excluded from later labels.',
        'Baseline input selection checks period_end and created_at against requested now.',
        'No observed accuracy claim is possible from the current zero evaluation count.'
    ]
}
path = ROOT / '.integration-artifacts/crowd-validation/baseline_checks.json'
path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
