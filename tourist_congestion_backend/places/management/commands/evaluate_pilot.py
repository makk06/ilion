import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from places.models import ExternalSource, Place, PlaceSource
from recommendations.service import recommend


BENCHMARK_CENTERS = {
    'seoul': (37.575, 126.977),
    'busan': (35.160, 129.160),
    'jeju': (33.500, 126.530),
    'daejeon': (36.350, 127.385),
    'daegu': (35.872, 128.602),
    'gwangju': (35.160, 126.851),
    'gangneung': (37.752, 128.876),
}


class Command(BaseCommand):
    help = 'Measure public-place detail coverage and seven-city recommendation evidence.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', type=Path, required=True)
        parser.add_argument('--output', type=Path, required=True)
        parser.add_argument('--at', help='Replay an offset-aware ISO 8601 visit/observation time')

    def handle(self, *args, **options):
        manifest = json.loads(options['manifest'].read_text())
        if manifest.get('selection_version') != 'pilot-1':
            raise CommandError('Invalid pilot manifest')
        external_ids = [entry['external_id'] for entry in manifest['entries']]
        sources = PlaceSource.objects.filter(source=ExternalSource.TOUR_API,
                                             external_id__in=external_ids).select_related('place', 'place__info')
        by_external_id = {source.external_id: source for source in sources}
        cohort = Counter()
        by_city = {city: Counter() for city in ('seoul', 'busan', 'jeju')}
        for entry in manifest['entries']:
            city = entry['city']
            source = by_external_id.get(entry['external_id'])
            for bucket in (cohort, by_city[city]):
                bucket['selected'] += 1
                if source is None or source.place_id is None:
                    bucket['unmatched'] += 1
                    continue
                place = source.place
                info = getattr(place, 'info', None)
                if info:
                    bucket['detail'] += 1
                    bucket['description'] += bool(info.description)
                    bucket['image'] += bool(info.first_image_url)
                bucket['classified'] += place.indoor_outdoor != Place.IndoorOutdoor.UNKNOWN
        try:
            now = datetime.fromisoformat(options['at']) if options['at'] else timezone.now()
        except ValueError:
            raise CommandError('--at must be an ISO 8601 timestamp') from None
        if timezone.is_naive(now):
            raise CommandError('--at must include a UTC offset')
        benchmark = {}
        cohort_place_ids = {source.place_id for source in sources if source.place_id}
        for city, (lat, lon) in BENCHMARK_CENTERS.items():
            criteria = {'latitude': lat, 'longitude': lon, 'radius_km': 10,
                        'crowd_level': 'any', 'limit': 10}
            started = perf_counter()
            data, _ = recommend(criteria, now=now, supplement=False)
            elapsed_ms = round((perf_counter() - started) * 1000, 1)
            items = data['items']
            benchmark[city] = {
                'candidate_count': data['candidate_count'], 'returned': len(items),
                'weather_evidence': sum(item['weather'] is not None for item in items),
                'indoor_outdoor_evidence': sum(item['place']['indoor_outdoor'] != 'unknown' for item in items),
                'crowd_evidence': sum(item['crowd'] is not None for item in items),
                'cohort_exposure': sum(item['place']['id'] in cohort_place_ids for item in items),
                'category_count': len({item['place']['category'] for item in items}),
                'mean_data_coverage': round(sum(item['data_coverage'] for item in items) / len(items), 3) if items else 0,
                'elapsed_ms': elapsed_ms,
            }
            weather_data, weather_message = recommend(
                {**criteria, 'weather_evidence_required': True},
                now=now, supplement=False,
            )
            benchmark[city]['weather_required'] = {
                'candidate_count': weather_data['candidate_count'],
                'returned': len(weather_data['items']),
                'shortage': bool(weather_message),
            }
        result = {'measured_at': timezone.now().isoformat(), 'evaluated_at': now.isoformat(),
                  'cohort': dict(cohort),
                  'cohort_by_city': {city: dict(counts) for city, counts in by_city.items()},
                  'default_recommendations': benchmark}
        options['output'].parent.mkdir(parents=True, exist_ok=True)
        options['output'].write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        self.stdout.write(f'cohort={dict(cohort)} benchmark_cities={len(benchmark)} '
                          f'output={options["output"]}')
