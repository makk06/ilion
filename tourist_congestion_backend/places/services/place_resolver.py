import json
import math
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from shapely import make_valid
from shapely.geometry import Point, Polygon, shape, mapping as geometry_mapping
from shapely.ops import transform

from places.integrations.weather import weather_grid
from places.models import CrowdArea, ExternalSource, PlaceCrowdArea, PlaceCrowdProfile
from .crowd_estimator import profile_for, profiles


def import_geometry(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[1]/'data/seoul_crowd_geometry.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    features = data.get('features', [])
    ids = [f['properties']['AREA_CD'] for f in features]
    if len(features) != 121 or len(set(ids)) != 121:
        raise ValueError('Expected 121 unique official Seoul areas')
    prepared = []
    for feature in features:
        geo = shape(feature['geometry'])
        repaired = not geo.is_valid
        if repaired:
            geo = make_valid(geo)
        if not geo.is_valid or geo.is_empty or geo.geom_type not in ('Polygon', 'MultiPolygon'):
            raise ValueError('Invalid official area polygon')
        bounds = list(geo.bounds)
        if not (124 < bounds[0] < bounds[2] < 132 and 33 < bounds[1] < bounds[3] < 39):
            raise ValueError('Expected Korean WGS84 coordinates')
        prepared.append((feature, bounds, geo, repaired))
    with transaction.atomic():
        for feature, bounds, geo, repaired in prepared:
            prop = feature['properties']
            CrowdArea.objects.update_or_create(source=ExternalSource.SEOUL_REALTIME, external_id=prop['AREA_CD'], defaults={
                'name': prop['AREA_NM'], 'region_code': '11', 'geometry': geometry_mapping(geo),
                'bounds': bounds, 'geometry_version': data['version'], 'last_synced_at': timezone.now(),
                'raw_data': {'category': prop['CATEGORY'], 'source_url': data['source_url'], 'geometry_repaired': repaired}})
    return len(prepared)


def select_mapping(mappings, now):
    """Choose an approved mapping without making row order an approval policy."""
    eligible = [m for m in mappings if m.verified
                and (not m.valid_from or m.valid_from <= now)
                and (not m.valid_until or m.valid_until > now)]
    preferred = [m for m in eligible if m.match_method in ('manual', 'source')]
    candidates = preferred or eligible
    if not candidates:
        return None, None
    primary = [m for m in candidates if m.is_primary]
    if len(primary) == 1:
        return primary[0], None
    if len(candidates) == 1:
        return candidates[0], None
    return None, 'APPROVAL_CONFLICT'


def polygon_diagnostics(lat, lon, areas):
    try:
        lat, lon = float(lat), float(lon)
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except (TypeError, ValueError):
        return {'reason': 'NO_COORDINATE', 'area': None, 'candidates': []}
    point = Point(lon, lat)
    hits, candidates = [], []
    in_hole = False
    for area, geometry in areas:
        polygons = [geometry] if geometry.geom_type == 'Polygon' else geometry.geoms
        in_hole = in_hole or any(point.within(Polygon(r))
                                   for polygon in polygons for r in polygon.interiors)
        if geometry.covers(point):
            scale_x = 111320 * math.cos(math.radians(lat))
            projected = transform(lambda x, y, z=None: ((x-lon)*scale_x, (y-lat)*111320), geometry)
            distance = projected.boundary.distance(Point(0, 0))
            hits.append((area, distance))
            candidates.append({'area_id': getattr(area, 'external_id', area),
                               'boundary_distance_m': round(distance, 2),
                               'geometry_version': getattr(area, 'geometry_version', '')})
    reason = ('OVERLAP' if len(hits) > 1 else 'BOUNDARY' if hits and hits[0][1] <= 50
              else None if hits else 'HOLE' if in_hole else 'OUTSIDE')
    return {'reason': reason, 'area': hits[0][0] if reason is None else None, 'candidates': candidates}


def polygon_match(lat, lon, areas):
    return polygon_diagnostics(lat, lon, areas)['area']


def resolve_places(places):
    areas = [(area, shape(area.geometry)) for area in CrowdArea.objects.exclude(geometry={})]
    now = timezone.now()
    count = 0
    for place in places:
        sources = list(place.sources.all())
        source = next((s for s in sources if s.source == ExternalSource.TOUR_API and s.match_status == 'matched'), None)
        raw = source.raw_data if source else {}
        gx, gy = weather_grid(float(place.latitude), float(place.longitude))
        existing = PlaceCrowdProfile.objects.filter(place=place).first()
        evidence = {'type': 'category_inference', 'source': 'tour_api' if source else 'place_category',
                    'source_id': source.external_id if source else None, 'category': source.source_category if source else place.category}
        if not existing or existing.evidence.get('type') != 'manual':
            PlaceCrowdProfile.objects.update_or_create(place=place, defaults={
                'profile': profile_for(raw, place.category), 'version': profiles()['version'],
                'evidence': evidence, 'grid_x': gx, 'grid_y': gy})
        mappings = list(PlaceCrowdArea.objects.filter(place=place).order_by('-is_primary', 'id'))
        manual, conflict = select_mapping([m for m in mappings if m.match_method in ('manual', 'source')], now)
        if conflict:
            continue
        with transaction.atomic():
            if manual:
                PlaceCrowdArea.objects.filter(place=place, is_primary=True).exclude(pk=manual.pk).update(is_primary=False)
                if not manual.is_primary:
                    manual.is_primary = True
                    manual.save(update_fields=['is_primary'])
            else:
                area = polygon_match(float(place.latitude), float(place.longitude), areas)
                PlaceCrowdArea.objects.filter(place=place, match_method='coordinate').update(is_primary=False, verified=False)
                if area:
                    PlaceCrowdArea.objects.filter(place=place, is_primary=True).update(is_primary=False)
                    PlaceCrowdArea.objects.update_or_create(place=place, crowd_area=area, defaults={
                        'match_method': 'coordinate', 'match_quality': .9, 'representativeness': .65,
                        'verified': True, 'is_primary': True, 'valid_from': now, 'valid_until': None,
                        'evidence': {'type': 'polygon', 'geometry_version': area.geometry_version,
                                     'latitude': str(place.latitude), 'longitude': str(place.longitude)}})
        count += 1
    return count
