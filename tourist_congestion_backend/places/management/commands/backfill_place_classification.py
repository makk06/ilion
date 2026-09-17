from django.core.management.base import BaseCommand

from places.models import Place
from places.services.classification import classify_place


class Command(BaseCommand):
    help = 'Apply conservative evidence-based indoor/outdoor name rules to unclassified places.'

    def handle(self, *args, **options):
        classified = 0
        scanned = 0
        places = Place.objects.filter(indoor_outdoor=Place.IndoorOutdoor.UNKNOWN).iterator(chunk_size=1000)
        for place in places:
            scanned += 1
            classified += int(classify_place(place))
        self.stdout.write(f'scanned={scanned} classified={classified}')
