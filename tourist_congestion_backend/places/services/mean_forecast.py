"""Pure, as-of area population forecasting. No database or network access."""
import math
from datetime import datetime, timedelta, timezone
from statistics import mean

KST = timezone(timedelta(hours=9))
VERSION = 'area-mean-v1'
DEFAULTS = {'half_life': 28, 'tau': 1.5, 'weather': True, 'events': True}


def dt(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return value.astimezone(KST)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def population(rows, cutoff):
    """Keep the first received valid source observation, never a revised future value."""
    found = {}
    for row in sorted(rows, key=lambda r: dt(r['received_at'])):
        at, received = dt(row['at']), dt(row['received_at'])
        lo, hi = row.get('min'), row.get('max')
        if (at > cutoff or received > cutoff or row.get('replaced') or row.get('demo')
                or not finite(lo) or not finite(hi) or not 0 <= lo <= hi):
            continue
        found.setdefault(at, {**row, 'at': at, 'received_at': received, 'value': (lo + hi) / 2})
    return sorted(found.values(), key=lambda r: r['at'])


def hourly(rows):
    buckets = {}
    for row in rows:
        at = row['at']
        hour = at.replace(minute=0, second=0, microsecond=0)
        if at <= hour + timedelta(minutes=5):
            buckets.setdefault(hour, {**row, 'bucket': hour})
    return list(buckets.values())


def weather(data, target, cutoff, forecast=False):
    hour = target.replace(minute=0, second=0, microsecond=0)
    source = data.get('_weather', {}).get(hour, []) if '_weather' in data else data.get('weather', [])
    rows = [r for r in source if dt(r['received_at']) <= cutoff
            and dt(r['issued_at']) <= cutoff and dt(r['at']) == hour
            and (r['product'] != 'getUltraSrtNcst') == forecast]
    for row in sorted(rows, key=lambda r: (dt(r['issued_at']), dt(r['received_at'])), reverse=True):
        temp, rain = row.get('temperature'), row.get('precipitation_type')
        if finite(temp) and -60 <= temp <= 60 and rain in (0, 1, 2, 3, 4, 5, 6, 7):
            return temp, {0: 'none', 1: 'rain', 2: 'mixed', 3: 'snow', 4: 'rain',
                          5: 'rain', 6: 'mixed', 7: 'snow'}[rain]
    return None


def calendar(data, target, cutoff):
    source = data.get('_calendar', {}).get(target.date().isoformat(), []) if '_calendar' in data else data.get('calendar', [])
    rows = [r for r in source if r['date'] == target.date().isoformat()
            and dt(r['received_at']) <= cutoff]
    if not rows:
        return None
    return max(rows, key=lambda r: dt(r['received_at']))['is_holiday']


def events(data, target, cutoff):
    # Explicit area verification snapshots establish absence; catalog proximity does not.
    checks = [r for r in data.get('event_checks', []) if dt(r['received_at']) <= cutoff
              and r['start_date'] <= target.date().isoformat() <= r['end_date']]
    if not checks:
        return None, ['events_unknown']
    latest = max(checks, key=lambda r: dt(r['received_at']))
    active, reasons = [], []
    for row in latest['events']:
        if not row.get('active', True):
            continue
        if row.get('starts_at') and row.get('ends_at'):
            applies = dt(row['starts_at']) <= target < dt(row['ends_at'])
        else:
            applies = row['start_date'] <= target.date().isoformat() <= row['end_date']
            if applies:
                reasons.append('event_time_unknown')
        if applies:
            active.append(row)
    return active, reasons


def day_group(at, holiday):
    return 'holiday' if holiday else ('weekend' if at.weekday() >= 5 else 'weekday')


def weighted(rows, weights):
    total = sum(weights)
    return sum(r['value'] * w for r, w in zip(rows, weights)) / total if total > 0 else None


def baseline(data, history, target, cutoff, params):
    holiday = calendar(data, target, cutoff)
    candidates = [r for r in history if r['bucket'].hour == target.hour]
    exact = [r for r in candidates if r['bucket'].weekday() == target.weekday()
             and calendar(data, r['bucket'], cutoff) == holiday]
    group = [r for r in candidates if day_group(r['bucket'], calendar(data, r['bucket'], cutoff))
             == day_group(target, holiday)]
    selected, fallback = candidates, 'all_days'
    for rows, name in ((exact, 'same_weekday'), (group, 'day_group'), (candidates, 'all_days')):
        if len({r['bucket'].date() for r in rows}) >= 8:
            selected, fallback = rows, name
            break
    result = {'base': None, 'conditional': None, 'historical': None, 'alpha': 0,
              'sample_days': len(selected), 'event_editions': 0, 'fallback': fallback,
              'reasons': ['calendar_unknown'] if holiday is None else []}
    if len(selected) < 8:
        result['reasons'].append('insufficient_history')
        return result
    weights = [2 ** (-(cutoff.date() - r['bucket'].date()).days / params['half_life']) for r in selected]
    result.update(base=weighted(selected, weights), arithmetic=mean(r['value'] for r in selected))
    target_weather = weather(data, target, cutoff, forecast=target > cutoff) if params['weather'] else None
    if params['weather'] and target_weather is None:
        result['reasons'].append('weather_unavailable')
    active, reasons = events(data, target, cutoff) if params['events'] else (None, [])
    result['reasons'].extend(reasons)
    historical_events = [events(data, r['bucket'], cutoff)[0] for r in selected]
    event_family = None
    if active and len(active) == 1:
        event_family = active[0]['family']
        if not any(es and len(es) == 1 and es[0]['family'] == event_family for es in historical_events):
            result['reasons'].append('event_unmodeled')
            event_family, active = None, None
    elif active and len(active) > 1:
        result['reasons'].append('multiple_events')
        active = None
    cond_rows, cond_weights, support = [], [], {}
    for row, weight, past_events in zip(selected, weights, historical_events):
        if event_family and (not past_events or len(past_events) != 1 or past_events[0]['family'] != event_family):
            continue
        if active == [] and past_events != []:
            continue
        sim = 1.0
        if target_weather:
            past = weather(data, row['bucket'], cutoff)
            if past is None:
                continue
            sim = math.exp(-abs(past[0] - target_weather[0]) / 5) * (1 if past[1] == target_weather[1] else .25)
        key = past_events[0]['edition'] if event_family else row['bucket'].date().isoformat()
        support[key] = max(support.get(key, 0), sim)
        cond_rows.append(row)
        cond_weights.append(weight * sim)
    # With no usable context this must be exactly the base, not a synthetic correction.
    if target_weather or active is not None:
        result['conditional'] = weighted(cond_rows, cond_weights)
        if result['conditional'] is not None:
            n = sum(support.values())
            result['alpha'] = n / (n + 8)
            result['event_editions'] = len(support) if event_family else 0
    result['historical'] = result['base'] if result['conditional'] is None else (
        (1 - result['alpha']) * result['base'] + result['alpha'] * result['conditional'])
    return result


def predict(data, issued_at, parameters=None):
    now = dt(issued_at)
    data = dict(data)
    data['_weather'], data['_calendar'] = {}, {}
    for row in data.get('weather', []):
        data['_weather'].setdefault(dt(row['at']), []).append(row)
    for row in data.get('calendar', []):
        data['_calendar'].setdefault(row['date'], []).append(row)
    if now.minute or now.second or now.microsecond:
        raise ValueError('Forecast issue must be an exact hour')
    params = {**DEFAULTS, **(parameters or {})}
    if not finite(params['half_life']) or params['half_life'] <= 0 or (
            params['tau'] is not None and (not finite(params['tau']) or params['tau'] <= 0)):
        raise ValueError('Invalid weights')
    rows = population(data.get('population', []), now)
    midnight = now.replace(hour=0)
    history = [r for r in hourly(rows) if midnight - timedelta(days=84) <= r['bucket'] < midnight]
    distribution = sorted(r['value'] for r in history)
    recent = {}
    for row in rows:
        if now - timedelta(minutes=30) < row['at'] <= now:
            key = int((now - row['at']).total_seconds() // 300)
            recent[key] = row
    delta, current_reasons = 0, []
    if params['tau'] is not None:
        if len(recent) < 3 or not rows or now - rows[-1]['at'] > timedelta(minutes=15):
            current_reasons.append('current_unavailable')
        else:
            differences = []
            for row in recent.values():
                b = baseline(data, history, row['at'], now, params)
                if b['historical'] is not None:
                    differences.append(row['value'] - b['historical'])
            if len(differences) >= 3:
                delta = mean(differences)
            else:
                current_reasons.append('current_baseline_unavailable')
    result = []
    for h in (1, 2, 3):
        target = now + timedelta(hours=h)
        b = baseline(data, history, target, now, params)
        correction = math.exp(-h / params['tau']) * delta if params['tau'] else 0
        value = max(0, b['historical'] + correction) if b['historical'] is not None else None
        def percentile(value):
            return 100 * (sum(v < value for v in distribution)+.5*sum(v == value for v in distribution))/len(distribution) if value is not None and distribution else None
        score = percentile(value)
        arithmetic_score = percentile(b.get('arithmetic'))
        week = next((r['value'] for r in history if r['bucket'] == target - timedelta(days=7)), None)
        result.append({**b, 'area_id': data['area_id'], 'issued_at': now.isoformat(),
            'valid_at': target.isoformat(), 'hours_ahead': h, 'population': value,
            'crowd_score': score, 'arithmetic_score': arithmetic_score, 'correction': correction, 'delta': delta,
            'parameters': params, 'model_version': VERSION, 'scope': 'area_population',
            'latest_observed_at': rows[-1]['at'].isoformat() if rows else None,
            'reasons': sorted(set(b['reasons'] + current_reasons)),
            'status': 'ok' if value is not None else 'insufficient_history',
            'comparisons': {'weekly': week, 'persistence': rows[-1]['value'] if rows and now-rows[-1]['at'] <= timedelta(minutes=15) else None,
                            'arithmetic': b.get('arithmetic'), 'recent': b['base'], 'conditional': b['historical']}})
    return result
