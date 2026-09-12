import math
from datetime import timedelta

from .crowd_confidence import confidence, freshness, clip
from .crowd_estimator import KST, event_effect, level, percentile, prior, rounded, weather_effect


def forecast(inputs, now, baseline_now, a, delta, history, current_confidence,
             history_reliability, qe, tier, *, trend_enabled=(True, True, True), observation_quality=(0,0)):
    from django.utils.dateparse import parse_datetime
    trend = 0
    if len(history) >= 4:
        elapsed = (parse_datetime(history[-1]['at'])-parse_datetime(history[0]['at'])).total_seconds()/3600
        if elapsed >= 1/3:
            trend = clip((history[-1].get('dnow',a*history[-1]['delta'])-history[0].get('dnow',a*history[0]['delta']))/elapsed, -10, 10)
    result = []
    for h in (1, 2, 3):
        at = (now+timedelta(hours=h)).astimezone(KST)
        baseline = inputs.get('baselines', {}).get((at.weekday(), at.hour))
        dist = inputs.get('distribution', [])
        empirical = bool(dist and baseline and baseline['sample_days'] >= 4)
        b = percentile(dist, baseline['median']) if empirical else prior(inputs.get('profile', 'unknown'), at, inputs.get('calendars', {}).get(at.date()))
        future_weather = inputs.get('forecast_weather', {}).get(h)
        w, quality = weather_effect(inputs.get('profile', 'unknown'), inputs.get('indoor_outdoor'), future_weather.get('values') if future_weather else None)
        qw = freshness(future_weather['issued_at'], now, 'weather')*quality if future_weather else 0
        future_qe = freshness(inputs.get('events_checked_at'), at, 'event')*inputs.get('event_coverage', 0)
        e = event_effect(inputs.get('events', []), inputs['latitude'], inputs['longitude'], at) if future_qe else 0
        ctx = baseline.get('context', {}) if empirical else {}
        context = clip(12*future_qe*(e-ctx.get('event', 0))+10*qw*(w-ctx.get('weather_'+inputs.get('profile', 'unknown'), ctx.get('weather', 0))), -20, 20)
        rho = math.exp(-h/1.5)
        value = b+rho*a*delta+.25*h*rho*trend*int(trend_enabled[h-1])+(1-a*rho)*context
        if not trend_enabled[h-1]:
            value = b+context
        score = rounded(value)
        # Evidence available when issuing the forecast, plus only valid future context.
        # The explicit horizon decay below is not a claim of fresh future observations.
        horizon_history = min(1, baseline['sample_days']/8)*baseline['coverage'] if empirical else .2
        _, horizon_conf = confidence(*observation_quality, future_qe, qw, horizon_history,
            empirical=empirical, fresh_population=tier=='A',
            area_proxy=inputs.get('mapping',{}).get('representativeness',1)<1,
            bootstrap=bool(inputs.get('population') and not dist))
        result.append({'hours_ahead': h, 'valid_at': at.isoformat(), 'crowd_score': score,
            'crowd_level': level(score)[0], 'confidence': round(min(current_confidence, horizon_conf)*math.exp(-.12*h), 2),
            'baseline_score': round(b, 2), 'weather_available': bool(qw),
            'baseline_fallback': not trend_enabled[h-1],
            'normalization': 'empirical_percentile' if empirical else 'heuristic_prior'})
    return result
