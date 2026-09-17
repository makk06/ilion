"""Replay captured evidence and separate synthetic semantic checks; never call APIs."""
import importlib.util
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('comparison', Path(__file__).with_name('compare_models.py'))
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)
import places.services.crowd_estimator as estimator


def run():
    now = datetime.fromisoformat('2026-09-12T23:26:14.771409+09:00')
    # Freeze reviewed mappings from the original capture, not today's mutable DB.
    mappings = []
    areas = {row['name']: row['external_id'] for row in comparison.read('seoul.json')['observations']}
    for row in comparison.read('comparison.json')['places']:
        mapping = row['mapping']
        if mapping.get('match_method') not in ('manual', 'source'):
            continue
        sources = SimpleNamespace(filter=lambda contentid=row['contentid'], **kw: [SimpleNamespace(external_id=contentid)])
        mappings.append(SimpleNamespace(valid_from=None, valid_until=None,
            place=SimpleNamespace(sources=sources), crowd_area_id=mapping['area_id'],
            crowd_area=SimpleNamespace(external_id=areas[mapping['area_name']], name=mapping['area_name']),
            match_method=mapping['match_method'], match_quality=mapping['match_quality'],
            representativeness=mapping['representativeness']))
    original_model = comparison.PlaceCrowdArea
    comparison.PlaceCrowdArea = SimpleNamespace(objects=SimpleNamespace(
        filter=lambda **kw: SimpleNamespace(select_related=lambda *args: mappings)))
    try:
        captured = comparison.make_inputs(now)
    finally:
        comparison.PlaceCrowdArea = original_model
    actual = []
    for name, _, data, _ in captured:
        features = comparison.features(data, now)
        full = comparison.candidates(features)['C']
        ablation = {'FULL': full}
        ablation['without_empirical_baseline'] = full  # Captured inputs contain no empirical baseline.
        for signal in ('population', 'transit', 'weather', 'event'):
            ablation['without_' + signal] = comparison.candidates(features, {signal: 0})['C']
        neutral = {**features, 'B': 50}
        ablation['neutral_baseline_50_diagnostic'] = comparison.candidates(neutral)['C']
        sensitivity = {signal: {str(scale): comparison.candidates(features, {signal: scale})['C'] - full
                               for scale in (.8, 1.2)} for signal in ('population', 'transit', 'weather', 'event')}
        actual.append({'place': name, 'ablation': ablation, 'sensitivity': sensitivity,
                       'features': features, 'score': estimator.estimate(data, now)[0]['crowd_score']})

    revised = estimator.weather_effect

    def legacy(profile, exposure, values):
        if values:
            values = {**values, 'wind_speed': values.get('wind_speed', 0)}
        effect, quality = revised(profile, exposure, values)
        if profile == 'beach' and quality and values.get('sky') == 1 and 24 <= values['temperature'] <= 32:
            effect = comparison.clip(effect + .4, -1, 1)
        return effect, quality

    synthetic = []
    base = deepcopy(captured[2][2])
    base.update(population=None, transit=[], mapping={}, events=[], event_coverage=0,
                events_checked_at=None, profile='beach', indoor_outdoor='outdoor', forecast_weather={})
    try:
        for hour in (12, 23):
            at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            for name, values in (
                ('warm_clear', {'temperature': 28, 'precipitation_type': 0, 'wind_speed': 0, 'sky': 1}),
                ('clear_rain', {'temperature': 28, 'precipitation_type': 1, 'wind_speed': 0, 'sky': 1}),
                ('missing_wind_rain', {'temperature': 28, 'precipitation_type': 1, 'sky': 1}),
            ):
                data = deepcopy(base)
                data['weather'] = {'issued_at': at, 'valid_at': at, 'product': 'getUltraSrtNcst', 'values': values}
                estimator.weather_effect = legacy
                before = estimator.estimate(data, at)[0]
                estimator.weather_effect = revised
                after = estimator.estimate(data, at)[0]
                synthetic.append({'hour': hour, 'case': name, 'before': before['crowd_score'],
                                  'after': after['crowd_score'], 'confidence_before': before['confidence'],
                                  'confidence_after': after['confidence']})
    finally:
        estimator.weather_effect = revised
    saturation = [{'events': n, 'effect': 1 - .825**n, 'points_at_full_coverage': 12*(1 - .825**n)}
                  for n in (1, 5, 10, 20)]
    return {'captured_at': now.isoformat(), 'model_version': estimator.MODEL_VERSION,
            'actual_captured_replay': actual, 'synthetic_semantic_checks': synthetic,
            'synthetic_date_only_event_saturation': saturation,
            'limitations': ['No ground-truth labels: no accuracy or superiority estimate.',
                            'Neutral B=50 is a dependency diagnostic, not an alternative model.',
                            'Legacy weather reconstructed only for these controlled fixtures.',
                            'Transit quality and weather effect are zero in the captured ablation.']}


if __name__ == '__main__':
    output = comparison.ARTIFACTS / 'improvement_checks.json'
    result = run()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for filename, values in (
        ('improvement_actual.json', {'captured_at': result['captured_at'], 'model_version': result['model_version'],
                                     'places': result['actual_captured_replay'], 'accuracy': 'UNKNOWN'}),
        ('improvement_synthetic.json', {'weather': result['synthetic_semantic_checks'],
                                       'event_saturation': result['synthetic_date_only_event_saturation'],
                                       'is_observed_data': False}),
    ):
        (comparison.ARTIFACTS / filename).write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
