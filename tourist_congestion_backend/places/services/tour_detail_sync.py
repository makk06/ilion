from dataclasses import dataclass

from django.db import transaction

from places.integrations.exceptions import ExternalAPIError
from places.models import ExternalSource, PlaceInfo


@dataclass
class TourPlaceDetailSyncResult:
    processed: int = 0
    infos_created: int = 0
    infos_updated: int = 0
    skipped: int = 0


class TourPlaceDetailSyncService:
    def __init__(self, client):
        self.client = client

    def sync(self, sources, *, include_intro=True, dry_run=False):
        if dry_run:
            with transaction.atomic():
                result = self._sync(sources, include_intro=include_intro)
                transaction.set_rollback(True)
                return result
        return self._sync(sources, include_intro=include_intro)

    def _sync(self, sources, *, include_intro):
        result = TourPlaceDetailSyncResult()
        for source in sources:
            content_type_id = str(
                source.raw_data.get('contenttypeid')
                or source.raw_data.get('contentTypeId')
                or ''
            ).strip()
            if source.place_id is None or not content_type_id:
                result.skipped += 1
                continue

            record = self.client.fetch_place_detail(
                source.external_id,
                content_type_id,
                include_intro=include_intro,
            )
            if record.external_id and record.external_id != source.external_id:
                raise ExternalAPIError(
                    'TourAPI detail content ID does not match the requested place'
                )
            created = self._upsert_info(source.place, record)
            result.processed += 1
            result.infos_created += int(created)
            result.infos_updated += int(not created)
        return result

    @staticmethod
    @transaction.atomic
    def _upsert_info(place, record):
        _, created = PlaceInfo.objects.update_or_create(
            place=place,
            defaults={
                'description': record.description,
                'phone': record.phone[:255],
                'homepage_url': record.homepage_url[:1000],
                'first_image_url': record.first_image_url[:1000],
                'opening_hours': record.opening_hours,
                'holiday_info': record.holiday_info,
                'merged_summary_source': ExternalSource.TOUR_API,
                'raw_data': record.raw_data,
            },
        )
        return created
