import re

from django.core.management.base import BaseCommand, CommandError

from places.integrations import ExternalAPIError
from places.integrations.tour_api import TourAPIClient
from places.services import TourPlaceSyncService


class Command(BaseCommand):
    help = 'Synchronize nationwide places from Korea Tourism Organization TourAPI.'

    def add_arguments(self, parser):
        parser.add_argument('--page-size', type=int, default=100)
        parser.add_argument('--max-pages', type=int)
        parser.add_argument('--modified-since', help='YYYYMMDD')
        parser.add_argument('--region-code', help='TourAPI legal-dong region code')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if not 1 <= options['page_size'] <= 1000:
            raise CommandError('--page-size must be between 1 and 1000')
        if options['max_pages'] is not None and options['max_pages'] < 1:
            raise CommandError('--max-pages must be at least 1')
        modified_since = options['modified_since']
        if modified_since and not re.fullmatch(r'\d{8}', modified_since):
            raise CommandError('--modified-since must use YYYYMMDD')

        try:
            result = TourPlaceSyncService(TourAPIClient()).sync(
                page_size=options['page_size'],
                max_pages=options['max_pages'],
                modified_since=modified_since,
                region_code=options['region_code'],
                dry_run=options['dry_run'],
            )
        except ExternalAPIError as error:
            raise CommandError(str(error)) from None

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}pages={result.pages} processed={result.processed} '
                f'sources_created={result.sources_created} '
                f'sources_updated={result.sources_updated} '
                f'places_created={result.places_created} '
                f'unmatched={result.unmatched} inactive={result.inactive}'
            )
        )
