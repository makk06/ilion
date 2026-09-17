"""Pure hourly v2 predictor. Data is already indexed by its independent target."""
import math
from statistics import mean
from datetime import timedelta
from .mean_forecast import dt, finite, day_group

VERSION = 'hourly-mean-v2'
METRICS = {'seoul': ('population_count', 'persons', 'area_population'),
           'tmap': ('population_density', 'persons_per_m2', 'place_density')}
DEFAULTS = {'half_life': None, 'tau': None}
PARAMETERS = [{'half_life': half, 'tau': tau} for half in (None, 14, 28, 56) for tau in (None, .5, 1.5, 3)]


def validate_identity(data):
    if data.get('provider') not in METRICS or data.get('metric') != METRICS[data['provider']][0]:
        raise ValueError('Provider and metric must match')
    for row in data.get('observations', []):
        if any(row.get(k, data[k]) != data[k] for k in ('provider', 'external_id', 'metric')):
            raise ValueError('Mixed observation identity')


def samples(data, cutoff):
    """Latest observed reading received by the hour; first version of an observation wins."""
    cutoff = dt(cutoff)
    first = {}
    for row in sorted(data.get('observations', []), key=lambda r: (dt(r['received_at']), r.get('id', 0))):
        at, received = dt(row['observed_at']), dt(row['received_at'])
        if not finite(row['value']) or row['value'] < 0 or at > received or received > cutoff:
            continue
        first.setdefault(at, {**row, 'observed_at': at, 'received_at': received})
    result = {}
    for at, row in sorted(first.items()):
        hour = at.replace(minute=0, second=0, microsecond=0)
        if at != hour:
            hour += timedelta(hours=1)
        if hour <= cutoff and hour - at <= timedelta(minutes=15) and row['received_at'] <= hour:
            result[hour] = row
    return result


def baseline(history, target, cutoff, calendar, half):
    holiday = calendar.get(target.date().isoformat())
    candidate = [(t, r['value']) for t, r in history.items() if t.hour == target.hour]
    exact = [(t, v) for t, v in candidate if t.weekday() == target.weekday() and calendar.get(t.date().isoformat()) == holiday]
    group = [(t, v) for t, v in candidate if day_group(t, calendar.get(t.date().isoformat())) == day_group(target, holiday)]
    for selected, fallback in ((exact, 'same_weekday'), (group, 'day_group'), (candidate, 'all_days')):
        if len(selected) >= 8:
            weights = [2 ** (-(cutoff.date()-t.date()).days/half) if half else 1 for t, _ in selected]
            return {'base': sum(v*w for (_, v), w in zip(selected, weights))/sum(weights),
                    'arithmetic': mean(v for _, v in selected), 'sample_days': len(selected), 'fallback': fallback}
    return {'base': None, 'arithmetic': None, 'sample_days': len(candidate), 'fallback': 'insufficient_history'}


def predict(data, issued_at, parameters=None, *, history_days=84):
    validate_identity(data)
    now = dt(issued_at)
    if now.minute or now.second or now.microsecond:
        raise ValueError('Exact-hour issue required')
    params = {**DEFAULTS, **(parameters or {})}
    for key in ('half_life', 'tau'):
        if params[key] is not None and (not finite(params[key]) or params[key] <= 0):
            raise ValueError('Positive weight or None required')
    points = samples(data, now)
    midnight = now.replace(hour=0)
    history = {t: r for t, r in points.items() if midnight-timedelta(days=history_days) <= t < midnight}
    calendar = data.get('calendar', {})
    current = points.get(now)
    cb = baseline(history, now, now, calendar, params['half_life'])
    available = current is not None and cb['base'] is not None
    delta = current['value']-cb['base'] if available and params['tau'] else 0
    distribution = [r['value'] for r in history.values()]
    result = []
    for h in (1, 2, 3):
        target = now + timedelta(hours=h)
        b = baseline(history, target, now, calendar, params['half_life'])
        correction = math.exp(-h/params['tau'])*delta if params['tau'] else 0
        value = max(0, b['base']+correction) if b['base'] is not None else None
        reasons = []
        if value is None:
            reasons.append('insufficient_history')
        if params['tau'] and not available:
            reasons.append('current_unavailable')
        if target.date().isoformat() not in calendar:
            reasons.append('calendar_unknown')
        week = points.get(target-timedelta(days=7))
        result.append({**b, 'provider': data['provider'], 'external_id': data['external_id'],
                       'metric': data['metric'], 'unit': METRICS[data['provider']][1], 'scope': METRICS[data['provider']][2],
                       'issued_at': now.isoformat(), 'valid_at': target.isoformat(), 'hours_ahead': h,
                       'value': value, 'population': value if data['metric'] == 'population_count' else None,
                       'correction': correction, 'delta': delta, 'model_version': VERSION, 'parameters': params,
                       'latest_observed_at': current['observed_at'].isoformat() if current else None,
                       'crowd_score': 100*(sum(v < value for v in distribution)+.5*sum(v == value for v in distribution))/len(distribution) if value is not None and distribution else None,
                       'reasons': reasons, 'status': 'ok' if value is not None else 'insufficient_history',
                       'comparisons': {'arithmetic': b['arithmetic'], 'weekly': week['value'] if week else None,
                                       'persistence': current['value'] if current else None}})
    return result
