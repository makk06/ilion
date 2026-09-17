"""Pure 30-day event experiment. No provider calls, DB, or promotion side effects."""
import math
from datetime import timedelta
from statistics import mean
from .hourly_forecast import predict, samples, baseline, validate_identity, dt
from .event_rules import overlaps

VERSION = 'hourly-event-30day-v1'
PARAMETERS = {'half_life': None, 'tau': 3}


def history(points, at):
    midnight = dt(at).replace(hour=0, minute=0, second=0, microsecond=0)
    return {t: r for t, r in points.items() if midnight-timedelta(days=30) <= t < midnight}


def effect(data, points, events, at, cutoff):
    frozen = data.get('event_effects', {}).get(dt(at).isoformat())
    if frozen is not None:
        return frozen['value'], frozen['reason'], frozen['editions']
    active = [e for e in events if overlaps(e, at)]
    if not active:
        return 0, 'no_registered_event', []
    if len(active) != 1:
        return 0, 'overlapping_events', []
    event = active[0]
    if 'allowed_families' in data and event.get('family') not in data['allowed_families']:
        return 0, 'event_family_not_selected', []
    if not event.get('starts_at') or not event.get('ends_at'):
        return 0, 'event_time_unknown', []
    if not event.get('family') or not event.get('edition'):
        return 0, 'event_identity_unverified', []
    bucket = int((dt(at)-dt(event['starts_at'])).total_seconds()//3600)
    editions = {}
    for old in events:
        if (old.get('family') != event['family'] or not old.get('edition') or old['edition'] == event['edition']
                or not old.get('starts_at') or not old.get('ends_at') or dt(old['ends_at']) >= cutoff
                or dt(old['starts_at']) < cutoff-timedelta(days=400)):
            continue
        for t, point in points.items():
            if not (dt(old['starts_at']) <= t < dt(old['ends_at'])):
                continue
            if int((t-dt(old['starts_at'])).total_seconds()//3600) != bucket:
                continue
            # Never learn from overlapping events, even if their family is different.
            if sum(overlaps(other, t) for other in events) != 1:
                continue
            b = baseline(history(points, t), t, t, data.get('calendar', {}), None)['base']
            if b is not None:
                editions.setdefault(old['edition'], {})[t] = point['value']-b
    count = len(editions)
    if count < 3:
        return 0, 'insufficient_event_editions', sorted(editions)
    return mean(mean(values.values()) for values in editions.values())*count/(count+8), 'event_adjusted', sorted(editions)


def predict_events(data, issued_at, events, parameters=None):
    validate_identity(data)
    now = dt(issued_at)
    params = {**PARAMETERS, **(parameters or {})}
    if params['half_life'] is not None:
        raise ValueError('Event v1 uses an unweighted 30-day baseline')
    known = []
    for e in events:
        if any(e.get(k) != data[k] for k in ('provider', 'external_id', 'metric')):
            raise ValueError('Mixed event identity')
        if e.get('verified') and dt(e['received_at']) <= now and e.get('status') == 'scheduled':
            known.append(e)
    points = samples(data, now)
    current = points.get(now)
    current_base = baseline(history(points, now), now, now, data.get('calendar', {}), None)['base']
    current_effect, current_reason, _ = effect(data, points, known, now, now)
    results = predict(data, now, params, history_days=30)
    distribution = sorted(r['value'] for r in history(points, now).values())
    for r in results:
        extra, reason, editions = effect(data, points, known, dt(r['valid_at']), now)
        residual = current['value']-current_base-current_effect if current and current_base is not None else 0
        correction = math.exp(-r['hours_ahead']/params['tau'])*residual if params['tau'] else 0
        value = max(0, r['base']+extra+correction) if r['base'] is not None else None
        r.update(unadjusted_value=r['value'], value=value, population=value if data['metric']=='population_count' else None,
            event_adjustment=extra, current_event_adjustment=current_effect, correction=correction, delta=residual,
            event_reason=reason, current_event_reason=current_reason, event_editions=editions,
            model_version=VERSION, decision_contract_version='relative-choice-v2',
            crowd_score=100*(sum(v<value for v in distribution)+.5*sum(v==value for v in distribution))/len(distribution) if value is not None and distribution else None)
    return results
