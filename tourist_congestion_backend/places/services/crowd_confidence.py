"""Evidence quality, never a calibrated probability of correctness."""
import math

FRESHNESS = {
    'population': (10, 15, 60), 'transit': (10, 10, 30),
    'weather': (90, 90, 240), 'event': (720, 1440, 4320),
    'calendar': (10080, 43200, 129600),
}


def clip(value, low=0.0, high=1.0):
    return max(low, min(high, value)) if math.isfinite(value) else low


def freshness(at, now, kind):
    if at is None:
        return 0.0
    age = (now - at).total_seconds() / 60
    if age < -2:
        return 0.0
    grace, half_life, ttl = FRESHNESS[kind]
    if age >= ttl:
        return 0.0
    return 1.0 if age <= grace else 2 ** (-(age - grace) / half_life)


def confidence(qp, qt, qe, qw, history, *, empirical=False, fresh_population=False,
               area_proxy=False, bootstrap=False):
    tier = 'A' if empirical and fresh_population and qp > 0 else (
        'B' if qp > 0 or qt > 0 or empirical else 'C')
    cap = {'A': .9, 'B': .65, 'C': .35}[tier]
    if area_proxy:
        cap = min(cap, .75)
    if bootstrap:
        cap = min(cap, .55)
    if not any((qp, qt, qe, qw)) and not empirical:
        cap = min(cap, .2)
    score = .10 + .55 * min(1, .8 * qp + .2 * qt) + .15 * (.6 * qw + .4 * qe) + .20 * history
    return tier, round(clip(score, 0, cap), 2)
