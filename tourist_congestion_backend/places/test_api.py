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
    PlaceInfo,
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
        PlaceInfo.objects.create(
            place=self.gyeongbokgung,
            description='조선 왕조의 법궁입니다.',
            phone='02-3700-3900',
            homepage_url='https://royal.khs.go.kr/',
            first_image_url='https://example.com/gyeongbokgung.jpg',
            opening_hours='09:00~18:00',
            holiday_info='화요일',
            tags=['역사', '궁궐'],
            merged_summary_source=ExternalSource.TOUR_API,
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
        self.assertEqual(
            items_by_name['경복궁']['image_url'],
            'https://example.com/gyeongbokgung.jpg',
        )
        self.assertIsNone(items_by_name['해운대해수욕장']['latest_crowd'])
        self.assertIsNone(items_by_name['해운대해수욕장']['image_url'])

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

    def test_nearby_returns_places_sorted_by_distance_with_latest_crowd(self):
        gwanghwamun = self._create_place(
            name='광화문광장',
            category='문화시설',
            region_code='11-110',
            address='서울특별시 종로구 세종대로 175',
            latitude='37.572389',
            longitude='126.976911',
        )
        self._create_source(gwanghwamun, 'gwanghwamun-1')

        with self.assertNumQueries(1):
            response = self.client.get(
                reverse('place-nearby'),
                {
                    'latitude': '37.576031',
                    'longitude': '126.976722',
                    'radius_km': '2',
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['pagination']['total'], 2)
        self.assertEqual(
            [item['name'] for item in data['items']],
            ['경복궁', '광화문광장'],
        )
        self.assertEqual(data['items'][0]['distance_km'], 0.0)
        self.assertGreater(data['items'][1]['distance_km'], 0)
        self.assertEqual(data['items'][0]['latest_crowd']['level'], 'busy')
        self.assertEqual(
            data['search_center'],
            {
                'latitude': 37.576031,
                'longitude': 126.976722,
                'radius_km': 2.0,
            },
        )

    def test_nearby_supports_category_crowd_and_pagination_filters(self):
        nearby_culture = self._create_place(
            name='국립고궁박물관',
            category='문화시설',
            region_code='11-110',
            address='서울특별시 종로구 효자로 12',
            latitude='37.576548',
            longitude='126.974973',
        )
        self._create_source(nearby_culture, 'museum-1')
        center = {
            'latitude': '37.576031',
            'longitude': '126.976722',
            'radius_km': '2',
        }

        category_response = self.client.get(
            reverse('place-nearby'),
            {**center, 'category': '문화'},
        )
        self.assertEqual(category_response.status_code, 200)
        self.assertEqual(
            [
                item['name']
                for item in category_response.json()['data']['items']
            ],
            ['국립고궁박물관'],
        )

        crowd_response = self.client.get(
            reverse('place-nearby'),
            {**center, 'crowd_level': 'busy'},
        )
        self.assertEqual(crowd_response.status_code, 200)
        self.assertEqual(
            [item['name'] for item in crowd_response.json()['data']['items']],
            ['경복궁'],
        )

        page_response = self.client.get(
            reverse('place-nearby'),
            {**center, 'page': '2', 'page_size': '1'},
        )
        self.assertEqual(page_response.status_code, 200)
        pagination = page_response.json()['data']['pagination']
        self.assertEqual(
            pagination,
            {'page': 2, 'page_size': 1, 'total': 2, 'total_pages': 2},
        )

    def test_nearby_rejects_invalid_coordinates_and_radius(self):
        cases = (
            ({'longitude': '127'}, 'latitude is required.'),
            ({'latitude': '37'}, 'longitude is required.'),
            (
                {'latitude': 'north', 'longitude': '127'},
                'latitude must be a number.',
            ),
            (
                {'latitude': 'nan', 'longitude': '127'},
                'latitude must be a finite number.',
            ),
            (
                {'latitude': '91', 'longitude': '127'},
                'latitude must be between -90 and 90.',
            ),
            (
                {'latitude': '37', 'longitude': '181'},
                'longitude must be between -180 and 180.',
            ),
            (
                {'latitude': '37', 'longitude': '127', 'radius_km': '0'},
                'radius_km must be greater than 0.',
            ),
            (
                {'latitude': '37', 'longitude': '127', 'radius_km': '101'},
                'radius_km must be at most 100.',
            ),
        )
        for params, expected_message in cases:
            with self.subTest(params=params):
                response = self.client.get(reverse('place-nearby'), params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['message'], expected_message)

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
        self.assertEqual(place['info']['description'], '조선 왕조의 법궁입니다.')
        self.assertEqual(place['info']['tags'], ['역사', '궁궐'])
        self.assertEqual(place['info']['source'], 'tour_api')
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
            self.client.post(reverse('place-nearby')).status_code,
            405,
        )
        self.assertEqual(
            self.client.post(
                reverse('place-detail', args=[self.gyeongbokgung.id])
            ).status_code,
            405,
        )


    def test_detail_exposes_normalized_fee_parking_and_missing_values(self):
        info = PlaceInfo.objects.get(place=self.gyeongbokgung)
        info.raw_data = {'intro': {'usefeeculture': '<b>성인 3,000원</b><br>청소년 무료', 'parkingculture': '주차장 &amp; 장애인 주차', 'usetimefestival': '09:00–18:00'}}
        info.save()
        data = self.client.get(reverse('place-detail', args=[self.gyeongbokgung.id])).json()['data']['info']
        self.assertEqual(data['admission_fee'], '성인 3,000원\n청소년 무료')
        self.assertEqual(data['parking'], '주차장 & 장애인 주차')
        info.raw_data = {'intro': {'usetimefestival': '09:00–18:00'}}
        info.save()
        data = self.client.get(reverse('place-detail', args=[self.gyeongbokgung.id])).json()['data']['info']
        self.assertIsNone(data['admission_fee'])
        self.assertIsNone(data['parking'])


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

        detail_response = self.client.get(
            reverse('place-detail', args=[data['items'][0]['id']])
        )
        self.assertIn(
            '실제 운영에서는 TourAPI 상세정보로 갱신됩니다.',
            detail_response.json()['data']['info']['description'],
        )
