from datetime import timedelta
from statistics import mean
from .mean_forecast import dt
from .mean_study import validation_rows
from .mean_validation import metrics


def monitor(study, now):
    now = dt(now)
    day = now.date().isoformat()
    logs = study.state.get('daily_monitor', {})
    if day in logs:
        return logs[day]
    end = now-timedelta(hours=27)
    rows = validation_rows(study, end-timedelta(days=7), end)
    promotion = study.state.get('promotion', {})
    scales, peaks = promotion.get('scales', {}), promotion.get('peaks', {})
    paired = [r for r in rows if r.get('population') is not None and r.get('actual') is not None
              and r.get('arithmetic') is not None and r['parameters'] == study.state.get('parameters')]
    sufficient = bool(scales) and all(sum(r['area_id'] == a and r['hours_ahead'] == h for r in paired) >= 100
                                    for a in study.state.get('areas', []) for h in (1, 2, 3))
    result = {'date': day, 'status': 'NEEDS_MORE_DATA', 'paired': len(paired),
              'provided_rate': mean(r.get('population') is not None for r in rows) if rows else 0,
              'label_rate': mean(r.get('actual') is not None for r in rows) if rows else 0}
    if sufficient:
        current = metrics(paired, 'population', scales, peaks)
        base = metrics(paired, 'arithmetic', scales, peaks)
        result.update(status='DEGRADED' if current['nmae'] > 1.1*base['nmae'] else 'OK', model=current, baseline=base)
    logs[day] = result
    previous = [(now.date()-timedelta(days=d)).isoformat() for d in range(3)]
    if study.state.get('deployment') == 'mean' and all(logs.get(d, {}).get('status') == 'DEGRADED' for d in previous):
        study.state['deployment'] = 'arithmetic'
        result['fallback'] = 'arithmetic'
    study.state['daily_monitor'] = {k: v for k, v in logs.items() if k >= (now.date()-timedelta(days=400)).isoformat()}
    study.save(update_fields=['state'])
    return result
