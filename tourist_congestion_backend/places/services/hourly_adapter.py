"""Explicitly promoted target route; no implicit cross-provider fallback."""
from datetime import timedelta
from places.hourly_models import HourlyTarget, HourlyRun
from .hourly_forecast import dt, METRICS
from .hourly_store import digest
from .crowd_estimator import level
from .hourly_decisions import CONTRACT, relative_label


def adapt_many(results, now):
    hour = dt(now).replace(minute=0, second=0, microsecond=0)
    targets = list(HourlyTarget.objects.filter(promoted=True, selected=True).select_related('study'))
    runs = {r.target_id: r for r in HourlyRun.objects.filter(target__in=targets, issued_at=hour).prefetch_related('forecasts')}
    routes = {}
    for target in targets:
        from .hourly_evaluation import require_frozen
        try:
            require_frozen(target.study)
        except ValueError:
            continue
        state = target.study.state
        fingerprint = digest(state.get('parameters', {}))
        if any(state.get(k, {}).get('status') != 'PASS' or state.get(k, {}).get('parameter_hash') != fingerprint
               or state.get(k, {}).get('selection_hash') != state['selection_hash']
               or state.get(k, {}).get('decision_contract_version') != CONTRACT['version']
               or state.get(k, {}).get('usability', {}).get('guidance', {}).get('status') != 'PASS'
               for k in ('validation', 'shadow_validation')):
            continue
        for place_id in target.mapping.get('place_ids', []):
            routes.setdefault(place_id, []).append(target)
    for place_id, candidates in routes.items():
        if place_id not in results or len(candidates) != 1:
            continue
        target = candidates[0]
        run = runs.get(target.pk)
        stored = {f.payload['hours_ahead']: f.payload for f in run.forecasts.all()} if run and run.parameters == target.study.state['parameters'] else {}
        forecasts = []
        for h in (1, 2, 3):
            row = stored.get(h, {})
            score = row.get('crowd_score')
            value = row.get('value')
            metric, unit, scope = METRICS[target.study.provider]
            ranking_ok = (target.study.state.get('selection_ranking_pass', False) and not target.study.state.get('ranking_suspended', False)
                          and all(target.study.state[k].get('usability', {}).get('ranking', {}).get('status') == 'PASS' for k in ('validation', 'shadow_validation')))
            forecasts.append({**row, 'hours_ahead': h, 'valid_at': (hour+timedelta(hours=h)).isoformat(),
                'provider': target.study.provider, 'external_id': target.external_id,
                'metric': metric, 'unit': unit, 'scope': scope, 'value': value,
                'area_population': value if metric == 'population_count' else None,
                'population': value if metric == 'population_count' else None,
                'crowd_score': score,
                'relative_label': relative_label(score), 'decision_contract_version': CONTRACT['version'],
                'comparison_basis': 'within_target_history',
                'very_busy_above': CONTRACT['very_busy_above'],
                'guidance_eligible': value is not None and score is not None,
                'ranking_eligible': ranking_ok and value is not None and score is not None,
                'decision_reasons': ([] if ranking_ok else ['ranking_not_validated']) + ([] if value is not None else ['forecast_missing']),
                'crowd_level': level(score)[0] if score is not None else None,
                'confidence': 0, 'confidence_status': 'not_calibrated',
                'status': row.get('status', 'unavailable'), 'reasons': row.get('reasons', ['forecast_missing']),
                'normalization': 'within_target_empirical_percentile', 'weather_available': False,
                'baseline_fallback': False, 'model_version': 'hourly-mean-v2'})
        results[place_id] = {**results[place_id], 'forecast': forecasts}
    return results
