"""Read-only, fixed-location comparison of ranking policies on the local DB."""

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from django.utils import timezone

from places.management.commands.evaluate_pilot import BENCHMARK_CENTERS
from places.models import CrowdData, Place, PlaceInfo, WeatherForecast
from places.views import _haversine_km, _nearby_bounding_box, _visible_places
from recommendations.service import MVP_CATEGORIES, _event_valid_at, recommend


def _distance_baseline(lat, lon, radius, limit, visit_at):
    """Apply the recommendation eligibility contract, then sort by distance."""
    lat_min, lat_max, lon_min, lon_max = _nearby_bounding_box(lat, lon, radius)
    queryset = _visible_places().filter(
        category__in=MVP_CATEGORIES,
        latitude__gte=lat_min, latitude__lte=lat_max,
        longitude__gte=lon_min, longitude__lte=lon_max,
    ).exclude(open_status=Place.OpenStatus.CLOSED)
    valid_events = {
        place_id for place_id, raw in PlaceInfo.objects.filter(
            place__category='축제/공연/행사',
            place__latitude__gte=lat_min, place__latitude__lte=lat_max,
            place__longitude__gte=lon_min, place__longitude__lte=lon_max,
        ).values_list('place_id', 'raw_data')
        if _event_valid_at(raw, visit_at)
    }
    distances = [(_haversine_km(lat, lon, place), place) for place in queryset
                 if place.category != '축제/공연/행사' or place.id in valid_events]
    distances.sort(key=lambda entry: (entry[0], entry[1].id))
    return [{'id': place.id, 'name': place.name, 'category': place.category,
             'distance_km': round(distance, 3)}
            for distance, place in distances if distance <= radius][:limit]


def _items_from_recommendation(items):
    return [{'id': item['place']['id'], 'name': item['place']['name'],
             'category': item['place']['category'], 'distance_km': item['distance_km'],
             'weather_scored': 'weather' in item['score_contributors']}
            for item in items]


def _summary(items):
    return {
        'count': len(items),
        'mean_distance_km': round(sum(item['distance_km'] for item in items) / len(items), 3) if items else None,
        'max_distance_km': max((item['distance_km'] for item in items), default=None),
        'category_count': len({item['category'] for item in items}),
        'weather_scored': sum(item.get('weather_scored', False) for item in items),
        'top_three': [item['name'] for item in items[:3]],
        'ids': [item['id'] for item in items],
    }


class Command(BaseCommand):
    help = 'Compare pure distance, weather off, and default recommendations without writes or provider calls.'

    def add_arguments(self, parser):
        parser.add_argument('--at', required=True, help='Offset-aware ISO 8601 request time')
        parser.add_argument('--radius-km', type=float, default=10)

    def handle(self, *args, **options):
        try:
            at = datetime.fromisoformat(options['at'])
        except ValueError:
            raise CommandError('--at must be an ISO 8601 timestamp') from None
        if timezone.is_naive(at):
            raise CommandError('--at must include a UTC offset')
        radius = options['radius_km']
        if not 0.1 <= radius <= 100:
            raise CommandError('--radius-km must be between 0.1 and 100')
        cities = {}
        for city, (lat, lon) in BENCHMARK_CENTERS.items():
            criteria = {'latitude': lat, 'longitude': lon, 'radius_km': radius,
                        'crowd_level': 'any', 'limit': 10}
            distance = _distance_baseline(lat, lon, radius, 10, at)
            weather_off = _items_from_recommendation(recommend(
                {**criteria, 'weather_aware': False}, now=at, supplement=False)[0]['items'])
            default = _items_from_recommendation(recommend(
                criteria, now=at, supplement=False)[0]['items'])
            cities[city] = {
                'distance_only': _summary(distance),
                'weather_off_travel_intent': _summary(weather_off),
                'default': _summary(default),
                'weather_on_off_top_ten_overlap': len(
                    {item['id'] for item in weather_off} & {item['id'] for item in default}),
            }
        result = {
            'evaluated_at': at.isoformat(),
            'radius_km': radius,
            'provider_calls': 0,
            'database_writes': 0,
            'snapshot': {
                'places': Place.objects.count(),
                'classified': Place.objects.exclude(indoor_outdoor=Place.IndoorOutdoor.UNKNOWN).count(),
                'weather_latest_issued_at': (WeatherForecast.objects.aggregate(v=Max('issued_at'))['v'] or None),
                'crowd_latest_observed_at': (CrowdData.objects.aggregate(v=Max('observed_at'))['v'] or None),
            },
            'cities': cities,
        }
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, indent=2))
