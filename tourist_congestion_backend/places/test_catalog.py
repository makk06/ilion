from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from places.catalog import (
    SeoulPlaceMappingDefinition,
    load_seoul_crowd_catalog,
)
from places.integrations.exceptions import ExternalAPIError
from places.integrations.seoul_realtime import SeoulPopulationRecord
from places.models import (
    CrowdArea,
    ExternalSource,
    Place,
    PlaceCrowdArea,
    PlaceSource,
)
from places.services.seoul_mapping import SeoulPlaceMappingService
from places.services.seoul_sync import SeoulCrowdSyncService


def population_record(external_id):
    return SeoulPopulationRecord(
        external_id=external_id,
        name=external_id,
        observed_at=timezone.now(),
        crowd_level='normal',
        crowd_message='test',
        population_min=100,
        population_max=200,
        is_replaced=False,
        raw_data={'AREA_CD': external_id},
    )


class SeoulCrowdCatalogTests(TestCase):
    def test_catalog_has_versioned_unique_areas_and_valid_mappings(self):
        catalog = load_seoul_crowd_catalog()

        self.assertEqual(catalog.version, '2026-04-14')
        self.assertEqual(len(catalog.areas), 121)
        self.assertEqual(len(catalog.mappings), 13)
        area_ids = {area.external_id for area in catalog.areas}
        self.assertEqual(len(area_ids), 121)
        self.assertIn('POI008', area_ids)
        self.assertIn('POI060', area_ids)
        self.assertTrue(
            all(
                mapping.crowd_area_external_id in area_ids
                for mapping in catalog.mappings
            )
        )


class SeoulCrowdCatalogSyncTests(TestCase):
    def test_batch_sync_can_continue_after_one_area_failure(self):
        client = Mock()
        client.fetch_population.side_effect = [
            ExternalAPIError('temporary failure'),
            population_record('POI009'),
        ]

        result = SeoulCrowdSyncService(client).sync(
            ['POI008', 'POI009'],
            continue_on_error=True,
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.areas_processed, 1)
        self.assertTrue(
            CrowdArea.objects.filter(external_id='POI009').exists()
        )

    @patch(
        'places.management.commands.sync_seoul_crowd_catalog.SeoulRealtimeClient'
    )
    def test_catalog_command_limits_scope_and_rolls_back_dry_run(
        self,
        client_class,
    ):
        client_class.return_value.fetch_population.side_effect = population_record
        output = StringIO()

        call_command(
            'sync_seoul_crowd_catalog',
            '--limit',
            '2',
            '--dry-run',
            stdout=output,
        )

        calls = client_class.return_value.fetch_population.call_args_list
        self.assertEqual([call.args[0] for call in calls], ['POI001', 'POI002'])
        self.assertIn('catalog=2026-04-14', output.getvalue())
        self.assertIn('selected=2', output.getvalue())
        self.assertFalse(CrowdArea.objects.exists())


class SeoulPlaceMappingTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name='경복궁',
            category='관광지',
            region_code='11-110',
            address='서울특별시 종로구 사직로 161',
            latitude=Decimal('37.576031'),
            longitude=Decimal('126.976722'),
        )
        PlaceSource.objects.create(
            place=self.place,
            source=ExternalSource.TOUR_API,
            external_id='126508',
            match_status=PlaceSource.MatchStatus.MATCHED,
            last_synced_at=timezone.now(),
        )
        CrowdArea.objects.create(
            source=ExternalSource.SEOUL_REALTIME,
            external_id='POI008',
            name='경복궁',
            region_code='11',
            last_synced_at=timezone.now(),
        )
        self.definition = SeoulPlaceMappingDefinition(
            place_source=ExternalSource.TOUR_API,
            place_external_id='126508',
            crowd_area_external_id='POI008',
        )

    def test_mapping_apply_is_idempotent(self):
        service = SeoulPlaceMappingService()

        first = service.apply([self.definition])
        second = service.apply([self.definition])

        self.assertEqual(first.created, 1)
        self.assertEqual(second.updated, 1)
        self.assertEqual(PlaceCrowdArea.objects.count(), 1)
        self.assertEqual(
            PlaceCrowdArea.objects.get().match_method,
            PlaceCrowdArea.MatchMethod.SOURCE,
        )



class SeoulCatalogMappingCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_catalog_mapping_command_reports_development_coverage(self):
        call_command('seed_dev_data', stdout=StringIO())
        output = StringIO()

        call_command('apply_seoul_crowd_mappings', stdout=output)

        self.assertIn('attempted=13', output.getvalue())
        self.assertIn('updated=2', output.getvalue())
        self.assertIn('missing_places=11', output.getvalue())
        self.assertIn('missing_areas=9', output.getvalue())
