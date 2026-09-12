from django.core.management.base import BaseCommand, CommandError
from places.models import Place
from places.services.place_resolver import import_geometry, resolve_places


class Command(BaseCommand):
    help = 'Import verified WGS84 Seoul polygons and resolve registered POIs without API calls.'

    def add_arguments(self, parser):
        parser.add_argument('--path')
        parser.add_argument('--resolve', action='store_true')

    def handle(self, *args, **options):
        try:
            count = import_geometry(options['path'])
        except (ValueError, OSError, KeyError) as error:
            raise CommandError(str(error)) from None
        resolved = resolve_places(Place.objects.prefetch_related('sources').iterator(chunk_size=500)) if options['resolve'] else 0
        self.stdout.write(f'areas={count} places_resolved={resolved}')
