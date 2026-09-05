from django.core.management.base import BaseCommand, CommandError

from places.integrations import ExternalAPIError
from places.integrations.seoul_realtime import SeoulRealtimeClient
from places.services import SeoulCrowdSyncService


class Command(BaseCommand):
    help = 'Synchronize current population congestion for selected Seoul areas.'

    def add_arguments(self, parser):
        parser.add_argument(
            'areas',
            nargs='+',
            help='One or more Seoul AREA_CD values or quoted area names',
        )
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        areas = list(dict.fromkeys(area.strip() for area in options['areas'] if area.strip()))
        if not areas:
            raise CommandError('At least one Seoul area is required')

        try:
            result = SeoulCrowdSyncService(SeoulRealtimeClient()).sync(
                areas,
                dry_run=options['dry_run'],
            )
        except ExternalAPIError as error:
            raise CommandError(str(error)) from None

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}areas={result.areas_processed} '
                f'areas_created={result.areas_created} '
                f'observations_created={result.observations_created} '
                f'observations_updated={result.observations_updated}'
            )
        )
