"""Deterministic, public-place-only selection for the local recommendation pilot."""

from places.models import ExternalSource, Place, PlaceSource
from places.views import _haversine_km


CATEGORIES = ('관광지', '문화시설', '축제/공연/행사', '레포츠', '쇼핑', '음식점')
ANCHORS = {
    'seoul': ('11', (('광화문', 37.575, 126.977), ('강남', 37.498, 127.028), ('홍대', 37.556, 126.924))),
    'busan': ('26', (('해운대', 35.160, 129.160), ('서면', 35.158, 129.059), ('남포', 35.097, 129.030))),
    'jeju': ('50', (('제주시', 33.500, 126.530), ('서귀포', 33.250, 126.560), ('성산', 33.460, 126.940))),
}


def select_pilot_cohort(per_city=120):
    if per_city < len(CATEGORIES) or per_city % len(CATEGORIES):
        raise ValueError('per_city must be a positive multiple of six')
    per_category = per_city // len(CATEGORIES)
    cells = {}
    for city, (region_prefix, anchors) in ANCHORS.items():
        for category in CATEGORIES:
            sources = list(PlaceSource.objects.filter(
                source=ExternalSource.TOUR_API,
                match_status=PlaceSource.MatchStatus.MATCHED,
                place__region_code__startswith=region_prefix,
                place__category=category,
            ).exclude(place__open_status=Place.OpenStatus.CLOSED).select_related('place'))
            ranked = []
            for anchor_name, lat, lon in anchors:
                ranked.append((anchor_name, sorted(
                    sources, key=lambda source: (
                        _haversine_km(lat, lon, source.place), source.external_id,
                    ),
                )))
            selected = []
            used = set()
            positions = [0] * len(ranked)
            while len(selected) < per_category:
                advanced = False
                for index, (anchor_name, ordered) in enumerate(ranked):
                    while positions[index] < len(ordered) and ordered[positions[index]].external_id in used:
                        positions[index] += 1
                    if positions[index] >= len(ordered):
                        continue
                    source = ordered[positions[index]]
                    positions[index] += 1
                    used.add(source.external_id)
                    selected.append({
                        'external_id': source.external_id,
                        'city': city,
                        'category': category,
                        'anchor': anchor_name,
                    })
                    advanced = True
                    if len(selected) == per_category:
                        break
                if not advanced:
                    break
            cells[(city, category)] = selected
    # Interleave cells so each day's bounded batch has the same city/category mix.
    result = []
    for index in range(per_category):
        for city in ANCHORS:
            for category in CATEGORIES:
                selected = cells[(city, category)]
                if index < len(selected):
                    result.append(selected[index])
    return result
