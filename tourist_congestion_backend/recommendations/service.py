import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from places.models import Place, PlaceCrowdArea, PlaceInfo
from places.views import _haversine_km, _nearby_bounding_box, _visible_places
from places.services.weather import forecast_for, forecasts_for, grid_for, latest_available_issue
from places.services.jobs import enqueue
from places.job_models import DataJob
from places.services.weather import KST
from places.services.classification import current_description_evidence, name_decision
from places.services.weather_exposure import (
    TYPE_PRIOR_FACTOR, exposure_for, source_codes_for, veto_ids_for,
)


ALGORITHM_VERSION = 'mvp-7'
MVP_CATEGORIES = {'관광지', '문화시설', '축제/공연/행사', '레포츠', '쇼핑', '음식점'}
CROWD_FIT = {
    'relaxed': {'relaxed': 100, 'normal': 65, 'busy': 25, 'crowded': 0},
    'normal': {'relaxed': 70, 'normal': 100, 'busy': 65, 'crowded': 20},
    'busy': {'relaxed': 20, 'normal': 70, 'busy': 100, 'crowded': 60},
    'crowded': {'relaxed': 0, 'normal': 30, 'busy': 70, 'crowded': 100},
    'any': {'relaxed': 100, 'normal': 100, 'busy': 80, 'crowded': 30},
}
# With no stated preference, a verified busy observation is a modest warning.
# Sparse Seoul coverage must not reward the few observed quiet places by default.
DEFAULT_CROWD_RISK = {'relaxed': 50, 'normal': 50, 'busy': 40, 'crowded': 25}
NEUTRAL_RANKING_BASELINE = 50
DEFAULT_TRAVEL_CATEGORY_FIT = {
    '관광지': 90, '문화시설': 90, '축제/공연/행사': 85,
    '레포츠': 85, '음식점': 60, '쇼핑': 45,
}
DEFAULT_CATEGORY_REASONS = {
    '관광지': '관광지로 등록된 장소입니다.',
    '문화시설': '문화시설로 등록된 장소입니다.',
    '축제/공연/행사': '방문일에 진행되는 행사로 등록된 장소입니다.',
    '레포츠': '레포츠 장소로 등록된 곳입니다.',
    '음식점': '주변 음식점으로 등록된 장소입니다.',
    '쇼핑': '주변 쇼핑 장소로 등록된 곳입니다.',
}


_CANDIDATE_FIELDS = (
    'id', 'name', 'category', 'subcategory', 'address', 'latitude', 'longitude',
    'indoor_outdoor', 'indoor_outdoor_source', 'indoor_outdoor_evidence', 'open_status',
    'info__description',
    'classification_record__label', 'classification_record__method',
    'classification_record__version', 'classification_record__input_hash',
    'classification_record__quote', 'classification_record__span_start',
    'classification_record__span_end', 'classification_record__evidence_quotes',
    'classification_record__primary_activity', 'classification_record__scope',
    'classification_record__ancillary_note', 'classification_record__rationale',
    'classification_record__weather_exposure', 'classification_record__weather_activity',
    'classification_record__weather_reason',
    'weather_exposure_record__level', 'weather_exposure_record__activity',
    'weather_exposure_record__source', 'weather_exposure_record__reason',
    'weather_exposure_record__conflict', 'weather_exposure_record__conflict_reason',
    'weather_exposure_record__type_code', 'weather_exposure_record__type_name',
    'weather_exposure_record__factor', 'weather_exposure_record__version',
    'weather_exposure_record__input_hash',
)


@dataclass(slots=True)
class PreparedRecommendations:
    now: datetime
    visit_at: datetime
    scope: tuple
    required_indoor_outdoor: object
    candidates: list
    classification_qualities: dict
    weather_profiles: dict
    grids: dict
    forecasts: dict


@dataclass(slots=True)
class _CandidateEvaluation:
    distance: float
    place: object
    crowd: object
    classification_quality: str
    profile: object
    forecast: object
    weather_fit: object
    weather_factors: list
    weather_status: str
    raw_scores: dict
    evidence_factors: dict
    rank_score: float = 0


def _event_valid_at(raw_data, visit_at):
    intro = raw_data.get('intro') if isinstance(raw_data, dict) else None
    if not isinstance(intro, dict):
        return False
    try:
        start = datetime.strptime(str(intro['eventstartdate']), '%Y%m%d').date()
        end = datetime.strptime(str(intro['eventenddate']), '%Y%m%d').date()
    except (KeyError, TypeError, ValueError):
        return False
    return start <= visit_at.astimezone(KST).date() <= end


def _classification_quality(place):
    if place.indoor_outdoor == Place.IndoorOutdoor.UNKNOWN:
        return 'unknown', 0
    if place.indoor_outdoor_source == 'manual':
        return 'manual_label', 1
    if place.indoor_outdoor_source.startswith('reviewed_name_rule_'):
        decision = name_decision(place)
        if decision and decision[0] == place.indoor_outdoor and (
            decision[1] == place.indoor_outdoor_source or (
                place.indoor_outdoor_source == 'reviewed_name_rule_v1' and
                decision[2] == place.indoor_outdoor_evidence
            ) or (
                place.indoor_outdoor_source == 'reviewed_name_rule_v2' and
                decision[1] == 'reviewed_name_rule_v5' and
                decision[2] == place.indoor_outdoor_evidence
            )
        ):
            return 'inferred_from_name', settings.RECOMMENDATION_NAME_RULE_WEIGHT_FACTOR
        return 'stale_auto_evidence', 0
    if place.indoor_outdoor_source in {'description_rule', 'luna_validated'}:
        record = current_description_evidence(place)
        if record is None:
            return 'stale_auto_evidence', 0
        if record.method == 'description_rule':
            return 'inferred_from_description', settings.RECOMMENDATION_DESCRIPTION_RULE_WEIGHT_FACTOR
        return 'inferred_from_luna', settings.RECOMMENDATION_LUNA_VALIDATED_WEIGHT_FACTOR
    # A filled label with no provenance is not proof of exposure.
    return 'unattributed', 0


def _weather_fit(profile, forecast):
    if forecast is None or not profile.factor:
        return None, [], 'unavailable'
    factors = []
    if forecast.precipitation_type is not None and forecast.precipitation_type > 0:
        factors.append('rain_or_snow')
    if forecast.wind_mps is not None and forecast.wind_mps >= settings.WEATHER_THRESHOLDS['wind_mps']:
        factors.append('strong_wind')
    if forecast.temperature_c is not None:
        if forecast.temperature_c >= settings.WEATHER_THRESHOLDS['hot_c']:
            factors.append('hot')
        elif forecast.temperature_c <= settings.WEATHER_THRESHOLDS['cold_c']:
            factors.append('cold')
    complete = all(getattr(forecast, field) is not None for field in (
        'precipitation_type', 'wind_mps', 'temperature_c'))
    if not complete and not factors:
        # A benign value in just one field cannot establish favorable weather.
        return None, [], 'partial_uninformative'
    if complete:
        outdoor = max(0, 85 - 35 * len(factors))
        indoor = 95 if factors else 65
    else:
        # Partial forecasts only contribute a known hazard, never fair weather.
        outdoor = max(0, 50 - 35 * len(factors))
        indoor = 85
    if profile.level == 'low':
        return indoor, factors, 'complete' if complete else 'partial_hazard'
    if profile.level == 'medium':
        return (indoor + outdoor) / 2, factors, 'complete' if complete else 'partial_hazard'
    if profile.level == 'high':
        return outdoor, factors, 'complete' if complete else 'partial_hazard'
    return None, factors, 'unavailable'


def _profiles_for_candidates(candidates):
    ids = [place.id for _, place in candidates]
    codes = source_codes_for(ids)
    veto_ids = veto_ids_for(ids)
    return {place.id: exposure_for(place, codes.get(place.id, ()),
                                   veto=place.id in veto_ids)
            for _, place in candidates}


def _crowd(place, visit_at, now):
    observed = place.latest_crowd_observed_at
    # Current observation is evidence only for a visit effectively now.
    if observed is None or abs((visit_at - now).total_seconds()) > 300:
        return None
    age = (now - observed).total_seconds()
    if age < 0 or age > settings.CROWD_MAX_AGE_MINUTES * 60 or place.latest_crowd_level not in CROWD_FIT['any']:
        return None
    is_delayed = age > settings.CROWD_FULL_WEIGHT_MINUTES * 60
    return {
        'type': 'delayed_observation' if is_delayed else 'realtime',
        'level': place.latest_crowd_level,
        'source': place.latest_crowd_source, 'observed_at': observed,
        'is_stale': age > settings.CROWD_FRESH_MINUTES * 60,
        'is_delayed': is_delayed,
        'score_weight_factor': settings.CROWD_DELAYED_WEIGHT_FACTOR if is_delayed else 1.0,
    }


def _context_scope(criteria, visit_at):
    return (
        float(criteria['latitude']), float(criteria['longitude']),
        float(criteria['radius_km']), visit_at,
        tuple(sorted(criteria.get('required_categories') or ())),
    )


def _with_candidate_data(queryset):
    return queryset.select_related(
        'classification_record', 'info', 'weather_exposure_record',
    ).only(*_CANDIDATE_FIELDS)


def _load_candidates(criteria, visit_at):
    lat, lon = criteria['latitude'], criteria['longitude']
    radius = criteria['radius_km']
    lat_min, lat_max, lon_min, lon_max = _nearby_bounding_box(lat, lon, radius)
    queryset = _visible_places().filter(
        category__in=MVP_CATEGORIES,
        latitude__gte=lat_min, latitude__lte=lat_max,
        longitude__gte=lon_min, longitude__lte=lon_max,
    ).exclude(open_status=Place.OpenStatus.CLOSED)
    required_categories = criteria.get('required_categories') or []
    if required_categories:
        queryset = queryset.filter(category__in=required_categories)
    if criteria.get('required_indoor_outdoor'):
        queryset = queryset.filter(indoor_outdoor=criteria['required_indoor_outdoor']).exclude(
            indoor_outdoor_source='')
    queryset = _with_candidate_data(queryset)
    valid_event_ids = {
        place_id for place_id, raw_data in PlaceInfo.objects.filter(
            place__category='축제/공연/행사',
            place__latitude__gte=lat_min, place__latitude__lte=lat_max,
            place__longitude__gte=lon_min, place__longitude__lte=lon_max,
        ).values_list('place_id', 'raw_data')
        if _event_valid_at(raw_data, visit_at)
    }
    candidates = []
    classification_qualities = {}
    for place in queryset:
        if place.category == '축제/공연/행사' and place.id not in valid_event_ids:
            continue
        if criteria.get('required_indoor_outdoor'):
            quality = _classification_quality(place)
            classification_qualities[place.id] = quality
            if quality[0] not in {'manual_label', 'inferred_from_description'}:
                continue
        distance = _haversine_km(lat, lon, place)
        if distance <= radius:
            candidates.append((distance, place))
    candidates.sort(key=lambda item: (item[0], item[1].id))
    return candidates, classification_qualities


def prepare_recommendations(criteria, *, now=None, supplement=True):
    """Hydrate request-invariant recommendation inputs once for one or more rankings."""
    now = now or timezone.now()
    visit_at = criteria.get('visit_at') or now
    candidates, classification_qualities = _load_candidates(criteria, visit_at)
    weather_profiles = _profiles_for_candidates(candidates)
    if supplement:
        jobs = _prepare_jobs(
            candidates, visit_at, now,
            weather_requested=(criteria.get('weather_aware', True)
                               or bool(criteria.get('weather_evidence_required'))),
            crowd_requested=True,
            weather_profiles=weather_profiles,
        )
        if _wait_for_running_jobs(jobs):
            refreshed = {
                place.id: place for place in _with_candidate_data(
                    _visible_places().filter(id__in=[place.id for _, place in candidates])
                )
            }
            candidates = [(distance, refreshed.get(place.id, place))
                          for distance, place in candidates]
            classification_qualities = {}
            weather_profiles = _profiles_for_candidates(candidates)
    for _, place in candidates:
        classification_qualities.setdefault(place.id, _classification_quality(place))
    grids = {
        place.id: grid_for(place.latitude, place.longitude) if weather_profiles[place.id].factor else None
        for _, place in candidates
    }
    return PreparedRecommendations(
        now=now,
        visit_at=visit_at,
        scope=_context_scope(criteria, visit_at),
        required_indoor_outdoor=criteria.get('required_indoor_outdoor'),
        candidates=candidates,
        classification_qualities=classification_qualities,
        weather_profiles=weather_profiles,
        grids=grids,
        forecasts=forecasts_for(
            {grid for grid in grids.values() if grid is not None}, visit_at, now,
        ),
    )


def _prepare_jobs(candidates, visit_at, now, *, weather_requested=False,
                  crowd_requested=False, weather_profiles=None):
    if weather_requested and weather_profiles is None:
        hydrated = Place.objects.filter(id__in=[place.id for _, place in candidates]).select_related(
            'info', 'classification_record', 'weather_exposure_record').in_bulk()
        weather_profiles = _profiles_for_candidates([
            (distance, hydrated.get(place.id, place)) for distance, place in candidates])
    weather_collectible = weather_requested and now - timedelta(hours=1) <= visit_at <= now + timedelta(days=5)
    issue = latest_available_issue(now, target_at=visit_at) if weather_collectible else None
    pending = []
    # Limit supplementary work to the nearest distinct grids/areas. The worker owns provider calls.
    seen_grids = set()
    seen_areas = set()
    # The crowd annotation covers places with observations. For newly mapped
    # places, one lookup supplies IDs without a query per nearby candidate.
    mapped_areas = {}
    if crowd_requested:
        mappings = PlaceCrowdArea.objects.filter(
            place_id__in=[place.id for _, place in candidates[:100]],
            crowd_area__source='seoul_realtime',
        ).select_related('crowd_area').order_by('place_id', 'id')
        for mapping in mappings:
            mapped_areas.setdefault(mapping.place_id, mapping.crowd_area.external_id)
    # Candidate rows are already in memory. Unknown venues cannot starve a
    # classified venue beyond an arbitrary distance-rank cutoff.
    for index, (_, place) in enumerate(candidates):
        if index >= 100 and (not weather_requested or len(seen_grids) >= 5):
            break
        # The weather profile is independent of the compatibility label.
        if (weather_collectible and len(seen_grids) < 5 and weather_profiles and
            weather_profiles[place.id].factor):
            grid = grid_for(place.latitude, place.longitude)
            if grid and grid not in seen_grids and len(seen_grids) < 5:
                seen_grids.add(grid)
                stored_forecast = forecast_for(grid, visit_at, now)
                if stored_forecast is None or stored_forecast.issued_at < issue:
                    pending.append(enqueue('weather', f'{grid[0]}:{grid[1]}',
                        payload={'grid': grid, 'issued_at': issue.isoformat(),
                                 'target_at': visit_at.isoformat()}, lane='supplemental',
                        window=issue.strftime('%Y%m%d%H')))
        if crowd_requested and index < 100:
            area_id = place.latest_crowd_area_external_id or mapped_areas.get(place.id)
            if area_id and area_id not in seen_areas:
                seen_areas.add(area_id)
                if _crowd(place, visit_at, now) is None and abs((visit_at - now).total_seconds()) <= 300:
                    pending.append(enqueue('seoul_crowd', area_id,
                        lane='supplemental', window=now.strftime('%Y%m%d%H') + str(now.minute // 5)))
    return pending


def _wait_for_running_jobs(jobs):
    active_ids = [job.id for job in jobs if job.status == DataJob.Status.RUNNING]
    if not active_ids:
        return False
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not DataJob.objects.filter(id__in=active_ids, status=DataJob.Status.RUNNING).exists():
            return True
        time.sleep(min(.1, max(0, deadline - time.monotonic())))
    return False


def recommend(criteria, user=None, *, now=None, supplement=True, forecast_lookup=None,
              prepared=None):
    now = now or (prepared.now if prepared is not None else timezone.now())
    visit_at = criteria.get('visit_at') or now
    if prepared is None:
        prepared = prepare_recommendations(criteria, now=now, supplement=supplement)
    elif (prepared.scope != _context_scope(criteria, visit_at)
          or (prepared.required_indoor_outdoor is not None
              and prepared.required_indoor_outdoor != criteria.get('required_indoor_outdoor'))):
        raise ValueError('prepared recommendation scope does not match criteria')
    preferred_categories = [criteria['category']] if criteria.get('category') else (
        user.preferred_categories or [] if user and user.is_authenticated else [])
    preference_source = ('request' if criteria.get('category') else
                         'profile' if preferred_categories else 'default_travel_intent')
    forecast_cache = {} if forecast_lookup is not None else prepared.forecasts
    evaluations = []
    crowd_can_rank = False
    weather_can_rank = False
    indoor_outdoor_can_rank = False
    for distance, place in prepared.candidates:
        classification_quality, classification_factor = prepared.classification_qualities[place.id]
        if criteria.get('required_indoor_outdoor') and (
            place.indoor_outdoor != criteria['required_indoor_outdoor']
            or not place.indoor_outdoor_source
            or classification_quality not in {'manual_label', 'inferred_from_description'}
        ):
            continue
        crowd = _crowd(place, visit_at, now)
        if criteria.get('quiet_required') and (
            crowd is None or crowd['is_delayed'] or crowd['level'] != 'relaxed'
        ):
            continue
        profile = prepared.weather_profiles[place.id]
        # Type priors may score weather weakly without claiming an indoor or
        # outdoor label. Nearby places share a forecast grid.
        forecast = None
        if profile.factor:
            grid = prepared.grids[place.id]
            if forecast_lookup is not None and grid not in forecast_cache:
                forecast_cache[grid] = forecast_lookup(grid, visit_at, now)
            forecast = forecast_cache.get(grid)
        weather_fit, weather_factors, weather_status = _weather_fit(profile, forecast)
        if criteria.get('weather_evidence_required') and (
            weather_fit is None or profile.source == 'type_prior'
        ):
            continue
        if criteria['crowd_level'] == 'any':
            crowd_fit = DEFAULT_CROWD_RISK[crowd['level']] if crowd else None
        else:
            crowd_fit = CROWD_FIT[criteria['crowd_level']][crowd['level']] if crowd else None
        raw_scores = {
            'distance': 100 / (1 + distance / settings.RECOMMENDATION_DISTANCE_SCALE_KM),
            'category': (100 if place.category in preferred_categories else 0)
            if preferred_categories else DEFAULT_TRAVEL_CATEGORY_FIT[place.category],
            'crowd': crowd_fit,
            'weather': weather_fit,
            'indoor_outdoor': (
                100 if place.indoor_outdoor == criteria['indoor_outdoor'] else
                60 if place.indoor_outdoor == 'mixed' else 0
            ) if criteria.get('indoor_outdoor') and classification_factor else None,
        }
        evidence_factors = {
            'distance': 1, 'category': 1,
            'crowd': crowd['score_weight_factor'] if crowd else 0,
            'weather': profile.factor,
            'indoor_outdoor': classification_factor,
        }
        crowd_can_rank |= crowd_fit is not None and (
            criteria['crowd_level'] != 'any' or crowd_fit < NEUTRAL_RANKING_BASELINE
        )
        weather_can_rank |= weather_fit is not None
        indoor_outdoor_can_rank |= raw_scores['indoor_outdoor'] is not None
        evaluations.append(_CandidateEvaluation(
            distance=distance,
            place=place,
            crowd=crowd,
            classification_quality=classification_quality,
            profile=profile,
            forecast=forecast,
            weather_fit=weather_fit,
            weather_factors=weather_factors,
            weather_status=weather_status,
            raw_scores=raw_scores,
            evidence_factors=evidence_factors,
        ))
    ranking_keys = ['distance', 'category']
    if crowd_can_rank:
        ranking_keys.append('crowd')
    if criteria.get('weather_aware', True) and weather_can_rank:
        ranking_keys.append('weather')
    if criteria.get('indoor_outdoor') and indoor_outdoor_can_rank:
        ranking_keys.append('indoor_outdoor')
    weights = settings.RECOMMENDATION_WEIGHTS
    ranking_total = sum(weights[key] for key in ranking_keys)
    for evaluation in evaluations:
        raw_scores = evaluation.raw_scores
        factors = evaluation.evidence_factors
        effective_scores = {
            key: (NEUTRAL_RANKING_BASELINE + (value - NEUTRAL_RANKING_BASELINE) * factors[key])
            if value is not None else None
            for key, value in raw_scores.items()
        }
        score = sum(weights[key] * (
            effective_scores[key] if effective_scores[key] is not None else NEUTRAL_RANKING_BASELINE
        ) for key in ranking_keys) / ranking_total
        guard = 1 / (1 + max(0, evaluation.distance - settings.RECOMMENDATION_DISTANCE_GUARD_FREE_KM)
                     / settings.RECOMMENDATION_DISTANCE_GUARD_SCALE_KM)
        evaluation.rank_score = score * guard
    crowd_ranking_requested = criteria['crowd_level'] != 'any'
    evaluations.sort(key=lambda evaluation: (
        -evaluation.rank_score,
        -(evaluation.crowd['observed_at'].timestamp()
          if crowd_ranking_requested and evaluation.crowd else 0),
        evaluation.distance,
        evaluation.place.id,
    ))
    items = []
    for rank, evaluation in enumerate(evaluations[:criteria['limit']], 1):
        raw_scores = evaluation.raw_scores
        factors = evaluation.evidence_factors
        effective_scores = {
            key: (NEUTRAL_RANKING_BASELINE + (value - NEUTRAL_RANKING_BASELINE) * factors[key])
            if value is not None else None
            for key, value in raw_scores.items()
        }
        contributors = [key for key in ranking_keys if raw_scores[key] is not None]
        score = sum(weights[key] * (
            effective_scores[key] if effective_scores[key] is not None else NEUTRAL_RANKING_BASELINE
        ) for key in ranking_keys) / ranking_total
        guard = 1 / (1 + max(0, evaluation.distance - settings.RECOMMENDATION_DISTANCE_GUARD_FREE_KM)
                     / settings.RECOMMENDATION_DISTANCE_GUARD_SCALE_KM)
        place = evaluation.place
        profile = evaluation.profile
        forecast = evaluation.forecast
        item = {
            'place': {
                'id': place.id, 'name': place.name, 'category': place.category,
                'address': place.address, 'latitude': float(place.latitude),
                'longitude': float(place.longitude), 'indoor_outdoor': place.indoor_outdoor,
                'indoor_outdoor_source': place.indoor_outdoor_source or None,
                'indoor_outdoor_evidence_quality': evaluation.classification_quality,
                'indoor_outdoor_evidence': place.indoor_outdoor_evidence or None,
                'weather_exposure': profile.as_dict(),
            },
            'distance_km': round(evaluation.distance, 3),
            'distance_type': 'straight_line',
            'travel_time_minutes': None,
            'crowd': evaluation.crowd,
            'weather_status': evaluation.weather_status,
            'weather': ({
                'source': forecast.source, 'issued_at': forecast.issued_at,
                'target_at': forecast.target_at,
                'precipitation_type': forecast.precipitation_type,
                'temperature_c': forecast.temperature_c, 'wind_mps': forecast.wind_mps,
                'completeness': evaluation.weather_status,
            } if forecast else None),
            'recommendation_score': round(evaluation.rank_score, 2),
            'distance_adjustment': {'factor': round(guard, 4), 'base_score': round(score, 2)},
            'score_breakdown': {
                key: round(value, 2) if value is not None else None
                for key, value in raw_scores.items()
            },
            'score_effective_breakdown': {
                key: round(value, 2) if value is not None else None
                for key, value in effective_scores.items()
            },
            'score_contributors': contributors,
            'data_coverage': round(sum(
                weights[key] * factors[key]
                for key, value in raw_scores.items() if value is not None
            ), 2),
            'ranking_coverage': round(sum(
                weights[key] * factors[key] for key in contributors
            ) / ranking_total, 2),
            'missing_data': [key for key, value in raw_scores.items() if value is None],
            'rank': rank,
        }
        reasons = [f"현재 위치에서 직선거리 {evaluation.distance:.1f}km입니다."]
        if preference_source != 'default_travel_intent' and raw_scores['category'] == 100:
            reasons.append('선호한 카테고리입니다.')
        elif preference_source == 'default_travel_intent':
            reasons.append(DEFAULT_CATEGORY_REASONS[place.category])
        crowd = evaluation.crowd
        if crowd:
            reasons.append(f"서울 혼잡도 관측값은 {crowd['level']}입니다.")
            if crowd['is_delayed']:
                reasons.append('30분 넘은 관측을 낮은 비중으로 반영했습니다.' if 'crowd' in contributors else
                               '30분 넘은 관측이며 순위에는 반영하지 않았습니다.')
        if 'weather' in contributors:
            if evaluation.weather_status == 'partial_hazard':
                reasons.append('예보에서 확인된 악조건만 날씨 점수에 반영했습니다.')
            else:
                reasons.append('예보된 날씨와 주된 방문 활동의 날씨 노출을 반영했습니다.')
            reasons.append(profile.reason)
        if evaluation.weather_factors and profile.level == 'high':
            reasons.append('야외 방문 시 예보된 비·눈, 바람 또는 기온을 확인하세요.')
        item['reasons'] = reasons
        items.append(item)
    message = '' if len(items) == criteria['limit'] else (
        '날씨·실내외 근거가 확인된 후보가 요청 개수보다 적습니다.'
        if criteria.get('weather_evidence_required') else
        '현재 필수 조건과 반경에 맞는 후보가 요청 개수보다 적습니다.'
    )
    ranking_basis = ('weather_and_travel_discovery' if 'weather' in ranking_keys and
                     preference_source == 'default_travel_intent' else
                     'weather_and_preferences' if 'weather' in ranking_keys else
                     'travel_discovery' if preference_source == 'default_travel_intent' else
                     'requested_preferences')
    return {'items': items, 'generated_at': now, 'visit_at': visit_at,
            'algorithm_version': ALGORITHM_VERSION, 'candidate_count': len(evaluations),
            'ranking_basis': ranking_basis, 'ranking_factors': ranking_keys,
            'preference_source': preference_source,
            'weather_aware': criteria.get('weather_aware', True),
            'weather_evidence_required': bool(criteria.get('weather_evidence_required')),
            'ranking_policy': {'missing_evidence_baseline': NEUTRAL_RANKING_BASELINE,
                               'meaning': 'ranking neutral point, not an observed value',
                               'weights': {key: weights[key] for key in ranking_keys},
                               'distance_scale_km': settings.RECOMMENDATION_DISTANCE_SCALE_KM,
                               'distance_guard_free_km': settings.RECOMMENDATION_DISTANCE_GUARD_FREE_KM,
                               'distance_guard_scale_km': settings.RECOMMENDATION_DISTANCE_GUARD_SCALE_KM,
                               'name_rule_weight_factor': settings.RECOMMENDATION_NAME_RULE_WEIGHT_FACTOR,
                               'description_rule_weight_factor': settings.RECOMMENDATION_DESCRIPTION_RULE_WEIGHT_FACTOR,
                               'luna_validated_weight_factor': settings.RECOMMENDATION_LUNA_VALIDATED_WEIGHT_FACTOR,
                               'type_prior_weather_weight_factor': TYPE_PRIOR_FACTOR}}, message
