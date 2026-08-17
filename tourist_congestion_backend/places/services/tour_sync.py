from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from places.models import ExternalSource, Place, PlaceSource


@dataclass
class TourPlaceSyncResult:
    processed: int = 0
    sources_created: int = 0
    sources_updated: int = 0
    places_created: int = 0
    unmatched: int = 0
    inactive: int = 0
    pages: int = 0


class TourPlaceSyncService:
    def __init__(self, client):
        self.client = client

    def sync(
        self,
        *,
        page_size=100,
        max_pages=None,
        modified_since=None,
        region_code=None,
        dry_run=False,
    ):
        if dry_run:
            with transaction.atomic():
                result = self._sync(
                    page_size=page_size,
                    max_pages=max_pages,
                    modified_since=modified_since,
                    region_code=region_code,
                )
                transaction.set_rollback(True)
                return result
        return self._sync(
            page_size=page_size,
            max_pages=max_pages,
            modified_since=modified_since,
            region_code=region_code,
        )

    def _sync(self, *, page_size, max_pages, modified_since, region_code):
        result = TourPlaceSyncResult()
        page_number = 1

        while True:
            page = self.client.fetch_places_page(
                page_number=page_number,
                page_size=page_size,
                modified_since=modified_since,
                region_code=region_code,
            )
            result.pages += 1
            for record in page.records:
                outcome = self._sync_record(record)
                result.processed += 1
                result.sources_created += outcome['source_created']
                result.sources_updated += not outcome['source_created']
                result.places_created += outcome['place_created']
                result.unmatched += outcome['unmatched']
                result.inactive += outcome['inactive']

            if not page.has_next or not page.records:
                break
            if max_pages is not None and result.pages >= max_pages:
                break
            page_number += 1

        return result

    @transaction.atomic
    def _sync_record(self, record):
        synced_at = timezone.now()
        existing = PlaceSource.objects.select_related('place').filter(
            source=ExternalSource.TOUR_API,
            external_id=record.external_id,
        ).first()
        place = existing.place if existing else None
        place_created = False

        if record.is_active:
            if place is None and record.can_create_place:
                place = Place.objects.create(
                    name=record.name[:255],
                    category=record.category[:100],
                    subcategory=record.subcategory[:100] or None,
                    region_code=record.region_code[:20],
                    address=record.address[:255],
                    latitude=record.latitude,
                    longitude=record.longitude,
                    indoor_outdoor=Place.IndoorOutdoor.UNKNOWN,
                )
                place_created = True
            elif place is not None:
                self._update_place(place, record)

            status = (
                PlaceSource.MatchStatus.MATCHED
                if place is not None
                else PlaceSource.MatchStatus.MANUAL_REVIEW
            )
        else:
            status = PlaceSource.MatchStatus.INACTIVE

        _, source_created = PlaceSource.objects.update_or_create(
            source=ExternalSource.TOUR_API,
            external_id=record.external_id,
            defaults={
                'place': place,
                'source_name': record.name[:255],
                'source_category': record.source_category[:100],
                'source_address': record.address[:500],
                'source_latitude': record.latitude,
                'source_longitude': record.longitude,
                'match_status': status,
                'raw_data': record.raw_data,
                'last_synced_at': synced_at,
            },
        )
        return {
            'source_created': int(source_created),
            'place_created': int(place_created),
            'unmatched': int(status == PlaceSource.MatchStatus.MANUAL_REVIEW),
            'inactive': int(status == PlaceSource.MatchStatus.INACTIVE),
        }

    @staticmethod
    def _update_place(place, record):
        changed_fields = []
        values = {
            'name': record.name[:255],
            'category': record.category[:100],
            'subcategory': record.subcategory[:100] or None,
            'region_code': record.region_code[:20],
            'address': record.address[:255],
            'latitude': record.latitude,
            'longitude': record.longitude,
        }
        for field, value in values.items():
            if value not in ('', None) and getattr(place, field) != value:
                setattr(place, field, value)
                changed_fields.append(field)
        if changed_fields:
            place.save(update_fields=changed_fields + ['updated_at'])
