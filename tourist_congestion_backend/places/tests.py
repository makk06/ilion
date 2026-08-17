import json
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from places.integrations.exceptions import ExternalAPIError
from places.integrations.seoul_realtime import (
    SeoulRealtimeClient,
    normalize_seoul_population,
)
from places.integrations.tour_api import (
    TourAPIClient,
    TourAPIPage,
    normalize_tour_place,
    normalize_tour_place_detail,
)
from places.models import (
    CrowdArea,
    CrowdData,
    ExternalSource,
    Place,
    PlaceCrowdArea,
    PlaceInfo,
    PlaceSource,
)
from places.services.seoul_sync import SeoulCrowdSyncService
from places.services.tour_detail_sync import TourPlaceDetailSyncService
from places.services.tour_sync import TourPlaceSyncService


FIXTURE_DIR = Path(__file__).resolve().parent / 'test_fixtures'


def load_fixture(name):
    with (FIXTURE_DIR / name).open(encoding='utf-8') as fixture_file:
        return json.load(fixture_file)


class PlaceModelTests(TestCase):
    def setUp(self):
        self.place_data = {
            'name': '서울숲',
            'category': '자연',
            'region_code': '11200',
            'address': '서울특별시 성동구 뚝섬로 273',
            'latitude': Decimal('37.544387'),
            'longitude': Decimal('127.037442'),
            'indoor_outdoor': Place.IndoorOutdoor.OUTDOOR,
        }

    def test_create_place_with_required_fields(self):
        place = Place.objects.create(**self.place_data)

        self.assertIsNotNone(place.id)
        self.assertEqual(str(place), '서울숲')
        self.assertIsNone(place.subcategory)
        self.assertIsNone(place.open_status)
        self.assertIsNone(place.avg_rating)
        self.assertIsNotNone(place.created_at)
        self.assertIsNotNone(place.updated_at)

    def test_indoor_outdoor_defaults_to_unknown(self):
        data = {**self.place_data}
        data.pop('indoor_outdoor')

        place = Place.objects.create(**data)

        self.assertEqual(place.indoor_outdoor, Place.IndoorOutdoor.UNKNOWN)

    def test_reject_invalid_choice_and_numeric_ranges(self):
        place = Place(
            **{
                **self.place_data,
                'indoor_outdoor': 'both',
                'latitude': Decimal('91'),
                'longitude': Decimal('181'),
                'avg_rating': Decimal('5.01'),
            }
        )

        with self.assertRaises(ValidationError) as context:
            place.full_clean()

        self.assertEqual(
            set(context.exception.message_dict),
            {'indoor_outdoor', 'latitude', 'longitude', 'avg_rating'},
        )


class TourAPIClientTests(TestCase):
    def test_parse_page_and_normalize_current_classification_fields(self):
        page = TourAPIClient._parse_page(load_fixture('tourapi_places.json'))

        self.assertEqual(page.total_count, 1)
        self.assertFalse(page.has_next)
        record = page.records[0]
        self.assertEqual(record.external_id, '126508')
        self.assertEqual(record.category, '관광지')
        self.assertEqual(record.subcategory, 'VE010100')
        self.assertEqual(record.region_code, '11-110')
        self.assertTrue(record.can_create_place)

    def test_client_sends_required_parameters(self):
        response = Mock()
        response.json.return_value = load_fixture('tourapi_places.json')
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        client = TourAPIClient(service_key='test-key', session=session)

        client.fetch_places_page(
            page_number=2,
            page_size=50,
            modified_since='20260801',
            region_code='11',
        )

        _, kwargs = session.get.call_args
        self.assertEqual(kwargs['params']['serviceKey'], 'test-key')
        self.assertEqual(kwargs['params']['pageNo'], 2)
        self.assertEqual(kwargs['params']['modifiedtime'], '20260801')
        self.assertEqual(kwargs['params']['lDongRegnCd'], '11')

    def test_missing_required_place_fields_are_not_creatable(self):
        record = normalize_tour_place(
            {'contentid': '1', 'contenttypeid': '12', 'title': '좌표 없는 장소'}
        )

        self.assertFalse(record.can_create_place)

    def test_normalizes_common_and_type_specific_detail_fields(self):
        common = load_fixture('tourapi_place_common.json')['response']['body'][
            'items'
        ]['item']
        intro = load_fixture('tourapi_place_intro.json')['response']['body'][
            'items'
        ]['item']

        record = normalize_tour_place_detail(common, intro)

        self.assertEqual(record.external_id, '126508')
        self.assertEqual(
            record.description,
            '조선 왕조의 법궁입니다.\n역사 문화 공간입니다.',
        )
        self.assertEqual(record.homepage_url, 'https://royal.khs.go.kr/')
        self.assertEqual(
            record.first_image_url,
            'https://example.com/gyeongbokgung.jpg',
        )
        self.assertEqual(record.opening_hours, '09:00~18:00\n입장 마감 17:00')
        self.assertEqual(record.holiday_info, '매주 화요일')

    def test_client_fetches_common_and_intro_details(self):
        common_response = Mock()
        common_response.json.return_value = load_fixture(
            'tourapi_place_common.json'
        )
        common_response.raise_for_status.return_value = None
        intro_response = Mock()
        intro_response.json.return_value = load_fixture(
            'tourapi_place_intro.json'
        )
        intro_response.raise_for_status.return_value = None
        session = Mock()
        session.get.side_effect = [common_response, intro_response]
        client = TourAPIClient(service_key='test-key', session=session)

        record = client.fetch_place_detail('126508', '12')

        self.assertEqual(record.external_id, '126508')
        self.assertEqual(session.get.call_count, 2)
        common_call, intro_call = session.get.call_args_list
        self.assertTrue(common_call.args[0].endswith('/detailCommon2'))
        self.assertTrue(intro_call.args[0].endswith('/detailIntro2'))
        self.assertEqual(common_call.kwargs['params']['contentId'], '126508')
        self.assertNotIn('contentTypeId', common_call.kwargs['params'])
        self.assertNotIn('defaultYN', common_call.kwargs['params'])
        self.assertEqual(intro_call.kwargs['params']['contentTypeId'], '12')

    def test_provider_error_does_not_include_service_key(self):
        response = Mock()
        response.raise_for_status.side_effect = __import__('requests').HTTPError(
            'failed https://example.test?serviceKey=secret-key'
        )
        response.status_code = 403
        response.json.return_value = {
            'OpenAPI_ServiceResponse': {
                'cmmMsgHeader': {
                    'returnReasonCode': '30',
                    'returnAuthMsg': '등록되지 않은 서비스키',
                }
            }
        }
        session = Mock()
        session.get.return_value = response
        client = TourAPIClient(service_key='secret-key', session=session)

        with self.assertRaises(ExternalAPIError) as context:
            client.fetch_places_page()

        self.assertNotIn('secret-key', str(context.exception))
        self.assertIn('code 30', str(context.exception))

    def test_top_level_parameter_error_is_reported_without_payload_dump(self):
        with self.assertRaises(ExternalAPIError) as context:
            TourAPIClient._parse_page(
                {
                    'resultCode': '10',
                    'resultMsg': 'INVALID_REQUEST_PARAMETER_ERROR(defaultYN)',
                }
            )

        self.assertIn('code 10', str(context.exception))
        self.assertIn('defaultYN', str(context.exception))


class TourPlaceSyncServiceTests(TestCase):
    def setUp(self):
        self.record = TourAPIClient._parse_page(
            load_fixture('tourapi_places.json')
        ).records[0]

    def make_client(self):
        client = Mock()
        client.fetch_places_page.return_value = TourAPIPage(
            records=[self.record],
            page_number=1,
            page_size=1,
            total_count=1,
        )
        return client

    def test_sync_is_idempotent_and_updates_existing_place(self):
        service = TourPlaceSyncService(self.make_client())

        first = service.sync()
        second = service.sync()

        self.assertEqual(first.sources_created, 1)
        self.assertEqual(first.places_created, 1)
        self.assertEqual(second.sources_updated, 1)
        self.assertEqual(Place.objects.count(), 1)
        self.assertEqual(PlaceSource.objects.count(), 1)
        source = PlaceSource.objects.get()
        self.assertEqual(source.match_status, PlaceSource.MatchStatus.MATCHED)
        self.assertEqual(source.place.name, '경복궁')
        self.assertEqual(source.place.indoor_outdoor, Place.IndoorOutdoor.UNKNOWN)

    def test_incomplete_record_is_preserved_for_manual_review(self):
        incomplete = normalize_tour_place(
            {'contentid': 'missing-location', 'contenttypeid': '12', 'title': '미완성'}
        )
        client = Mock()
        client.fetch_places_page.return_value = TourAPIPage(
            records=[incomplete], page_number=1, page_size=1, total_count=1
        )

        result = TourPlaceSyncService(client).sync()

        self.assertEqual(result.unmatched, 1)
        source = PlaceSource.objects.get(external_id='missing-location')
        self.assertIsNone(source.place)
        self.assertEqual(source.match_status, PlaceSource.MatchStatus.MANUAL_REVIEW)

    def test_dry_run_rolls_back_database_changes(self):
        result = TourPlaceSyncService(self.make_client()).sync(dry_run=True)

        self.assertEqual(result.processed, 1)
        self.assertFalse(Place.objects.exists())
        self.assertFalse(PlaceSource.objects.exists())


class TourPlaceDetailSyncServiceTests(TestCase):
    def setUp(self):
        self.source = self._create_source()
        common = load_fixture('tourapi_place_common.json')['response']['body'][
            'items'
        ]['item']
        intro = load_fixture('tourapi_place_intro.json')['response']['body'][
            'items'
        ]['item']
        self.detail = normalize_tour_place_detail(common, intro)

    @staticmethod
    def _create_source():
        record = TourAPIClient._parse_page(
            load_fixture('tourapi_places.json')
        ).records[0]
        TourPlaceSyncService(
            Mock(fetch_places_page=Mock(return_value=TourAPIPage(
                records=[record],
                page_number=1,
                page_size=1,
                total_count=1,
            )))
        ).sync()
        return PlaceSource.objects.select_related('place').get()

    def test_sync_is_idempotent_and_preserves_structured_detail(self):
        client = Mock()
        client.fetch_place_detail.return_value = self.detail
        service = TourPlaceDetailSyncService(client)

        first = service.sync([self.source])
        second = service.sync([self.source])

        self.assertEqual(first.infos_created, 1)
        self.assertEqual(second.infos_updated, 1)
        self.assertEqual(PlaceInfo.objects.count(), 1)
        info = PlaceInfo.objects.get()
        self.assertEqual(info.description, self.detail.description)
        self.assertEqual(info.opening_hours, self.detail.opening_hours)
        self.assertEqual(info.merged_summary_source, ExternalSource.TOUR_API)
        self.assertIn('common', info.raw_data)

    def test_dry_run_rolls_back_detail_changes(self):
        client = Mock()
        client.fetch_place_detail.return_value = self.detail

        result = TourPlaceDetailSyncService(client).sync(
            [self.source],
            dry_run=True,
        )

        self.assertEqual(result.processed, 1)
        self.assertFalse(PlaceInfo.objects.exists())

    def test_source_without_content_type_is_skipped(self):
        self.source.raw_data = {}
        self.source.save(update_fields=['raw_data'])
        client = Mock()

        result = TourPlaceDetailSyncService(client).sync([self.source])

        self.assertEqual(result.skipped, 1)
        client.fetch_place_detail.assert_not_called()


class SeoulRealtimeTests(TestCase):
    def setUp(self):
        self.payload = load_fixture('seoul_population.json')

    def test_normalizes_population_record(self):
        record = normalize_seoul_population(
            self.payload,
            fallback_area='광화문·덕수궁',
        )

        self.assertEqual(record.external_id, 'POI009')
        self.assertEqual(record.crowd_level, CrowdData.CrowdLevel.NORMAL)
        self.assertEqual(record.population_min, 18000)
        self.assertEqual(record.population_max, 20000)
        self.assertTrue(timezone.is_aware(record.observed_at))

    def test_client_encodes_area_name_in_path(self):
        response = Mock()
        response.json.return_value = self.payload
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response

        record = SeoulRealtimeClient(
            api_key='test-key', session=session
        ).fetch_population('광화문·덕수궁')

        called_url = session.get.call_args.args[0]
        self.assertIn('%EA%B4%91%ED%99%94%EB%AC%B8', called_url)
        self.assertEqual(record.external_id, 'POI009')

    def test_sync_is_idempotent_and_dry_run_rolls_back(self):
        record = normalize_seoul_population(self.payload, fallback_area='POI009')
        client = Mock()
        client.fetch_population.return_value = record
        service = SeoulCrowdSyncService(client)

        first = service.sync(['POI009'])
        second = service.sync(['POI009'])

        self.assertEqual(first.areas_created, 1)
        self.assertEqual(first.observations_created, 1)
        self.assertEqual(second.observations_updated, 1)
        self.assertEqual(CrowdArea.objects.count(), 1)
        self.assertEqual(CrowdData.objects.count(), 1)

        CrowdData.objects.all().delete()
        CrowdArea.objects.all().delete()
        dry_run = service.sync(['POI009'], dry_run=True)
        self.assertEqual(dry_run.areas_processed, 1)
        self.assertFalse(CrowdArea.objects.exists())


class SyncCommandTests(TestCase):
    @patch('places.management.commands.sync_tour_places.TourAPIClient')
    def test_tour_command_reports_dry_run(self, client_class):
        record = TourAPIClient._parse_page(
            load_fixture('tourapi_places.json')
        ).records[0]
        client_class.return_value.fetch_places_page.return_value = TourAPIPage(
            records=[record], page_number=1, page_size=1, total_count=1
        )
        output = StringIO()

        call_command('sync_tour_places', '--dry-run', stdout=output)

        self.assertIn('[dry-run]', output.getvalue())
        self.assertFalse(PlaceSource.objects.exists())

    def test_map_place_crowd_area_command_creates_mapping(self):
        place = Place.objects.create(
            name='경복궁',
            category='관광지',
            region_code='11-110',
            address='서울특별시 종로구 사직로 161',
            latitude=Decimal('37.578840'),
            longitude=Decimal('126.977016'),
        )
        crowd_area = CrowdArea.objects.create(
            source=ExternalSource.SEOUL_REALTIME,
            external_id='POI009',
            name='광화문·덕수궁',
            region_code='11',
            last_synced_at=timezone.now(),
        )
        output = StringIO()

        call_command(
            'map_place_crowd_area',
            str(place.id),
            crowd_area.external_id,
            stdout=output,
        )

        mapping = PlaceCrowdArea.objects.get()
        self.assertEqual(mapping.place, place)
        self.assertEqual(mapping.crowd_area, crowd_area)
        self.assertIn('created mapping', output.getvalue())

    @patch('places.management.commands.sync_tour_place_details.TourAPIClient')
    def test_tour_detail_command_reports_dry_run(self, client_class):
        record = TourAPIClient._parse_page(
            load_fixture('tourapi_places.json')
        ).records[0]
        TourPlaceSyncService(
            Mock(
                fetch_places_page=Mock(
                    return_value=TourAPIPage(
                        records=[record],
                        page_number=1,
                        page_size=1,
                        total_count=1,
                    )
                )
            )
        ).sync()
        common = load_fixture('tourapi_place_common.json')['response']['body'][
            'items'
        ]['item']
        intro = load_fixture('tourapi_place_intro.json')['response']['body'][
            'items'
        ]['item']
        client_class.return_value.fetch_place_detail.return_value = (
            normalize_tour_place_detail(common, intro)
        )
        output = StringIO()

        call_command(
            'sync_tour_place_details',
            '126508',
            '--dry-run',
            stdout=output,
        )

        self.assertIn('[dry-run]', output.getvalue())
        self.assertIn('external_requests=2', output.getvalue())
        self.assertFalse(PlaceInfo.objects.exists())


class SeedDevDataCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_seed_is_idempotent_and_clear_removes_only_seed_data(self):
        first_output = StringIO()
        second_output = StringIO()

        call_command('seed_dev_data', stdout=first_output)
        call_command('seed_dev_data', stdout=second_output)

        self.assertEqual(Place.objects.count(), 10)
        self.assertEqual(PlaceSource.objects.count(), 10)
        self.assertEqual(PlaceInfo.objects.count(), 10)
        self.assertEqual(CrowdArea.objects.count(), 2)
        self.assertEqual(CrowdData.objects.count(), 2)
        self.assertEqual(PlaceCrowdArea.objects.count(), 1)
        self.assertIn('places=10', first_output.getvalue())
        self.assertIn('places=10', second_output.getvalue())

        call_command('seed_dev_data', '--clear', stdout=StringIO())

        self.assertFalse(Place.objects.exists())
        self.assertFalse(PlaceSource.objects.exists())
        self.assertFalse(PlaceInfo.objects.exists())
        self.assertFalse(CrowdArea.objects.exists())
        self.assertFalse(CrowdData.objects.exists())

    @override_settings(DEBUG=False)
    def test_seed_is_rejected_outside_debug(self):
        with self.assertRaisesMessage(
            CommandError,
            'seed_dev_data is only available when DEBUG=true',
        ):
            call_command('seed_dev_data')
