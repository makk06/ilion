import json
import re
from dataclasses import dataclass
from pathlib import Path

from places.models import ExternalSource


DATA_DIR = Path(__file__).resolve().parent / 'data'


@dataclass(frozen=True)
class SeoulCrowdAreaDefinition:
    external_id: str
    name: str
    category: str


@dataclass(frozen=True)
class SeoulPlaceMappingDefinition:
    place_source: str
    place_external_id: str
    crowd_area_external_id: str


@dataclass(frozen=True)
class SeoulCrowdCatalog:
    version: str
    source_url: str
    areas: tuple[SeoulCrowdAreaDefinition, ...]
    mappings: tuple[SeoulPlaceMappingDefinition, ...]


class CatalogConfigurationError(ValueError):
    pass


def _read_json(filename):
    with (DATA_DIR / filename).open(encoding='utf-8') as data_file:
        return json.load(data_file)


def load_seoul_crowd_catalog():
    area_payload = _read_json('seoul_crowd_areas.json')
    mapping_payload = _read_json('seoul_place_mappings.json')
    version = str(area_payload.get('catalog_version') or '').strip()
    if not version or version != str(mapping_payload.get('catalog_version') or ''):
        raise CatalogConfigurationError('Seoul catalog versions do not match')

    areas = tuple(
        SeoulCrowdAreaDefinition(
            external_id=str(item.get('external_id') or '').strip(),
            name=str(item.get('name') or '').strip(),
            category=str(item.get('category') or '').strip(),
        )
        for item in area_payload.get('areas', [])
    )
    mappings = tuple(
        SeoulPlaceMappingDefinition(
            place_source=str(item.get('place_source') or '').strip(),
            place_external_id=str(item.get('place_external_id') or '').strip(),
            crowd_area_external_id=str(
                item.get('crowd_area_external_id') or ''
            ).strip(),
        )
        for item in mapping_payload.get('mappings', [])
    )
    _validate_catalog(areas, mappings)
    return SeoulCrowdCatalog(
        version=version,
        source_url=str(area_payload.get('source_url') or '').strip(),
        areas=areas,
        mappings=mappings,
    )


def _validate_catalog(areas, mappings):
    if not areas:
        raise CatalogConfigurationError('Seoul crowd area catalog is empty')
    area_ids = [area.external_id for area in areas]
    if len(area_ids) != len(set(area_ids)):
        raise CatalogConfigurationError('Seoul crowd area IDs must be unique')
    for area in areas:
        if not re.fullmatch(r'POI\d{3}', area.external_id):
            raise CatalogConfigurationError(
                f'Invalid Seoul crowd area ID: {area.external_id}'
            )
        if not area.name or not area.category:
            raise CatalogConfigurationError(
                f'Seoul crowd area {area.external_id} is incomplete'
            )

    mapping_keys = [
        (
            mapping.place_source,
            mapping.place_external_id,
            mapping.crowd_area_external_id,
        )
        for mapping in mappings
    ]
    if len(mapping_keys) != len(set(mapping_keys)):
        raise CatalogConfigurationError('Seoul place mappings must be unique')
    known_area_ids = set(area_ids)
    for mapping in mappings:
        if mapping.place_source != ExternalSource.TOUR_API:
            raise CatalogConfigurationError(
                f'Unsupported place source: {mapping.place_source}'
            )
        if not mapping.place_external_id:
            raise CatalogConfigurationError('Place external ID is required')
        if mapping.crowd_area_external_id not in known_area_ids:
            raise CatalogConfigurationError(
                'Mapping references an area outside the selected Seoul catalog: '
                f'{mapping.crowd_area_external_id}'
            )
