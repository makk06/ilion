import math

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from places.services.jobs import enqueue
from places.services.weather import grid_for, latest_available_issue


class Command(BaseCommand):
    help = 'Queue bounded nationwide TourAPI or grid-shared KMA collection; worker performs calls.'

    def add_arguments(self, parser):
        parser.add_argument('--tour', action='store_true')
        parser.add_argument('--max-pages', type=int, default=1)
        parser.add_argument('--page-size', type=int, default=1000)
        parser.add_argument('--modified-since', help='YYYYMMDD')
        parser.add_argument('--region-code')
        parser.add_argument('--weather-at', nargs=2, type=float, metavar=('LAT', 'LON'))
        parser.add_argument('--detail-place-id', type=int)
        parser.add_argument('--estimate-tour', action='store_true')

    def handle(self, *args, **options):
        if not 1 <= options['page_size'] <= 1000 or options['max_pages'] < 1:
            raise CommandError('page size must be 1..1000 and max pages must be positive')
        if options['estimate_tour']:
            from places.integrations.tour_api import TourAPIClient
            from places.integrations.exceptions import ExternalAPIError
            from places.services.jobs import BudgetExceeded, debit
            try:
                client = TourAPIClient()
                debit('tour_api', 'regular')
                page = client.fetch_places_page(
                    page_size=options['page_size'], modified_since=options['modified_since'],
                    region_code=options['region_code'])
            except (BudgetExceeded, ExternalAPIError) as exc:
                raise CommandError(str(exc)) from None
            expected = math.ceil(page.total_count / options['page_size'])
            self.stdout.write(f'TourAPI reported {page.total_count} records; estimated {expected} list calls at this page size. Detail calls cost 2 each.')
            return
        if options['tour']:
            now = timezone.localtime()
            key = ':'.join([options['region_code'] or 'nationwide', options['modified_since'] or 'full'])
            job = enqueue('tour_places', key, payload={
                'page_size': options['page_size'], 'max_pages': options['max_pages'],
                'modified_since': options['modified_since'], 'region_code': options['region_code'],
            }, window=now.strftime('%Y%m%d'))
            self.stdout.write(f'TourAPI job {job.id} status={job.status}; maximum list calls={options["max_pages"]}')
        if options['weather_at']:
            grid = grid_for(*options['weather_at'])
            if grid is None:
                raise CommandError('Coordinate is outside KMA short-forecast grid coverage')
            issue = latest_available_issue(timezone.now())
            job = enqueue('weather', f'{grid[0]}:{grid[1]}',
                payload={'grid': grid, 'issued_at': issue.isoformat()},
                window=issue.strftime('%Y%m%d%H'))
            self.stdout.write(f'KMA grid={grid} job={job.id} status={job.status}')
        if options['detail_place_id']:
            from places.models import PlaceSource, ExternalSource
            source = PlaceSource.objects.filter(place_id=options['detail_place_id'], source=ExternalSource.TOUR_API,
                match_status=PlaceSource.MatchStatus.MATCHED).first()
            if source is None:
                raise CommandError('No matched TourAPI source for this place')
            job = enqueue('tour_detail', str(source.pk), payload={'source_id': source.pk})
            self.stdout.write(f'TourAPI detail job={job.id} status={job.status}; maximum calls=2')
        if not options['tour'] and not options['weather_at'] and not options['detail_place_id']:
            raise CommandError('Choose --tour, --weather-at, --detail-place-id, or --estimate-tour')
