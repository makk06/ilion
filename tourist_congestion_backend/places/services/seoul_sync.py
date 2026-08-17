from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from places.models import CrowdArea, CrowdData, ExternalSource


@dataclass
class SeoulCrowdSyncResult:
    areas_processed: int = 0
    areas_created: int = 0
    observations_created: int = 0
    observations_updated: int = 0


class SeoulCrowdSyncService:
    def __init__(self, client):
        self.client = client

    def sync(self, areas, *, dry_run=False):
        if dry_run:
            with transaction.atomic():
                result = self._sync(areas)
                transaction.set_rollback(True)
                return result
        return self._sync(areas)

    def _sync(self, areas):
        result = SeoulCrowdSyncResult()
        for area_selector in areas:
            record = self.client.fetch_population(area_selector)
            outcome = self._sync_record(record)
            result.areas_processed += 1
            result.areas_created += outcome['area_created']
            result.observations_created += outcome['observation_created']
            result.observations_updated += not outcome['observation_created']
        return result

    @staticmethod
    @transaction.atomic
    def _sync_record(record):
        synced_at = timezone.now()
        crowd_area, area_created = CrowdArea.objects.update_or_create(
            source=ExternalSource.SEOUL_REALTIME,
            external_id=record.external_id,
            defaults={
                'name': record.name[:255],
                'region_code': '11',
                'raw_data': {
                    'AREA_CD': record.external_id,
                    'AREA_NM': record.name,
                },
                'last_synced_at': synced_at,
            },
        )
        _, observation_created = CrowdData.objects.update_or_create(
            crowd_area=crowd_area,
            observed_at=record.observed_at,
            defaults={
                'crowd_level': record.crowd_level,
                'crowd_message': record.crowd_message,
                'population_min': record.population_min,
                'population_max': record.population_max,
                'is_replaced': record.is_replaced,
                'raw_data': record.raw_data,
            },
        )
        return {
            'area_created': int(area_created),
            'observation_created': int(observation_created),
        }
