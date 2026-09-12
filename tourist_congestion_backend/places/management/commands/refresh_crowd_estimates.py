from django.core.management.base import BaseCommand
from django.utils import timezone
from places.models import Place
from places.services.crowd_inputs import estimates_for


class Command(BaseCommand):
    help = 'Refresh mapped place snapshots without external API calls.'

    def add_arguments(self, parser):
        parser.add_argument('--place-id', type=int, action='append')

    def handle(self, *args, **options):
        query = Place.objects.filter(pk__in=options['place_id']) if options['place_id'] else Place.objects.filter(crowd_area_mappings__verified=True).distinct()
        count, chunk = 0, []
        now = timezone.now()
        for place in query.iterator(chunk_size=100):
            chunk.append(place)
            if len(chunk) == 100:
                estimates_for(chunk, now, persist=True)
                count += len(chunk)
                chunk = []
        estimates_for(chunk, now, persist=True)
        self.stdout.write(f'estimates={count+len(chunk)}')
