import fcntl
import json
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from places.catalog import load_seoul_crowd_catalog
from places.job_models import DataJob
from places.models import PlaceSource, ExternalSource
from places.services.jobs import enqueue, run_one
from places.services.weather import latest_available_issue
from datetime import timedelta
from django.db.models import Q


class Command(BaseCommand):
    help = 'Run the single SQLite data worker. --dev also schedules bounded Seoul refreshes.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--dev', action='store_true')
        parser.add_argument('--max-jobs', type=int, default=0,
                            help='Stop after this many jobs; zero keeps running.')

    def handle(self, *args, **options):
        if options['max_jobs'] < 0:
            raise CommandError('--max-jobs must be non-negative')
        lock_path = settings.BASE_DIR / '.data-worker.lock'
        with open(lock_path, 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CommandError('One data worker is already running') from None
            processed = 0
            while True:
                if options['dev']:
                    self._schedule_dev()
                job = run_one()
                if job:
                    processed += 1
                    self.stdout.write(f'job={job.id} kind={job.kind} status={job.status} cursor={job.cursor} processed={job.processed} error={job.error_code}')
                if options['once'] or options['max_jobs'] and processed >= options['max_jobs']:
                    break
                if not job:
                    if options['max_jobs']:
                        break
                    time.sleep(5)

    @staticmethod
    def _schedule_dev():
        now = timezone.localtime()
        if os.environ.get('MVP_AUTO_TOUR_SYNC', '').lower() == 'true':
            max_pages = max(1, int(os.environ.get('TOUR_SYNC_MAX_PAGES', '1')))
            if now.hour >= 3:
                since = (now - timedelta(days=1)).strftime('%Y%m%d')
                enqueue('tour_places', f'nationwide:daily:{since}',
                    payload={'page_size': 1000, 'max_pages': max_pages, 'modified_since': since},
                    window=now.strftime('%Y%m%d'))
            if now.weekday() == 6 and now.hour >= 4:
                enqueue('tour_places', 'nationwide:weekly',
                    payload={'page_size': 1000, 'max_pages': max_pages},
                    window=now.strftime('%Y%m%d'))
        window = now.strftime('%Y%m%d%H') + str(now.minute // 15)
        for area in load_seoul_crowd_catalog().areas:
            enqueue('seoul_crowd', area.external_id, window=window)
        if now.hour >= 4:
            pilot_manifest = os.environ.get('PILOT_COHORT_MANIFEST', '').strip()
            if pilot_manifest:
                daily_places = max(0, min(200, int(os.environ.get('PILOT_DETAIL_DAILY_PLACES', '150'))))
                already_scheduled = DataJob.objects.filter(kind='tour_detail',
                    created_at__date=now.date()).count()
                remaining = max(0, daily_places - already_scheduled)
                path = settings.BASE_DIR / pilot_manifest
                if not path.is_file():
                    raise CommandError(f'Pilot manifest does not exist: {path}')
                manifest = json.loads(path.read_text())
                if manifest.get('selection_version') != 'pilot-1':
                    raise CommandError('Invalid pilot manifest')
                for entry in manifest['entries']:
                    if remaining == 0:
                        break
                    source = PlaceSource.objects.filter(source=ExternalSource.TOUR_API,
                        external_id=entry['external_id'], match_status=PlaceSource.MatchStatus.MATCHED,
                        place__info__isnull=True).first()
                    if source:
                        enqueue('tour_detail', str(source.pk), payload={'source_id': source.pk},
                                window=now.strftime('%Y%m%d'))
                        remaining -= 1
            else:
                cutoff = timezone.now() - timedelta(days=7)
                sources = PlaceSource.objects.filter(source=ExternalSource.TOUR_API,
                    match_status=PlaceSource.MatchStatus.MATCHED).filter(
                        Q(place__info__isnull=True) | Q(place__info__updated_at__lt=cutoff)
                    ).order_by('last_synced_at', 'id')[:20]
                for source in sources:
                    enqueue('tour_detail', str(source.pk), payload={'source_id': source.pk}, window=now.strftime('%Y%m%d'))
        issue = latest_available_issue(timezone.now())
        recent = DataJob.objects.filter(kind='weather', created_at__gte=timezone.now() - timedelta(days=7)).order_by('-created_at')
        seen = set()
        for job in recent:
            grid = tuple(job.payload.get('grid') or ())
            if len(grid) != 2 or grid in seen:
                continue
            seen.add(grid)
            enqueue('weather', f'{grid[0]}:{grid[1]}', payload={'grid': grid, 'issued_at': issue.isoformat()},
                window=issue.strftime('%Y%m%d%H'))
            if len(seen) >= 5:
                break
