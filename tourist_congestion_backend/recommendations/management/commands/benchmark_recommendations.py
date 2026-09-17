"""Read-only recommendation latency and query-count benchmark."""

import json
import math
from datetime import datetime
from statistics import median
from time import perf_counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from places.management.commands.evaluate_pilot import BENCHMARK_CENTERS
from recommendations.service import (
    clear_recommendation_context_cache, prepare_recommendations, recommend,
)


class Command(BaseCommand):
    help = 'Measure stored-data recommendation latency without writes or provider calls.'

    def add_arguments(self, parser):
        parser.add_argument('--runs', type=int, default=3)
        parser.add_argument('--radius-km', type=float, default=10)
        parser.add_argument('--city', action='append', choices=sorted(BENCHMARK_CENTERS))
        parser.add_argument('--at', help='Optional offset-aware ISO 8601 request time')

    def handle(self, *args, **options):
        runs = options['runs']
        radius = options['radius_km']
        if not 1 <= runs <= 20:
            raise CommandError('--runs must be between 1 and 20')
        if not 0.1 <= radius <= 100:
            raise CommandError('--radius-km must be between 0.1 and 100')
        at = self._request_time(options['at'])
        selected = options['city'] or list(BENCHMARK_CENTERS)
        clear_recommendation_context_cache()
        results = {}
        for city in selected:
            latitude, longitude = BENCHMARK_CENTERS[city]
            criteria = {
                'latitude': latitude,
                'longitude': longitude,
                'radius_km': radius,
                'crowd_level': 'any',
                'weather_aware': True,
                'limit': 10,
            }
            durations = []
            preparation_durations = []
            ranking_durations = []
            query_counts = []
            candidate_count = 0
            top_ids = []
            for _ in range(runs):
                with CaptureQueriesContext(connection) as queries:
                    started = perf_counter()
                    prepared = prepare_recommendations(criteria, now=at, supplement=False)
                    prepared_at = perf_counter()
                    data, _ = recommend(criteria, now=at, supplement=False, prepared=prepared)
                    finished = perf_counter()
                    preparation_durations.append(round((prepared_at - started) * 1000, 2))
                    ranking_durations.append(round((finished - prepared_at) * 1000, 2))
                    durations.append(round((finished - started) * 1000, 2))
                query_counts.append(len(queries))
                candidate_count = data['candidate_count']
                top_ids = [item['place']['id'] for item in data['items']]
            nearby_offset_km = min(settings.RECOMMENDATION_CONTEXT_REUSE_KM / 2, 0.25)
            nearby_criteria = {
                **criteria,
                'latitude': latitude + nearby_offset_km / 111.32,
            }
            with CaptureQueriesContext(connection) as nearby_queries:
                started = perf_counter()
                nearby_prepared = prepare_recommendations(
                    nearby_criteria, now=at, supplement=False,
                )
                nearby_data, _ = recommend(
                    nearby_criteria,
                    now=at,
                    supplement=False,
                    prepared=nearby_prepared,
                )
                nearby_ms = round((perf_counter() - started) * 1000, 2)
            smaller_radius = max(0.1, radius / 2)
            smaller_ms = None
            smaller_query_count = None
            smaller_candidate_count = None
            if smaller_radius < radius:
                smaller_criteria = {**criteria, 'radius_km': smaller_radius}
                with CaptureQueriesContext(connection) as smaller_queries:
                    started = perf_counter()
                    smaller_prepared = prepare_recommendations(
                        smaller_criteria, now=at, supplement=False,
                    )
                    smaller_data, _ = recommend(
                        smaller_criteria,
                        now=at,
                        supplement=False,
                        prepared=smaller_prepared,
                    )
                    smaller_ms = round((perf_counter() - started) * 1000, 2)
                smaller_query_count = len(smaller_queries)
                smaller_candidate_count = smaller_data['candidate_count']
            ordered = sorted(durations)
            results[city] = {
                'candidate_count': candidate_count,
                'top_ids': top_ids,
                'runs_ms': durations,
                'cold_ms': durations[0],
                'warm_median_ms': round(median(durations[1:]), 2) if len(durations) > 1 else None,
                'median_ms': round(median(durations), 2),
                'p95_ms': ordered[math.ceil(len(ordered) * 0.95) - 1],
                'preparation_runs_ms': preparation_durations,
                'ranking_runs_ms': ranking_durations,
                'query_counts': query_counts,
                'nearby_offset_km': nearby_offset_km,
                'nearby_ms': nearby_ms,
                'nearby_query_count': len(nearby_queries),
                'nearby_candidate_count': nearby_data['candidate_count'],
                'smaller_radius_km': smaller_radius,
                'smaller_radius_ms': smaller_ms,
                'smaller_radius_query_count': smaller_query_count,
                'smaller_radius_candidate_count': smaller_candidate_count,
            }
        self.stdout.write(json.dumps({
            'evaluated_at': at.isoformat(),
            'radius_km': radius,
            'runs': runs,
            'provider_calls': 0,
            'database_writes': 0,
            'context_cache_seconds': settings.RECOMMENDATION_CONTEXT_CACHE_SECONDS,
            'context_reuse_km': settings.RECOMMENDATION_CONTEXT_REUSE_KM,
            'cities': results,
        }, ensure_ascii=False, indent=2))

    @staticmethod
    def _request_time(raw):
        if not raw:
            return timezone.now()
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            raise CommandError('--at must be an ISO 8601 timestamp') from None
        if timezone.is_naive(value):
            raise CommandError('--at must include a UTC offset')
        return value
