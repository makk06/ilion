from django.core.management.base import BaseCommand, CommandError

from places.catalog import CatalogConfigurationError, load_seoul_crowd_catalog
from places.services import SeoulPlaceMappingService


class Command(BaseCommand):
    help = 'Apply and audit versioned TourAPI-to-Seoul crowd area mappings.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        try:
            catalog = load_seoul_crowd_catalog()
        except CatalogConfigurationError as error:
            raise CommandError(str(error)) from None

        result = SeoulPlaceMappingService().apply(
            catalog.mappings,
            dry_run=options['dry_run'],
        )
        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}catalog={catalog.version} attempted={result.attempted} '
                f'created={result.created} updated={result.updated} '
                f'missing_places={len(result.missing_places)} '
                f'missing_areas={len(result.missing_areas)}'
            )
        )
        if result.missing_places:
            self.stdout.write(
                self.style.WARNING(
                    'missing place source IDs: '
                    + ', '.join(result.missing_places)
                )
            )
        if result.missing_areas:
            self.stdout.write(
                self.style.WARNING(
                    'missing Seoul AREA_CD values: '
                    + ', '.join(sorted(set(result.missing_areas)))
                )
            )
