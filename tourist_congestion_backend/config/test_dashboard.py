"""Read-only recommendation preview; operational diagnostics are DEBUG-only."""

import os
from time import perf_counter

from django.conf import settings
from django.db.models import Count, Max, OuterRef, Subquery
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from places.models import (
    CrowdArea, CrowdData, DataJob, Place, PlaceCrowdArea, PlaceInfo,
    PlaceClassificationEvidence, PlaceClassificationAttempt,
    ProviderCallBudget, WeatherForecast,
)
from places.services.classification import current_description_evidence
from places.services.description_classification import is_placeholder_description
from places.services.weather_exposure import exposure_for, source_codes_for, veto_ids_for
from recommendations.management.commands.evaluate_recommendation_quality import _distance_baseline
from recommendations.serializers import RecommendationRequestSerializer
from recommendations.service import (
    _classification_quality, prepare_recommendations, recommend,
)


CITY_PRESETS = (
    {'name': '서울 광화문', 'latitude': '37.575', 'longitude': '126.977'},
    {'name': '부산 해운대', 'latitude': '35.160', 'longitude': '129.160'},
    {'name': '제주시', 'latitude': '33.500', 'longitude': '126.530'},
    {'name': '대전', 'latitude': '36.350', 'longitude': '127.385'},
    {'name': '대구', 'latitude': '35.872', 'longitude': '128.602'},
    {'name': '광주', 'latitude': '35.160', 'longitude': '126.851'},
    {'name': '강릉', 'latitude': '37.752', 'longitude': '128.876'},
)
CATEGORIES = ('관광지', '문화시설', '축제/공연/행사', '레포츠', '쇼핑', '음식점')
INDOOR_LABELS = {'indoor': '실내', 'outdoor': '실외', 'mixed': '실내외 혼합', 'unknown': '미확인'}
EXPOSURE_LABELS = {'high': '날씨 영향 큼', 'medium': '날씨 영향 일부',
                   'low': '날씨 영향 작음', 'unknown': '날씨 노출 미확인'}
EXPOSURE_SOURCES = {'manual': '수동', 'description_rule': '공개 설명',
                    'description_rule_and_type': '공개 설명+공식 유형',
                    'luna_validated': 'AI 추정', 'luna_exposure': 'AI 주활동 추정',
                    'luna_validated_and_type': 'AI+공식 유형', 'name_rule': '이름 추정',
                    'type_prior': '공식 유형의 약한 추정', 'audit_veto': '검수 후 제외',
                    'inference_conflict': '근거 충돌', 'source_conflict': '출처 충돌',
                    'luna_exposure_unknown': 'AI 유보', 'unavailable': '근거 없음'}
CROWD_LABELS = {'relaxed': '여유', 'normal': '보통', 'busy': '혼잡',
                'crowded': '매우 혼잡', 'unknown': '미확인'}
PRECIPITATION_LABELS = {0: '강수 없음', 1: '비', 2: '비·눈', 3: '눈', 4: '소나기',
                        5: '빗방울', 6: '빗방울·눈날림', 7: '눈날림'}
CONTRIBUTOR_LABELS = {
    'distance': '거리', 'category': '카테고리', 'crowd': '혼잡도',
    'weather': '날씨', 'indoor_outdoor': '실내외',
}
PROVIDERS = (
    ('tour_api', 'TourAPI', 'TOUR_API_DAILY_LIMIT'),
    ('kma', '기상청', 'KMA_DAILY_LIMIT'),
    ('seoul', '서울 혼잡도', 'SEOUL_DAILY_LIMIT'),
)
JOB_STATUSES = ('pending', 'running', 'succeeded', 'failed')
SCENARIOS = {'live', 'weather', 'taste', 'strict', 'distance'}


def _form_values(request):
    defaults = {
        'latitude': CITY_PRESETS[0]['latitude'],
        'longitude': CITY_PRESETS[0]['longitude'],
        'radius_km': '10',
        'limit': '10',
        'category': '',
        'crowd_level': 'any',
        'required_indoor_outdoor': '',
        'weather_aware': True,
        'weather_evidence_required': False,
        'quiet_required': False,
        'visit_at': '',
        'scenario': 'live',
    }
    if request.method == 'POST':
        for key in defaults:
            if key in ('weather_aware', 'weather_evidence_required', 'quiet_required'):
                defaults[key] = key in request.POST
            else:
                defaults[key] = request.POST.get(key, '')
        if defaults['scenario'] not in SCENARIOS:
            defaults['scenario'] = 'live'
    return defaults


def _decorate_items(items):
    details = {
        info.place_id: info for info in PlaceInfo.objects.filter(
            place_id__in=[item['place']['id'] for item in items]
        ).only('place_id', 'description', 'first_image_url')
    }
    for item in items:
        item['indoor_label'] = INDOOR_LABELS[item['place']['indoor_outdoor']]
        item['contributors_labels'] = [CONTRIBUTOR_LABELS[key] for key in item['score_contributors']]
        item['missing_labels'] = [CONTRIBUTOR_LABELS[key] for key in item['missing_data']]
        item['evidence_percent'] = round(item['data_coverage'] * 100) if item['data_coverage'] is not None else None
        info = details.get(item['place']['id'])
        item['description'] = info.description if info and not is_placeholder_description(info.description) else ''
        profile = item['place'].get('weather_exposure')
        item['exposure_label'] = EXPOSURE_LABELS.get(profile['level'], '날씨 노출 미확인') if profile else '모델 미평가'
        item['exposure_source_label'] = EXPOSURE_SOURCES.get(profile['source'], '자동 추정') if profile else ''
        image = info.first_image_url if info else ''
        item['image_url'] = image if image.startswith(('https://', 'http://')) else ''
        item['crowd_label'] = CROWD_LABELS.get(item['crowd']['level'], '미확인') if item['crowd'] else ''
        item['crowd_ranked'] = 'crowd' in item['score_contributors']
        item['weather_label'] = PRECIPITATION_LABELS.get(item['weather']['precipitation_type'], '강수 정보 없음') if item['weather'] else ''


def _pack_preview(data, message, elapsed_ms, *, is_distance=False, virtual=False):
    items = data['items']
    _decorate_items(items)
    return {
        'items': items,
        'candidate_count': data['candidate_count'],
        'ranking_basis': data['ranking_basis'],
        'algorithm_version': data['algorithm_version'],
        'visit_at': data['visit_at'],
        'message': message,
        'elapsed_ms': elapsed_ms,
        'weather_count': sum('weather' in item['score_contributors'] for item in items),
        'crowd_count': sum(bool(item['crowd']) for item in items),
        'detail_count': sum(bool(item['description']) for item in items),
        'mean_distance_km': round(sum(item['distance_km'] for item in items) / len(items), 2) if items else None,
        'classified_count': sum(item['place']['indoor_outdoor_evidence_quality'] in
                                ('manual_label', 'inferred_from_name',
                                 'inferred_from_description', 'inferred_from_luna') for item in items),
        'top_name': items[0]['place']['name'] if items else None,
        'is_distance': is_distance,
        'virtual': virtual,
    }


def _model_preview(criteria, now, *, forecast_lookup=None, virtual=False, prepared=None):
    started = perf_counter()
    data, message = recommend(criteria, user=None, now=now, supplement=False,
                              forecast_lookup=forecast_lookup, prepared=prepared)
    return _pack_preview(data, message, round((perf_counter() - started) * 1000), virtual=virtual)


def _distance_preview(criteria, now):
    started = perf_counter()
    rows = _distance_baseline(criteria['latitude'], criteria['longitude'],
                              criteria['radius_km'], criteria['limit'], criteria.get('visit_at') or now)
    places = Place.objects.select_related('info', 'classification_record').in_bulk(
        [row['id'] for row in rows])
    items = []
    for rank, row in enumerate(rows, 1):
        place = places[row['id']]
        quality, _ = _classification_quality(place)
        items.append({
            'rank': rank,
            'place': {'id': place.id, 'name': place.name, 'category': place.category,
                      'address': place.address, 'indoor_outdoor': place.indoor_outdoor,
                      'indoor_outdoor_source': place.indoor_outdoor_source or None,
                      'indoor_outdoor_evidence_quality': quality,
                      'indoor_outdoor_evidence': place.indoor_outdoor_evidence or None},
            'distance_km': row['distance_km'], 'recommendation_score': None,
            'score_contributors': ['distance'], 'missing_data': [], 'data_coverage': None,
            'weather': None, 'weather_status': None, 'crowd': None,
            'reasons': ['같은 후보 조건에서 직선거리만으로 정렬했습니다.'],
        })
    return _pack_preview({'items': items, 'candidate_count': len(rows),
                          'ranking_basis': 'distance_only', 'algorithm_version': '거리순 비교 기준',
                          'visit_at': criteria.get('visit_at') or now}, '',
                         round((perf_counter() - started) * 1000), is_distance=True)


def _virtual_lookup(kind, now):
    values = {'fair': (0, 20, 2), 'rain': (1, 20, 2), 'wind': (0, 20, 11)}
    precipitation, temperature, wind = values[kind]

    def lookup(grid, visit_at, request_now):
        if grid is None:
            return None
        return WeatherForecast(
            source='virtual_test_only', grid_x=grid[0], grid_y=grid[1],
            issued_at=now, target_at=visit_at.replace(minute=0, second=0, microsecond=0),
            precipitation_type=precipitation, temperature_c=temperature,
            wind_mps=wind, raw_data={'simulation': kind},
        )

    return lookup


def _distance_comparison_criteria(criteria):
    # The distance baseline is a pure proximity sort under the base venue
    # eligibility contract; preference and strict-filter fields are excluded.
    return {key: criteria[key] for key in ('latitude', 'longitude', 'radius_km', 'limit', 'visit_at')
            if key in criteria} | {'crowd_level': 'any', 'weather_aware': True,
                                   'weather_evidence_required': False, 'quiet_required': False}


def _comparison(title, description, panels, *, virtual=False):
    first = panels[0]['preview']
    first_ids = {item['place']['id'] for item in first['items']}
    for panel in panels:
        preview = panel['preview']
        panel['overlap'] = len(first_ids & {item['place']['id'] for item in preview['items']})
        panel['top_comparison_available'] = bool(preview['top_name'] and first['top_name'])
        panel['top_changed'] = preview['top_name'] != first['top_name']
    return {'title': title, 'description': description, 'panels': panels, 'virtual': virtual}


def _preview(request, form, now):
    payload = {key: form[key] for key in ('latitude', 'longitude', 'radius_km', 'limit', 'crowd_level')}
    for key in ('category', 'required_indoor_outdoor', 'visit_at'):
        if form[key]:
            payload[key] = form[key]
    payload['weather_evidence_required'] = form['weather_evidence_required']
    payload['weather_aware'] = form['weather_aware']
    payload['quiet_required'] = form['quiet_required']
    serializer = RecommendationRequestSerializer(data=payload)
    if not serializer.is_valid():
        return None, None, serializer.errors
    criteria = serializer.validated_data
    scenario = form['scenario']
    if scenario == 'live':
        return _model_preview(criteria, now), None, None
    if scenario == 'weather':
        weather_criteria = {**criteria, 'weather_aware': True}
        prepared = prepare_recommendations(weather_criteria, now=now, supplement=False)
        panels = [{'title': title, 'preview': _model_preview(weather_criteria, now,
                   forecast_lookup=_virtual_lookup(kind, now), virtual=True,
                   prepared=prepared)}
                  for kind, title in (('fair', '가상 맑음'), ('rain', '가상 비'), ('wind', '가상 강풍'))]
        experiment = _comparison('날씨만 바꾸면?',
            '입력한 위치·선호·필수 조건과 실제 장소·실내외 분류를 유지하고 예보만 메모리에서 바꿉니다. 날씨 반영은 이 실험에서 켭니다. 실제 기상 예보가 아닙니다.',
            panels, virtual=True)
    elif scenario == 'taste':
        taste_base = {**criteria}
        taste_base.pop('category', None)
        prepared = prepare_recommendations(taste_base, now=now, supplement=False)
        panels = [{'title': title, 'preview': _model_preview(
            {**taste_base, **extra}, now, prepared=prepared)}
                  for title, extra in (('기본 여행 탐색', {}), ('음식점 선호', {'category': '음식점'}),
                                       ('쇼핑 선호', {'category': '쇼핑'}))]
        experiment = _comparison('선호를 바꾸면?',
            '입력한 다른 조건은 유지하고 카테고리 선호만 바꿉니다. 현재 저장된 날씨가 사용 가능할 때만 반영합니다.', panels)
    elif scenario == 'strict':
        strict_base = {**criteria, 'crowd_level': 'any', 'weather_evidence_required': False,
                       'quiet_required': False}
        strict_base.pop('required_indoor_outdoor', None)
        prepared = prepare_recommendations(strict_base, now=now, supplement=False)
        panels = [{'title': title, 'preview': _model_preview(
            {**strict_base, **extra}, now, prepared=prepared)}
                  for title, extra in (('필수 조건 없음', {}),
                                       ('날씨 근거 필수', {'weather_evidence_required': True}),
                                       ('실내 분류 필수', {'required_indoor_outdoor': 'indoor'}),
                                       ('한산함 필수', {'quiet_required': True}))]
        experiment = _comparison('필수 조건을 걸면?',
            '각 열에서 필수 조건 하나만 추가합니다. 입력한 카테고리 선호 등은 유지하고, 비교를 위해 혼잡 선호만 ‘상관없음’으로 통일합니다. 근거가 부족하면 조건을 완화하지 않습니다.', panels)
    else:
        distance_criteria = _distance_comparison_criteria(criteria)
        panels = [{'title': '직선거리만', 'preview': _distance_preview(distance_criteria, now)},
                  {'title': '개선 추천 모델', 'preview': _model_preview(distance_criteria, now)}]
        experiment = _comparison('가까운 순서와 지금 추천의 차이',
            '같은 위치·반경·방문 시각과 기본 후보 자격을 사용합니다. 요청 폼의 선호·필수 조건은 이 비교에서 제외합니다.', panels)
    return None, experiment, None


def _snapshot(now, *, include_operations=True):
    total_places = Place.objects.count()
    detail_count = PlaceInfo.objects.exclude(description='').exclude(
        description__contains='개발용 상세정보').count()
    classified_count = Place.objects.exclude(indoor_outdoor=Place.IndoorOutdoor.UNKNOWN).count()
    weather_grids = WeatherForecast.objects.values('grid_x', 'grid_y').distinct().count()
    catalog = {
        'total_places': total_places,
        'detail_count': detail_count,
        'detail_percent': 100 * detail_count / total_places if total_places else 0,
        'classified_count': classified_count,
        'classified_percent': 100 * classified_count / total_places if total_places else 0,
        'weather_grids': weather_grids,
        'mapped_places': PlaceCrowdArea.objects.values('place_id').distinct().count(),
    }
    if not include_operations:
        return catalog
    weather_latest = WeatherForecast.objects.aggregate(issued=Max('issued_at'), fetched=Max('fetched_at'))
    latest_observation = CrowdData.objects.filter(crowd_area_id=OuterRef('pk')).order_by('-observed_at', '-id')
    areas = list(CrowdArea.objects.annotate(
        latest_observed_at=Subquery(latest_observation.values('observed_at')[:1]),
        latest_level=Subquery(latest_observation.values('crowd_level')[:1]),
    ).order_by('name'))
    crowd_fresh = 0
    crowd_valid = 0
    crowd_delayed = 0
    for area in areas:
        observed_at = area.latest_observed_at
        area.latest_level_label = CROWD_LABELS.get(area.latest_level, '미확인')
        if observed_at is None:
            area.freshness = '관측 없음'
            area.freshness_class = 'muted'
        else:
            age_minutes = (now - observed_at).total_seconds() / 60
            if 0 <= age_minutes <= settings.CROWD_FRESH_MINUTES:
                area.freshness = '신선'
                area.freshness_class = 'good'
                crowd_fresh += 1
                crowd_valid += 1
            elif age_minutes <= settings.CROWD_FULL_WEIGHT_MINUTES:
                area.freshness = '15분 초과'
                area.freshness_class = 'warn'
                crowd_valid += 1
            elif age_minutes <= settings.CROWD_MAX_AGE_MINUTES:
                area.freshness = '지연 관측'
                area.freshness_class = 'warn'
                crowd_valid += 1
                crowd_delayed += 1
            else:
                area.freshness = '만료'
                area.freshness_class = 'bad'

    job_counts = {status: 0 for status in JOB_STATUSES}
    job_counts.update({row['status']: row['total'] for row in DataJob.objects.values('status').annotate(total=Count('id'))})
    today_rows = list(ProviderCallBudget.objects.filter(date=timezone.localdate(now)))
    budgets = []
    for code, name, env_name in PROVIDERS:
        try:
            daily_limit = int(os.environ.get(env_name, '0'))
        except ValueError:
            daily_limit = 0
        lanes = {row.lane: row.used for row in today_rows if row.provider == code}
        budgets.append({
            'name': name,
            'used': sum(lanes.values()),
            'regular': lanes.get('regular', 0),
            'supplemental': lanes.get('supplemental', 0),
            'reserve': lanes.get('reserve', 0),
            'limit': '일일 제한 없음' if code == 'seoul' and daily_limit == -1 else (
                f'{daily_limit:,}회' if daily_limit > 0 else '미설정'
            ),
        })
    return {
        **catalog,
        'weather_latest': weather_latest,
        'crowd_areas': areas,
        'crowd_fresh': crowd_fresh,
        'crowd_valid': crowd_valid,
        'crowd_delayed': crowd_delayed,
        'job_counts': job_counts,
        'recent_jobs': DataJob.objects.order_by('-created_at', '-id')[:8],
        'budgets': budgets,
    }


@never_cache
@require_http_methods(['GET', 'POST'])
def backend_test_dashboard(request):
    now = timezone.now()
    form = _form_values(request)
    preview, experiment, form_errors = _preview(request, form, now)
    context = {
        'now': now,
        'form': form,
        'form_errors': form_errors,
        'preview': preview,
        'experiment': experiment,
        'city_presets': CITY_PRESETS,
        'categories': CATEGORIES,
        'show_operations': settings.DEBUG,
        'snapshot': _snapshot(now, include_operations=settings.DEBUG),
    }
    if not settings.DEBUG:
        return render(request, 'config/backend_test_dashboard.html', context)
    recent_cases = list(PlaceClassificationEvidence.objects.filter(
        method__in=('description_rule', 'luna_validated')).select_related(
        'place', 'place__info').order_by(
        '-classified_at', 'place_id')[:20])
    # Stable evaluation examples stay visible even as newer offline batches
    # arrive. These IDs select dashboard examples, never classification rules.
    fixed_cases = list(PlaceClassificationEvidence.objects.filter(
        place_id__in=(3997, 28656), method='description_rule').select_related(
        'place', 'place__info').order_by('place_id'))
    fixed_ids = {case.place_id for case in fixed_cases}
    classification_cases = fixed_cases + [case for case in recent_cases
                                          if case.place_id not in fixed_ids]
    for case in classification_cases:
        case.display_label = INDOOR_LABELS.get(case.label, case.label)
        case.display_previous = INDOOR_LABELS.get(case.previous_label, '이전 기록 없음')
        case.display_method = 'AI 추정' if case.method == 'luna_validated' else '설명 규칙 추정'
        case.is_current = current_description_evidence(case.place) is not None
    # Stable examples are selected for the testbed only, never by the model.
    # The first row shows that an unknown indoor/outdoor label can still have
    # a weak, explicitly identified official-type weather prior.
    profile_places = list(Place.objects.filter(
        id__in=(1, 3997, 28656, 2687, 824, 2346, 883),
    ).select_related('info', 'classification_record', 'weather_exposure_record'))
    profile_places.sort(key=lambda place: (place.id != 1, place.id))
    profile_codes = source_codes_for([place.id for place in profile_places])
    profile_veto = veto_ids_for([place.id for place in profile_places])
    weather_profile_cases = []
    for place in profile_places:
        profile = exposure_for(place, profile_codes.get(place.id, ()),
                               veto=place.id in profile_veto).as_dict()
        weather_profile_cases.append({
            'place': place, 'profile': profile,
            'label': EXPOSURE_LABELS[profile['level']],
            'source_label': EXPOSURE_SOURCES.get(profile['source'], '자동 추정'),
            'indoor_label': INDOOR_LABELS[place.indoor_outdoor],
        })
    return render(request, 'config/backend_test_dashboard.html', {
        **context,
        'classification_cases': classification_cases,
        'weather_profile_cases': weather_profile_cases,
        'luna_attempt_count': PlaceClassificationAttempt.objects.count(),
    })
