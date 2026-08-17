from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from places.dev_seed_data import (
    CROWD_AREA_ITEMS,
    PLACE_CROWD_AREA_MAPPINGS,
    TOUR_PLACE_INFO_ITEMS,
    TOUR_PLACE_ITEMS,
)
from places.integrations.tour_api import TourAPIPage, normalize_tour_place
from places.models import (
    CrowdArea,
    CrowdData,
    ExternalSource,
    Place,
    PlaceCrowdArea,
    PlaceInfo,
    PlaceSource,
)
from places.services import TourPlaceSyncService


class StaticTourClient:
    def __init__(self, records):
        self.records = records

    def fetch_places_page(self, **_kwargs):
        count = len(self.records)
        return TourAPIPage(
            records=self.records,
            page_number=1,
            page_size=max(count, 1),
            total_count=count,
        )


class Command(BaseCommand):
    help = 'Create or clear deterministic local development place data.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('seed_dev_data is only available when DEBUG=true')

        if options['clear']:
            result = self._clear()
            self.stdout.write(
                self.style.SUCCESS(
                    'cleared development data: '
                    f"places={result['places']} sources={result['sources']} "
                    f"infos={result['infos']} "
                    f"areas={result['areas']} observations={result['observations']}"
                )
            )
            return

        result = self._seed()
        self.stdout.write(
            self.style.SUCCESS(
                    'seeded development data: '
                    f"places={result['places']} sources={result['sources']} "
                    f"infos={result['infos']} "
                    f"areas={result['areas']} observations={result['observations']} "
                f"mappings={result['mappings']} skipped_real={result['skipped_real']}"
            )
        )

    @staticmethod
    @transaction.atomic
    def _seed():
        records = []
        skipped_real = 0
        for item in TOUR_PLACE_ITEMS:
            existing = PlaceSource.objects.filter(
                source=ExternalSource.TOUR_API,
                external_id=item['contentid'],
            ).first()
            if existing and not existing.raw_data.get('dev_seed'):
                skipped_real += 1
                continue
            records.append(normalize_tour_place(dict(item)))

        TourPlaceSyncService(StaticTourClient(records)).sync()
        for item in TOUR_PLACE_INFO_ITEMS:
            source = PlaceSource.objects.filter(
                source=ExternalSource.TOUR_API,
                external_id=item['external_id'],
                raw_data__dev_seed=True,
                place__isnull=False,
            ).select_related('place').first()
            if source is None:
                continue
            existing_info = PlaceInfo.objects.filter(place=source.place).first()
            if existing_info and not existing_info.raw_data.get('dev_seed'):
                continue
            PlaceInfo.objects.update_or_create(
                place=source.place,
                defaults={
                    'description': item['description'],
                    'opening_hours': item['opening_hours'],
                    'tags': item['tags'],
                    'merged_summary_source': ExternalSource.TOUR_API,
                    'raw_data': {'dev_seed': True},
                },
            )

        now = timezone.now()
        seeded_areas = []
        for item in CROWD_AREA_ITEMS:
            crowd_area, _ = CrowdArea.objects.get_or_create(
                source=ExternalSource.SEOUL_REALTIME,
                external_id=item['external_id'],
                defaults={
                    'name': item['name'],
                    'region_code': '11',
                    'raw_data': {'dev_seed': True},
                    'last_synced_at': now,
                },
            )
            seeded_areas.append(crowd_area)
            observation = CrowdData.objects.filter(
                crowd_area=crowd_area,
                raw_data__dev_seed=True,
            ).first()
            values = {
                'observed_at': now,
                'crowd_level': item['crowd_level'],
                'crowd_message': item['crowd_message'],
                'population_min': item['population_min'],
                'population_max': item['population_max'],
                'is_replaced': False,
                'raw_data': {'dev_seed': True},
            }
            if observation:
                for field, value in values.items():
                    setattr(observation, field, value)
                observation.save()
            else:
                CrowdData.objects.create(crowd_area=crowd_area, **values)

        for place_external_id, area_external_id in PLACE_CROWD_AREA_MAPPINGS:
            source = PlaceSource.objects.filter(
                source=ExternalSource.TOUR_API,
                external_id=place_external_id,
                raw_data__dev_seed=True,
                place__isnull=False,
            ).first()
            crowd_area = next(
                (
                    area
                    for area in seeded_areas
                    if area.external_id == area_external_id
                ),
                None,
            )
            if source and crowd_area:
                PlaceCrowdArea.objects.get_or_create(
                    place=source.place,
                    crowd_area=crowd_area,
                    defaults={
                        'match_method': PlaceCrowdArea.MatchMethod.SOURCE,
                    },
                )

        mappings = PlaceCrowdArea.objects.filter(
            place__sources__raw_data__dev_seed=True,
            crowd_area__in=seeded_areas,
        ).distinct().count()

        return {
            'places': Place.objects.filter(sources__raw_data__dev_seed=True)
            .distinct()
            .count(),
            'sources': PlaceSource.objects.filter(raw_data__dev_seed=True).count(),
            'infos': PlaceInfo.objects.filter(raw_data__dev_seed=True).count(),
            'areas': len(seeded_areas),
            'observations': CrowdData.objects.filter(
                raw_data__dev_seed=True
            ).count(),
            'mappings': mappings,
            'skipped_real': skipped_real,
        }

    @staticmethod
    @transaction.atomic
    def _clear():
        seed_sources = PlaceSource.objects.filter(raw_data__dev_seed=True)
        seed_areas = CrowdArea.objects.filter(raw_data__dev_seed=True)
        place_ids = list(seed_sources.values_list('place_id', flat=True))
        area_ids = list(seed_areas.values_list('id', flat=True))

        PlaceCrowdArea.objects.filter(
            Q(place_id__in=place_ids) | Q(crowd_area_id__in=area_ids)
        ).delete()
        infos_deleted, _ = PlaceInfo.objects.filter(
            raw_data__dev_seed=True,
            place_id__in=place_ids,
        ).delete()
        observations_deleted, _ = CrowdData.objects.filter(
            raw_data__dev_seed=True
        ).delete()
        sources_deleted, _ = seed_sources.delete()
        places_deleted, _ = Place.objects.filter(
            id__in=place_ids,
            sources__isnull=True,
        ).delete()
        areas_deleted, _ = seed_areas.filter(
            observations__isnull=True,
            place_mappings__isnull=True,
        ).delete()
        return {
            'places': places_deleted,
            'sources': sources_deleted,
            'infos': infos_deleted,
            'areas': areas_deleted,
            'observations': observations_deleted,
        }
