from django.test import TestCase
from places.models import Place, PlaceSource
from django.utils import timezone


class RegionAPITests(TestCase):
    def setUp(self):
        for name, address in [('yeongtong', '경기도 수원시 영통구 광교로 1'), ('paldal', '경기 수원시 팔달구 행궁로 2'), ('sujeong', '경기도 성남시 수정구 산성대로 3'), ('county', '경기도 양평군 양평읍 1'), ('seoul', '서울 강남구 테헤란로 1')]:
            Place.objects.create(name=name, address=address, category='관광지', region_code='31', latitude=37, longitude=127)
        hidden = Place.objects.create(name='hidden', address='경기도 안산시 단원구 1', category='관광지', region_code='31', latitude=37, longitude=127)
        PlaceSource.objects.create(place=hidden, source='tour_api', external_id='hidden', match_status='inactive', last_synced_at=timezone.now())

    def test_tree_all_visible_records_not_limited_by_page(self):
        data = self.client.get('/api/places/regions', {'page_size': 1}).json()['data']
        self.assertEqual(data['coverage'], 'registered_places')
        provinces = {item['name']: item for item in data['items']}
        cities = {item['name']: item for item in provinces['경기도']['children']}
        self.assertEqual(set(cities), {'수원시', '성남시', '양평군'})
        self.assertEqual([item['path'] for item in cities['수원시']['children']], ['경기도/수원시/영통구', '경기도/수원시/팔달구'])
        self.assertEqual(cities['양평군']['children'], [])
        self.assertEqual(provinces['서울특별시']['children'][0]['name'], '강남구')

    def test_exact_city_and_district_filters_and_alias(self):
        def names(path):
            response = self.client.get('/api/places', {'region_path': path})
            self.assertEqual(response.status_code, 200)
            return {item['name'] for item in response.json()['data']['items']}
        self.assertEqual(names('경기도/수원시'), {'yeongtong', 'paldal'})
        self.assertEqual(names('경기/수원시/영통구'), {'yeongtong'})
        self.assertEqual(names('경기도/수원'), set())
        self.assertEqual(names('경기도/성남시/영통구'), set())
        self.assertEqual(self.client.get('/api/places', {'region_path': '경기도//수원시'}).status_code, 400)
        self.assertEqual(self.client.get('/api/places', {'region_path': '미등록도'}).status_code, 400)
