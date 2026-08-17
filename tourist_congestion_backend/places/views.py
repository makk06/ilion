import math

from django.db.models import Exists, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from places.models import CrowdData, Place, PlaceSource


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


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
    }


def _serialize_place(place, *, detail=False):
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
        'latest_crowd': _latest_crowd(place),
    }
    if detail:
        data.update(
            {
                'open_status': place.open_status,
                'created_at': place.created_at,
                'updated_at': place.updated_at,
            }
        )
    return data


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
    crowd_level = request.GET.get('crowd_level', '').strip().lower()

    if keyword:
        queryset = queryset.filter(
            Q(name__icontains=keyword) | Q(address__icontains=keyword)
        )
    if category:
        queryset = queryset.filter(category__icontains=category)
    if region_code:
        queryset = queryset.filter(region_code__startswith=region_code)
    if crowd_level:
        valid_levels = set(CrowdData.CrowdLevel.values)
        if crowd_level not in valid_levels:
            return _error(
                'crowd_level must be one of: '
                + ', '.join(CrowdData.CrowdLevel.values)
                + '.'
            )
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
                'crowd_level': crowd_level,
            },
        }
    )


@require_GET
def place_detail(request, place_id):
    place = _visible_places().filter(pk=place_id).first()
    if place is None:
        return _error('Place not found.', status=404)
    return _success(_serialize_place(place, detail=True))
