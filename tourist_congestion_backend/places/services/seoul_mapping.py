from dataclasses import dataclass, field

from django.db import transaction

from places.models import CrowdArea, ExternalSource, PlaceCrowdArea, PlaceSource


@dataclass
class SeoulPlaceMappingResult:
    attempted: int = 0
    created: int = 0
    updated: int = 0
    missing_places: list[str] = field(default_factory=list)
    missing_areas: list[str] = field(default_factory=list)


class SeoulPlaceMappingService:
    def apply(self, definitions, *, dry_run=False):
        if dry_run:
            with transaction.atomic():
                result = self._apply(definitions)
                transaction.set_rollback(True)
                return result
        return self._apply(definitions)

    @staticmethod
    def _apply(definitions):
        result = SeoulPlaceMappingResult()
        for definition in definitions:
            result.attempted += 1
            source = PlaceSource.objects.filter(
                source=definition.place_source,
                external_id=definition.place_external_id,
                match_status=PlaceSource.MatchStatus.MATCHED,
                place__isnull=False,
            ).select_related('place').first()
            if source is None:
                if definition.place_external_id not in result.missing_places:
                    result.missing_places.append(definition.place_external_id)

            crowd_area = CrowdArea.objects.filter(
                source=ExternalSource.SEOUL_REALTIME,
                external_id=definition.crowd_area_external_id,
            ).first()
            if crowd_area is None:
                if definition.crowd_area_external_id not in result.missing_areas:
                    result.missing_areas.append(definition.crowd_area_external_id)
            if source is None or crowd_area is None:
                continue

            _, created = PlaceCrowdArea.objects.update_or_create(
                place=source.place,
                crowd_area=crowd_area,
                defaults={
                    'match_method': PlaceCrowdArea.MatchMethod.SOURCE,
                },
            )
            result.created += int(created)
            result.updated += int(not created)
        return result
