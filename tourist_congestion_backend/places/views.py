import math

from django.db.models import Exists, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from places.models import CrowdData, Place, PlaceSource
from places.integrations.tour_api import _first_text
from places.regions import address_path, parse_region_path, region_tree


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_RADIUS_KM = 5.0
MAX_RADIUS_KM = 100.0
EARTH_RADIUS_KM = 6371.0088


def _success(data):
    return JsonResponse({'success': True, 'data': data, 'message': ''})


def _error(message, *, status=400):
    return JsonResponse(
        {'success': False, 'data': None, 'message': message},
        status=status,
    )


def _positive_int(value, *, name, default):
    if value in (None, ''):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a positive integer.') from None
    if parsed < 1:
        raise ValueError(f'{name} must be a positive integer.')
    return parsed


def _finite_float(value, *, name, required=True, default=None):
    if value in (None, ''):
        if required:
            raise ValueError(f'{name} is required.')
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a number.') from None
    if not math.isfinite(parsed):
        raise ValueError(f'{name} must be a finite number.')
    return parsed


def _validate_crowd_level(crowd_level):
    if not crowd_level:
        return None
    valid_levels = set(CrowdData.CrowdLevel.values)
    if crowd_level not in valid_levels:
        raise ValueError(
            'crowd_level must be one of: '
            + ', '.join(CrowdData.CrowdLevel.values)
            + '.'
        )
    return crowd_level


def _visible_places():
    sources = PlaceSource.objects.filter(place_id=OuterRef('pk'))
    active_sources = sources.filter(match_status=PlaceSource.MatchStatus.MATCHED)
    latest_crowd = CrowdData.objects.filter(
        crowd_area__place_mappings__place_id=OuterRef('pk')
    ).order_by('-observed_at', '-id')

    return (
        Place.objects.annotate(
            _has_any_source=Exists(sources),
            _has_active_source=Exists(active_sources),
            latest_crowd_id=Subquery(latest_crowd.values('id')[:1]),
            latest_crowd_raw_data=Subquery(latest_crowd.values('raw_data')[:1]),
            latest_crowd_area_id=Subquery(
                latest_crowd.values('crowd_area_id')[:1]
            ),
            latest_crowd_area_external_id=Subquery(
                latest_crowd.values('crowd_area__external_id')[:1]
            ),
            latest_crowd_area_name=Subquery(
                latest_crowd.values('crowd_area__name')[:1]
            ),
            latest_crowd_source=Subquery(
                latest_crowd.values('crowd_area__source')[:1]
            ),
            latest_crowd_level=Subquery(
                latest_crowd.values('crowd_level')[:1]
            ),
            latest_crowd_message=Subquery(
                latest_crowd.values('crowd_message')[:1]
            ),
            latest_crowd_score=Subquery(
                latest_crowd.values('crowd_score')[:1]
            ),
            latest_crowd_population_min=Subquery(
                latest_crowd.values('population_min')[:1]
            ),
            latest_crowd_population_max=Subquery(
                latest_crowd.values('population_max')[:1]
            ),
            latest_crowd_observed_at=Subquery(
                latest_crowd.values('observed_at')[:1]
            ),
            latest_crowd_is_replaced=Subquery(
                latest_crowd.values('is_replaced')[:1]
            ),
        )
        .filter(Q(_has_any_source=False) | Q(_has_active_source=True))
        .select_related('info')
        .order_by('name', 'id')
    )


def _latest_crowd(place):
    if place.latest_crowd_id is None:
        return None
    return {
        'area_id': place.latest_crowd_area_id,
        'area_external_id': place.latest_crowd_area_external_id,
        'area_name': place.latest_crowd_area_name,
        'source': place.latest_crowd_source,
        'level': place.latest_crowd_level,
        'message': place.latest_crowd_message,
        'score': place.latest_crowd_score,
        'population_min': place.latest_crowd_population_min,
        'population_max': place.latest_crowd_population_max,
        'observed_at': place.latest_crowd_observed_at,
        'is_replaced': place.latest_crowd_is_replaced,
        'is_demo': bool((place.latest_crowd_raw_data or {}).get('dev_seed')),
    }


def _serialize_place(place, *, detail=False, distance_km=None):
    info = getattr(place, 'info', None)
    intro = (info.raw_data or {}).get('intro', {}) if info else {}
    if not isinstance(intro, dict):
        intro = {}
    data = {
        'id': place.id,
        'name': place.name,
        'category': place.category,
        'subcategory': place.subcategory,
        'region_code': place.region_code,
        'address': place.address,
        'latitude': float(place.latitude),
        'longitude': float(place.longitude),
        'indoor_outdoor': place.indoor_outdoor,
        'avg_rating': (
            float(place.avg_rating) if place.avg_rating is not None else None
        ),
        'image_url': info.first_image_url if info and info.first_image_url else None,
        'latest_crowd': _latest_crowd(place),
    }
    if detail:
        data.update(
            {
                'open_status': place.open_status,
                'info': (
                    {
                        'description': info.description,
                        'phone': info.phone or None,
                        'homepage_url': info.homepage_url or None,
                        'first_image_url': info.first_image_url or None,
                        'opening_hours': info.opening_hours or None,
                        'holiday_info': info.holiday_info or None,
                        'admission_fee': _first_text(intro, ('usefee', 'usefeeculture', 'usefeeleports')) or None,
                        'parking': _first_text(intro, ('parking', 'parkingculture', 'parkingleports', 'parkinglodging', 'parkingshopping', 'parkingfood')) or None,
                        'tags': info.tags,
                        'source': info.merged_summary_source or None,
                        'updated_at': info.updated_at,
                    }
                    if info
                    else None
                ),
                'created_at': place.created_at,
                'updated_at': place.updated_at,
            }
        )
    if distance_km is not None:
        data['distance_km'] = round(distance_km, 3)
    return data


def _haversine_km(latitude, longitude, place):
    place_latitude = math.radians(float(place.latitude))
    place_longitude = math.radians(float(place.longitude))
    latitude = math.radians(latitude)
    longitude = math.radians(longitude)
    latitude_delta = place_latitude - latitude
    longitude_delta = place_longitude - longitude
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude)
        * math.cos(place_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1, math.sqrt(haversine)))


def _nearby_bounding_box(latitude, longitude, radius_km):
    latitude_delta = radius_km / 111.32
    latitude_min = max(-90, latitude - latitude_delta)
    latitude_max = min(90, latitude + latitude_delta)
    longitude_scale = math.cos(math.radians(latitude))
    longitude_delta = (
        180 if abs(longitude_scale) < 1e-12 else radius_km / (111.32 * longitude_scale)
    )
    longitude_min = max(-180, longitude - longitude_delta)
    longitude_max = min(180, longitude + longitude_delta)
    return latitude_min, latitude_max, longitude_min, longitude_max


@require_GET
def place_regions(request):
    return _success({'items': region_tree(_visible_places().values_list('address', flat=True)),
                     'coverage': 'registered_places'})


@require_GET
def place_list(request):
    try:
        page = _positive_int(request.GET.get('page'), name='page', default=1)
        page_size = _positive_int(
            request.GET.get('page_size'),
            name='page_size',
            default=DEFAULT_PAGE_SIZE,
        )
    except ValueError as exc:
        return _error(str(exc))

    if page_size > MAX_PAGE_SIZE:
        return _error(f'page_size must be at most {MAX_PAGE_SIZE}.')

    queryset = _visible_places()
    keyword = request.GET.get('keyword', '').strip()
    category = request.GET.get('category', '').strip()
    region_code = request.GET.get('region_code', '').strip()
    region_path = request.GET.get('region_path', '').strip()
    crowd_level = request.GET.get('crowd_level', '').strip().lower()

    if keyword:
        queryset = queryset.filter(
            Q(name__icontains=keyword) | Q(address__icontains=keyword)
        )
    if category:
        queryset = queryset.filter(category__icontains=category)
    if region_code:
        queryset = queryset.filter(region_code__startswith=region_code)
    if region_path:
        try:
            selected = parse_region_path(region_path)
        except ValueError as exc:
            return _error(str(exc))
        matched_ids = [pk for pk, address in queryset.values_list('pk', 'address')
                       if address_path(address)[:len(selected)] == selected]
        queryset = queryset.filter(pk__in=matched_ids)
        region_path = '/'.join(selected)
    try:
        crowd_level = _validate_crowd_level(crowd_level)
    except ValueError as exc:
        return _error(str(exc))
    if crowd_level:
        queryset = queryset.filter(latest_crowd_level=crowd_level)

    total = queryset.count()
    offset = (page - 1) * page_size
    items = [
        _serialize_place(place)
        for place in queryset[offset : offset + page_size]
    ]
    return _success(
        {
            'items': items,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': math.ceil(total / page_size),
            },
            'filters': {
                'keyword': keyword,
                'category': category,
                'region_code': region_code,
                'region_path': region_path,
                'crowd_level': crowd_level,
            },
        }
    )


@require_GET
def nearby_places(request):
    try:
        latitude = _finite_float(request.GET.get('latitude'), name='latitude')
        longitude = _finite_float(request.GET.get('longitude'), name='longitude')
        radius_km = _finite_float(
            request.GET.get('radius_km'),
            name='radius_km',
            required=False,
            default=DEFAULT_RADIUS_KM,
        )
        page = _positive_int(request.GET.get('page'), name='page', default=1)
        page_size = _positive_int(
            request.GET.get('page_size'),
            name='page_size',
            default=DEFAULT_PAGE_SIZE,
        )
        crowd_level = _validate_crowd_level(
            request.GET.get('crowd_level', '').strip().lower()
        )
    except ValueError as exc:
        return _error(str(exc))

    if not -90 <= latitude <= 90:
        return _error('latitude must be between -90 and 90.')
    if not -180 <= longitude <= 180:
        return _error('longitude must be between -180 and 180.')
    if radius_km <= 0:
        return _error('radius_km must be greater than 0.')
    if radius_km > MAX_RADIUS_KM:
        return _error(f'radius_km must be at most {MAX_RADIUS_KM:g}.')
    if page_size > MAX_PAGE_SIZE:
        return _error(f'page_size must be at most {MAX_PAGE_SIZE}.')

    category = request.GET.get('category', '').strip()
    queryset = _visible_places()
    if category:
        queryset = queryset.filter(category__icontains=category)
    if crowd_level:
        queryset = queryset.filter(latest_crowd_level=crowd_level)

    latitude_min, latitude_max, longitude_min, longitude_max = (
        _nearby_bounding_box(latitude, longitude, radius_km)
    )
    candidates = queryset.filter(
        latitude__gte=latitude_min,
        latitude__lte=latitude_max,
        longitude__gte=longitude_min,
        longitude__lte=longitude_max,
    )
    nearby = []
    for place in candidates:
        distance_km = _haversine_km(latitude, longitude, place)
        if distance_km <= radius_km:
            nearby.append((distance_km, place))
    nearby.sort(key=lambda item: (item[0], item[1].name, item[1].id))

    total = len(nearby)
    offset = (page - 1) * page_size
    items = [
        _serialize_place(place, distance_km=distance_km)
        for distance_km, place in nearby[offset : offset + page_size]
    ]
    return _success(
        {
            'items': items,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': math.ceil(total / page_size),
            },
            'search_center': {
                'latitude': latitude,
                'longitude': longitude,
                'radius_km': radius_km,
            },
            'filters': {
                'category': category,
                'crowd_level': crowd_level or '',
            },
        }
    )


@require_GET
def place_detail(request, place_id):
    place = _visible_places().filter(pk=place_id).first()
    if place is None:
        return _error('Place not found.', status=404)
    return _success(_serialize_place(place, detail=True))
