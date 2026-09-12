"""Pure heuristic model. No network, ORM, or synthetic observations."""
import bisect
import json
import math
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .crowd_confidence import clip, confidence, freshness

KST = ZoneInfo('Asia/Seoul')
MODEL_VERSION = 'heuristic-v1.1'
LEVELS = ('VERY_LOW', 'LOW', 'NORMAL', 'HIGH', 'VERY_HIGH')
LABELS = ('매우 여유', '여유', '보통', '혼잡', '매우 혼잡')
ANCHORS = {'relaxed': 15, 'normal': 45, 'busy': 70, 'crowded': 90}


@lru_cache(maxsize=1)
def profiles():
    return json.loads((Path(__file__).resolve().parents[1] / 'data/crowd_profiles.json').read_text(encoding='utf-8'))


def level(score):
    i = bisect.bisect_left((20, 40, 65, 85), score)
    return LEVELS[i], LABELS[i]


def rounded(value):
    return int(math.floor(clip(value, 0, 100) + .5))


def percentile(values, value):
    if not values:
        return None
    return 100 * (bisect.bisect_left(values, value) + bisect.bisect_right(values, value)) / (2 * len(values))


def profile_for(source, category=''):
    raw = source or {}
    config = profiles()
    classification = str(raw.get('lclsSystm3', ''))
    if classification in config.get('classification_categories', {}):
        return config['classification_categories'][classification]
    legacy = raw.get('cat3', '')
    if legacy in config['legacy_categories']:
        return config['legacy_categories'][legacy]
    content_type = str(raw.get('contenttypeid', raw.get('contentTypeId', '')))
    if not content_type:
        content_type = {'관광지': '12', '문화시설': '14', '레포츠': '28', '쇼핑': '38', '음식점': '39'}.get(category, '')
    return config['content_types'].get(content_type, 'unknown')


def prior(profile, at, calendar=None):
    at = at.astimezone(KST)
    c = profiles()
    values = c['profiles'].get(profile, c['profiles']['unknown'])
    hour = at.hour + at.minute / 60 + at.second / 3600
    i = bisect.bisect_right(c['hours'], hour) - 1
    score = values[i] + (values[i + 1] - values[i]) * (hour - c['hours'][i]) / (c['hours'][i + 1] - c['hours'][i])
    calendar = calendar or {}
    if at.weekday() >= 5 or calendar.get('is_holiday'):
        score += 8
    if calendar.get('holiday_run', 0) >= 3:
        score += 3
    if profile in ('day_visit', 'park', 'beach') and at.month in (1, 2, 7, 8):
        score += 2
    if profile == 'beach':
        score += 8 if at.month in (6, 7, 8) else -8 if at.month in (12, 1, 2) else 0
    return clip(score, 5, 85)


def distance_m(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(other_lat)
    x = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(other_lon-lon)/2)**2
    return 12742017.6 * math.asin(math.sqrt(clip(x)))


def event_effect(events, lat, lon, at):
    remaining, seen = 1.0, set()
    day = at.astimezone(KST).date()
    for event in events:
        if event['external_id'] in seen or not event.get('active', True):
            continue
        seen.add(event['external_id'])
        d = distance_m(lat, lon, event['latitude'], event['longitude'])
        if d > 2000:
            continue
        start, end = event.get('starts_at'), event.get('ends_at')
        if event.get('time_quality') == 'verified' and start and end and end >= start:
            tw = min(clip(1 + (at-start).total_seconds()/3600), clip(1 + (end-at).total_seconds()/3600))
        else:
            tw = .35 if event['start_date'] <= day <= event['end_date'] else 0
        size = .5
        if event.get('size_evidence') and event.get('size_valid_until') and event['size_valid_until'] >= day:
            size = clip(event.get('size_weight', .5))
        remaining *= 1 - size * math.exp(-d / 700) * tw
    return 1 - remaining


def weather_effect(profile, indoor_outdoor, values):
    if not values or 'temperature' not in values or 'precipitation_type' not in values:
        return 0.0, 0.0
    temp = values['temperature']
    rain = float(values['precipitation_type'] != 0 or values.get('precipitation_mm', 0) > 0)
    hot, cold = clip((temp-28)/7), clip((5-temp)/10)
    wind = clip((values.get('wind_speed', 0)-8)/7)
    if profile == 'shopping' and indoor_outdoor == 'indoor':
        return .2 * rain, 1.0
    if indoor_outdoor == 'indoor':
        return 0.0, 0.0
    quality = 1.0 if indoor_outdoor == 'outdoor' else .5
    if profile == 'beach':
        w = .4 * int(values.get('sky') == 1 and 24 <= temp <= 32) - .9*rain - .5*cold - .4*wind
    elif profile in ('park', 'day_visit'):
        w = -.8*rain - .3*hot - .3*cold - .3*wind
    else:
        return 0.0, 0.0
    # The inferred exposure coefficient is represented by qW, applied once in fusion.
    return clip(w, -1, 1), quality


def opening_status(schedule, at, fallback=None):
    """Only a reviewed structured weekly schedule can override operating status."""
    local = at.astimezone(KST)
    if not schedule.get('verified') or not schedule.get('evidence') or schedule.get('valid_until','') < local.date().isoformat():
        return fallback
    periods = schedule.get('weekdays', {}).get(str(local.weekday()))
    if periods is None:
        return fallback
    try:
        ranges=[]
        for start,end in periods:
            sh,sm=map(int,start.split(':')); eh,em=map(int,end.split(':'))
            if not (0<=sh<24 and 0<=sm<60 and 0<=eh<=24 and 0<=em<60 and (eh<24 or em==0)):
                return fallback
            lo,hi=sh*60+sm,eh*60+em
            if hi<lo:
                return fallback  # Overnight ranges must be reviewed/split at midnight.
            ranges.append((lo,hi))
        minute=local.hour*60+local.minute
        return 'OPEN' if any(lo<=minute<hi for lo,hi in ranges) else 'CLOSED'
    except (ValueError,TypeError):
        return fallback


def ewma(delta, observed_at, previous, now):
    if not observed_at:
        return 0.0, [], None
    history = list(previous.get('history', [])) if previous else []
    stamp = observed_at.isoformat()
    if history and history[-1]['at'] == stamp:
        return history[-1]['delta'], history, stamp
    from django.utils.dateparse import parse_datetime
    if history:
        last = parse_datetime(history[-1]['at'])
        gap = (observed_at-last).total_seconds()/60
        if gap <= 0:
            return history[-1]['delta'], history, history[-1]['at']
        if gap >= 30:
            history = []
        else:
            alpha = 1 - 2**(-gap/10)
            delta = alpha*delta + (1-alpha)*history[-1]['delta']
    history.append({'at': stamp, 'delta': delta})
    # Providers may publish a whole series late. Keep its source-time window;
    # observation freshness is independently discounted in qP/qT.
    history = [p for p in history if 0 <= (observed_at-parse_datetime(p['at'])).total_seconds() <= 1800]
    return delta, history, stamp


def estimate(inputs, now, previous=None, *, trend_enabled=(True, True, True)):
    """inputs are normalized evidence dictionaries, at or before now."""
    local = now.astimezone(KST)
    profile = inputs.get('profile', 'unknown')
    calendar = inputs.get('calendars', {})
    baselines = inputs.get('baselines', {})
    distribution = inputs.get('distribution', [])
    baseline = baselines.get((local.weekday(), local.hour))
    empirical = bool(distribution and baseline and baseline['sample_days'] >= 4)
    b = percentile(distribution, baseline['median']) if empirical else prior(profile, now, calendar.get(local.date()))
    population = inputs.get('population')
    mapping = inputs.get('mapping') or {}
    qp, dp, ratio, popscore = 0.0, 0.0, None, None
    normalization = 'empirical_percentile' if empirical else 'heuristic_prior'
    if population and not population.get('is_replaced') and not inputs.get('is_demo'):
        qp = freshness(population['observed_at'], now, 'population') * mapping.get('match_quality', 0) * mapping.get('representativeness', 0)
        if distribution:
            popscore = percentile(distribution, population['value'])
            if qp:
                normalization = 'empirical_percentile'
            if empirical and baseline['median'] >= 10 and qp:
                ratio = round(population['value']/baseline['median'], 2)
        elif population.get('level') in ANCHORS:
            popscore = ANCHORS[population['level']]
            qp = min(qp, .45)
            if qp:
                normalization = 'provider_category_bootstrap'
        else:
            qp = 0
        if qp and popscore is not None:
            dp = popscore-b
    qt, dt = 0.0, 0.0
    used_transit = []
    for transit in inputs.get('transit', []):
        mu = transit.get('baseline', 0)
        if mu < 10 or transit.get('sample_days', 0) < 4:
            continue
        q = freshness(transit['observed_at'], now, 'transit') * mapping.get('match_quality', 0) * mapping.get('representativeness', 0)
        q *= 1.0 if transit.get('timestamp_quality') == 'source' else .6
        if q:
            delta = 15*math.tanh(math.log(clip(transit['value']/mu, .25, 4))/math.log(2))
            used_transit.append((q, delta, transit['observed_at']))
    if used_transit and not inputs.get('is_demo'):
        qt = sum(q for q, _, _ in used_transit)/len(used_transit)
        dt = sum(q*d for q, d, _ in used_transit)/sum(q for q, _, _ in used_transit)
    qe = freshness(inputs.get('events_checked_at'), now, 'event') * inputs.get('event_coverage', 0)
    events = inputs.get('events', [])
    e = event_effect(events, inputs['latitude'], inputs['longitude'], now) if qe else 0
    weather = inputs.get('weather')
    w, wq = weather_effect(profile, inputs.get('indoor_outdoor'), weather.get('values') if weather else None)
    qw = freshness(weather['issued_at'], now, 'weather') * wq if weather else 0
    ctx_base = baseline.get('context', {}) if empirical else {}
    ec = 12*qe*(e-ctx_base.get('event', 0))
    wc = 10*qw*(w-ctx_base.get('weather_'+profile, ctx_base.get('weather', 0)))
    context = clip(ec+wc, -20, 20)
    up, ut = .8*qp, .2*qt
    delta = (up*dp+ut*dt)/(up+ut) if up+ut else 0
    a = min(.9, .85*qp+.30*qt)
    times = ([population['observed_at']] if qp else []) + [t for _, _, t in used_transit if qt]
    observed_at = max(times) if times else None
    # Never blend EWMA state across a changed baseline or a changed mapping.
    state_key = ':'.join(str(x) for x in (inputs.get('baseline_version', ''), mapping.get('area_id'),
        mapping.get('geometry_version'), mapping.get('match_quality'), mapping.get('representativeness'),
        inputs.get('profile_version', profiles()['version']), profile, normalization))
    if previous and previous.get('state_key') != state_key:
        previous = None
    smoothed, history, stamp = ewma(delta, observed_at, previous, now)
    raw_score = b+a*smoothed+(1-a)*context
    score = rounded(raw_score)
    code, label = level(score)
    history_reliability = min(1, baseline['sample_days']/8)*baseline['coverage'] if empirical else .2
    tier, conf = confidence(qp, qt, qe, qw, history_reliability, empirical=empirical,
        fresh_population=bool(population and freshness(population['observed_at'], now, 'population') == 1),
        area_proxy=mapping.get('representativeness', 1)<1,
        bootstrap=normalization == 'provider_category_bootstrap')
    from .crowd_forecast import forecast
    new_observation = not previous or previous.get('observation_at') != stamp
    if new_observation and history:
        history[-1]['dnow'] = a*smoothed
    fresh_history = history if new_observation and observed_at and (now-observed_at).total_seconds() <= 600 else []
    forecasts = forecast(inputs, now, b, a, smoothed, fresh_history, conf, history_reliability,
                         qe, tier, trend_enabled=trend_enabled, observation_quality=(qp,qt))
    factors = [
        {'key': 'baseline', 'available': True, 'contribution_points': round(b, 2),
         'description': '같은 요일·시간의 관측 기준선' if empirical else '관광지 유형·시간·휴일·계절에 따른 초기 가정' +
             (' (방학 시즌 가정 포함)' if profile in ('day_visit','park','beach') and local.month in (1,2,7,8) else '')},
        {'key': 'population', 'available': qp>0, 'contribution_points': round(a*up*dp/(up+ut), 2) if up+ut else 0,
         'description': '관광지 주변 영역의 체류 인구를 반영합니다.'},
        {'key': 'transit', 'available': qt>0, 'contribution_points': round(a*ut*dt/(up+ut), 2) if up+ut else 0,
         'description': '주변 영역의 최근 30분 하차량을 평소와 비교합니다.'},
        {'key': 'smoothing', 'available': bool(times), 'contribution_points': round(a*(smoothed-delta), 2),
         'description': '최근 관측 변화의 일시적인 흔들림을 완화합니다.'},
        {'key': 'event', 'available': qe>0, 'contribution_points': round((1-a)*ec, 2),
         'description': 'KTO 주변 행사 정보입니다. 날짜만 확인된 행사는 약하게 반영합니다.'},
        {'key': 'weather', 'available': qw>0, 'contribution_points': round((1-a)*wc, 2),
         'description': '실내외 유형을 추론한 날씨 영향은 절반만 반영합니다.' if wq==.5 else '관광지 유형에 따른 날씨 영향을 반영합니다.'},
    ]
    factors.append({'key': 'bounds', 'available': True, 'contribution_points': round(score-sum(f['contribution_points'] for f in factors), 2), 'description': '점수 범위 제한과 반올림'})
    limits = ['RELATIVE_LEVEL_NOT_PHYSICAL_DENSITY', 'CONFIDENCE_IS_EVIDENCE_QUALITY']
    if mapping:
        limits.append('AREA_POPULATION_IS_NOT_PLACE_VISITOR_COUNT')
    if tier == 'C':
        limits.append('HEURISTIC_PRIOR_NOT_OBSERVED_VISITS')
    if not calendar.get(local.date()):
        limits.append('PUBLIC_HOLIDAY_UNCONFIRMED')
    if profile in ('day_visit', 'park', 'beach') and local.month in (1, 2, 7, 8):
        limits.append('SCHOOL_VACATION_SEASON_ASSUMPTION')
    evidence_dates = times + ([weather['issued_at']] if qw else []) + ([inputs['events_checked_at']] if qe else [])
    stale = bool(population and freshness(population['observed_at'], now, 'population')<1
                 or weather and freshness(weather['issued_at'], now, 'weather')<1
                 or inputs.get('events_checked_at') and freshness(inputs['events_checked_at'], now, 'event')<1)
    return {
        'place_id': inputs['place_id'], 'status': 'available', 'crowd_score': score,
        'crowd_level': code, 'crowd_label': label, 'tier': tier, 'confidence': conf,
        'confidence_kind': 'evidence_quality', 'normalization': normalization,
        'estimate_kind': 'observation_assisted' if qp or qt else 'historical_based' if empirical else 'prior_based',
        'estimated_at': local.isoformat(), 'data_as_of': min(evidence_dates).astimezone(KST).isoformat() if evidence_dates else None,
        'is_stale': stale, 'is_demo': inputs.get('is_demo', False),
        'open_status': opening_status(inputs.get('opening_schedule',{}), now, inputs.get('open_status')),
        'spatial_scope': {'type': 'area_proxy' if mapping else 'place_prior', **mapping},
        'relative_to_normal': ratio, 'relative_to_normal_scope': 'source_area' if ratio is not None else None,
        'estimated_visitors': None,
        'source_population': {'min': population['min'], 'max': population['max'], 'kind': 'provider_estimated_population', 'scope': 'source_area'} if population else None,
        'factors': factors, 'sources': inputs.get('sources', []) + ([{'provider':'model_prior','role':'assumption','version':profiles()['version']}] if not empirical else []), 'forecast': forecasts,
        'limitations': limits, 'model_version': MODEL_VERSION,
        'profile_version': inputs.get('profile_version', profiles()['version']),
        'baseline_version': inputs.get('baseline_version') if empirical else profiles()['version'],
    }, {'state_key': state_key, 'history': history, 'observation_at': stamp}
