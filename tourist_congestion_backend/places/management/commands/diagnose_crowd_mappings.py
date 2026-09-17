"""Read-only JSON lines suitable for a review export."""
import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from shapely.geometry import shape
from places.models import Place, CrowdArea
from places.services.place_resolver import polygon_diagnostics, select_mapping


class Command(BaseCommand):
    help = 'Print mapping candidates and rejection reasons without approving them.'

    def add_arguments(self, parser):
        parser.add_argument('--place-id', action='append', type=int)

    def handle(self, *args, **options):
        areas = [(a, shape(a.geometry)) for a in CrowdArea.objects.exclude(geometry={})]
        places = Place.objects.all().prefetch_related('crowd_area_mappings__crowd_area')
        if options['place_id']:
            places = places.filter(pk__in=options['place_id'])
        for place in places:
            result = polygon_diagnostics(place.latitude, place.longitude, areas)
            selected, conflict = select_mapping(place.crowd_area_mappings.all(), timezone.now())
            result.pop('area')
            result.update(place_id=place.pk, latitude=str(place.latitude), longitude=str(place.longitude),
                          selected_area_id=selected.crowd_area.external_id if selected else None)
            if conflict:
                result['reason'] = conflict
            self.stdout.write(json.dumps(result, ensure_ascii=False))
