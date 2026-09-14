import json
import os
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from places.job_models import DataJob, ProviderCallBudget
from places.models import ExternalSource, Place, PlaceSource, WeatherForecast
from places.services.jobs import LANE_SHARE, enqueue
from places.services.pilot import select_pilot_cohort
from places.services.weather import grid_for, latest_available_issue


class Command(BaseCommand):
    help = 'Create a stable public-place pilot cohort and optionally queue a budgeted detail batch.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', type=Path, required=True)
        parser.add_argument('--create', action='store_true')
        parser.add_argument('--per-city', type=int, default=120)
        parser.add_argument('--enqueue-limit', type=int, default=0)
        parser.add_argument('--weather-grids', type=int, default=0)

    def handle(self, *args, **options):
        path = options['manifest']
        if options['create']:
            if path.exists():
                raise CommandError('Manifest already exists; keep the pilot cohort stable')
            try:
                entries = select_pilot_cohort(options['per_city'])
            except ValueError as exc:
                raise CommandError(str(exc)) from None
            if len(entries) != 3 * options['per_city']:
                raise CommandError(f'Only {len(entries)} eligible sources found')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                'selection_version': 'pilot-1', 'per_city': options['per_city'],
                'entries': entries,
            }, ensure_ascii=False, indent=2) + '\n')
        if not path.exists():
            raise CommandError('Create the manifest first with --create')
        manifest = json.loads(path.read_text())
        if manifest.get('selection_version') != 'pilot-1' or not isinstance(manifest.get('entries'), list):
            raise CommandError('Invalid pilot manifest')
        entries = manifest['entries']
        self.stdout.write(f'cohort={len(entries)} city={dict(Counter(e["city"] for e in entries))} '
                          f'category={dict(Counter(e["category"] for e in entries))}')
        limit = options['enqueue_limit']
        if not 0 <= limit <= 200:
            raise CommandError('--enqueue-limit must be 0..200')
        if limit:
            available = self._available_calls('tour_api')
            remaining = PlaceSource.objects.filter(
                source=ExternalSource.TOUR_API,
                external_id__in=[entry['external_id'] for entry in entries],
                match_status=PlaceSource.MatchStatus.MATCHED,
                place__info__isnull=True,
            ).count()
            needed = min(limit, remaining)
            if needed * 2 > available:
                raise CommandError(f'Batch needs at most {needed * 2} calls; regular lane has {available} left')
            self._queue_details(entries, limit, available)
        if options['weather_grids']:
            self._queue_weather(entries, options['weather_grids'])

    @staticmethod
    def _available_calls(provider):
        daily_limit = int(os.environ.get({'tour_api': 'TOUR_API_DAILY_LIMIT',
                                          'kma': 'KMA_DAILY_LIMIT'}[provider], '0'))
        used = ProviderCallBudget.objects.filter(provider=provider, date=timezone.localdate(),
                                                lane='regular').values_list('used', flat=True).first() or 0
        return max(0, int(daily_limit * LANE_SHARE['regular']) - used)

    def _queue_details(self, entries, limit, available):
        queued = 0
        already_detailed = 0
        already_queued = 0
        for entry in entries:
            if queued >= limit:
                break
            source = PlaceSource.objects.filter(source=ExternalSource.TOUR_API,
                                                external_id=entry['external_id'],
                                                match_status=PlaceSource.MatchStatus.MATCHED,
                                                place__isnull=False).select_related('place').first()
            if source is None:
                continue
            if hasattr(source.place, 'info'):
                already_detailed += 1
                continue
            job = enqueue('tour_detail', str(source.pk), payload={'source_id': source.pk},
                          window=timezone.localdate().strftime('%Y%m%d'))
            if job.status == DataJob.Status.SUCCEEDED:
                already_queued += 1
                continue
            if job.status == DataJob.Status.FAILED:
                already_queued += 1
                continue
            queued += 1
        self.stdout.write(f'queued_or_pending={queued} already_detailed={already_detailed} '
                          f'already_finished_today={already_queued} max_new_calls={queued * 2} '
                          f'regular_calls_remaining_before_run={available}')

    def _queue_weather(self, entries, limit):
        if not 1 <= limit <= 100:
            raise CommandError('--weather-grids must be 0..100')
        issue = latest_available_issue(timezone.now())
        planned = []
        seen = set()
        for entry in entries:
            source = PlaceSource.objects.filter(source=ExternalSource.TOUR_API,
                external_id=entry['external_id'], match_status=PlaceSource.MatchStatus.MATCHED,
                place__isnull=False).select_related('place').first()
            if source is None or source.place.indoor_outdoor == Place.IndoorOutdoor.UNKNOWN:
                continue
            grid = grid_for(source.place.latitude, source.place.longitude)
            if grid is None or grid in seen:
                continue
            seen.add(grid)
            if WeatherForecast.objects.filter(grid_x=grid[0], grid_y=grid[1], issued_at=issue).exists():
                continue
            planned.append(grid)
            if len(planned) >= limit:
                break
        available = self._available_calls('kma')
        if len(planned) * 2 > available:
            raise CommandError(f'Weather batch reserves {len(planned) * 2} calls; regular lane has {available} left')
        for grid in planned:
            enqueue('weather', f'{grid[0]}:{grid[1]}',
                payload={'grid': grid, 'issued_at': issue.isoformat()},
                window=issue.strftime('%Y%m%d%H'))
        self.stdout.write(f'weather_grids_queued={len(planned)} max_calls={len(planned) * 2} '
                          f'kma_regular_calls_remaining_before_run={available}')
