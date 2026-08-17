from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from places.models import (
    CrowdArea,
    CrowdData,
    ExternalSource,
    Place,
    PlaceCrowdArea,
    PlaceSource,
)


class PlaceAPITests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.gyeongbokgung = self._create_place(
            name='경복궁',
            category='관광지',
            region_code='11-110',
            address='서울특별시 종로구 사직로 161',
            latitude='37.576031',
            longitude='126.976722',
        )
        self.haeundae = self._create_place(
            name='해운대해수욕장',
            category='관광지',
            region_code='26-350',
            address='부산광역시 해운대구 해운대해변로 264',
            latitude='35.159084',
            longitude='129.160279',
        )
        self.local_place = self._create_place(
            name='팀 추천 장소',
            category='기타',
            region_code='41-000',
            address='경기도 수원시',
            latitude='37.263573',
            longitude='127.028601',
        )
        self.inactive_place = self._create_place(
            name='폐쇄된 관광지',
            category='관광지',
            region_code='11-000',
            address='서울특별시',
            latitude='37.500000',
            longitude='127.000000',
        )

        self._create_source(self.gyeongbokgung, '126508')
        self._create_source(self.haeundae, '126081')
        self._create_source(
            self.inactive_place,
            'inactive-1',
            status=PlaceSource.MatchStatus.INACTIVE,
        )

        area = CrowdArea.objects.create(
            source=ExternalSource.SEOUL_REALTIME,
            external_id='POI008',
            name='경복궁',
            region_code='11',
            last_synced_at=now,
        )
        PlaceCrowdArea.objects.create(
            place=self.gyeongbokgung,
            crowd_area=area,
            match_method=PlaceCrowdArea.MatchMethod.SOURCE,
        )
        CrowdData.objects.create(
            crowd_area=area,
            observed_at=now - timedelta(minutes=30),
            crowd_level=CrowdData.CrowdLevel.NORMAL,
            population_min=8000,
            population_max=10000,
        )
        self.latest_observation = CrowdData.objects.create(
            crowd_area=area,
            observed_at=now,
            crowd_level=CrowdData.CrowdLevel.BUSY,
            crowd_message='사람이 붐비고 있습니다.',
            crowd_score=75,
            population_min=12000,
            population_max=14000,
        )

    @staticmethod
    def _create_place(**values):
        return Place.objects.create(
            indoor_outdoor=Place.IndoorOutdoor.UNKNOWN,
            **values,
        )

    @staticmethod
    def _create_source(place, external_id, *, status=PlaceSource.MatchStatus.MATCHED):
        return PlaceSource.objects.create(
            place=place,
            source=ExternalSource.TOUR_API,
            external_id=external_id,
            match_status=status,
            last_synced_at=timezone.now(),
        )

    def test_list_returns_visible_places_with_latest_crowd_without_n_plus_one(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse('place-list'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['message'], '')
        self.assertEqual(payload['data']['pagination']['total'], 3)
        items_by_name = {
            item['name']: item for item in payload['data']['items']
        }
        self.assertNotIn(self.inactive_place.name, items_by_name)
        crowd = items_by_name['경복궁']['latest_crowd']
        self.assertEqual(crowd['level'], CrowdData.CrowdLevel.BUSY)
        self.assertEqual(crowd['score'], 75)
        self.assertEqual(crowd['population_min'], 12000)
        self.assertEqual(crowd['area_external_id'], 'POI008')
        self.assertIsNone(items_by_name['해운대해수욕장']['latest_crowd'])

    def test_list_filters_by_keyword_region_category_and_latest_crowd(self):
        response = self.client.get(
            reverse('place-list'),
            {
                'keyword': '경복',
                'region_code': '11',
                'category': '관광',
                'crowd_level': 'busy',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['pagination']['total'], 1)
        self.assertEqual(data['items'][0]['id'], self.gyeongbokgung.id)
        self.assertEqual(data['filters']['keyword'], '경복')

        old_level_response = self.client.get(
            reverse('place-list'), {'crowd_level': 'normal'}
        )
        self.assertEqual(
            old_level_response.json()['data']['pagination']['total'],
            0,
        )

    def test_list_paginates_results(self):
        response = self.client.get(
            reverse('place-list'), {'page': 2, 'page_size': 2}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(
            data['pagination'],
            {'page': 2, 'page_size': 2, 'total': 3, 'total_pages': 2},
        )

    def test_list_rejects_invalid_pagination_and_crowd_level(self):
        cases = (
            ({'page': 'zero'}, 'page must be a positive integer.'),
            ({'page_size': '0'}, 'page_size must be a positive integer.'),
            ({'page_size': '101'}, 'page_size must be at most 100.'),
        )
        for params, expected_message in cases:
            with self.subTest(params=params):
                response = self.client.get(reverse('place-list'), params)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['success'])
                self.assertEqual(response.json()['message'], expected_message)

        response = self.client.get(
            reverse('place-list'), {'crowd_level': 'very_busy'}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('relaxed, normal, busy, crowded, unknown', response.json()['message'])

    def test_detail_returns_place_and_latest_crowd(self):
        with self.assertNumQueries(1):
            response = self.client.get(
                reverse('place-detail', args=[self.gyeongbokgung.id])
            )

        self.assertEqual(response.status_code, 200)
        place = response.json()['data']
        self.assertEqual(place['name'], '경복궁')
        self.assertEqual(place['latitude'], 37.576031)
        self.assertEqual(place['latest_crowd']['level'], 'busy')
        self.assertIn('created_at', place)
        self.assertIn('updated_at', place)

    def test_detail_returns_json_404_for_missing_or_inactive_place(self):
        for place_id in (999999, self.inactive_place.id):
            with self.subTest(place_id=place_id):
                response = self.client.get(
                    reverse('place-detail', args=[place_id])
                )
                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response.json(),
                    {
                        'success': False,
                        'data': None,
                        'message': 'Place not found.',
                    },
                )

    def test_endpoints_reject_post_requests(self):
        self.assertEqual(self.client.post(reverse('place-list')).status_code, 405)
        self.assertEqual(
            self.client.post(
                reverse('place-detail', args=[self.gyeongbokgung.id])
            ).status_code,
            405,
        )


class SeededPlaceAPITests(TestCase):
    @override_settings(DEBUG=True)
    def test_seed_data_is_immediately_available_through_api(self):
        call_command('seed_dev_data', verbosity=0)

        response = self.client.get(
            reverse('place-list'), {'keyword': '경복궁'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['pagination']['total'], 1)
        self.assertEqual(data['items'][0]['latest_crowd']['level'], 'normal')
