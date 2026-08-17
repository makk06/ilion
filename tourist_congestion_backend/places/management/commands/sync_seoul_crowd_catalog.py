from django.core.management.base import BaseCommand, CommandError

from places.catalog import CatalogConfigurationError, load_seoul_crowd_catalog
from places.integrations import ExternalAPIError
from places.integrations.seoul_realtime import SeoulRealtimeClient
from places.services import SeoulCrowdSyncService


class Command(BaseCommand):
    help = 'Synchronize the versioned initial Seoul crowd area catalog.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--area-code',
            action='append',
            dest='area_codes',
            help='Limit sync to a catalog AREA_CD; may be repeated',
        )
        parser.add_argument('--limit', type=int)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        try:
            catalog = load_seoul_crowd_catalog()
        except CatalogConfigurationError as error:
            raise CommandError(str(error)) from None

        selected = list(catalog.areas)
        requested_codes = list(dict.fromkeys(options['area_codes'] or []))
        if requested_codes:
            known_codes = {area.external_id for area in catalog.areas}
            unknown_codes = sorted(set(requested_codes) - known_codes)
            if unknown_codes:
                raise CommandError(
                    'Unknown Seoul catalog area codes: ' + ', '.join(unknown_codes)
                )
            selected = [
                area for area in selected if area.external_id in requested_codes
            ]
        if options['limit'] is not None:
            if not 1 <= options['limit'] <= len(selected):
                raise CommandError(
                    f'--limit must be between 1 and {len(selected)}'
                )
            selected = selected[: options['limit']]

        try:
            result = SeoulCrowdSyncService(SeoulRealtimeClient()).sync(
                [area.external_id for area in selected],
                dry_run=options['dry_run'],
                continue_on_error=True,
            )
        except ExternalAPIError as error:
            raise CommandError(str(error)) from None

        prefix = '[dry-run] ' if options['dry_run'] else ''
        summary = (
            f'{prefix}catalog={catalog.version} selected={len(selected)} '
            f'processed={result.areas_processed} failed={result.failed} '
            f'areas_created={result.areas_created} '
            f'observations_created={result.observations_created} '
            f'observations_updated={result.observations_updated}'
        )
        if result.failed:
            raise CommandError('Seoul crowd catalog sync incomplete: ' + summary)
        self.stdout.write(self.style.SUCCESS(summary))
