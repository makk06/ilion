from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from places.models import CrowdArea, CrowdData, DataJob, ExternalSource, Place, PlaceCrowdArea, PlaceSource, ProviderCallBudget, WeatherForecast
from places.services.weather import grid_for


class HealthzTests(TestCase):
    def test_healthz_returns_ok(self):
        response = self.client.get(reverse('healthz'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_healthz_rejects_post_requests(self):
        response = self.client.post(reverse('healthz'))

        self.assertEqual(response.status_code, 405)


class BackendTestDashboardTests(TestCase):
    url = '/test/backend/'

    @override_settings(DEBUG=True)
    def test_get_shows_snapshot_and_test_only_notice(self):
        Place.objects.create(
            name='테스트 장소', category='관광지', region_code='11', address='서울',
            latitude=37.5665, longitude=126.9780, indoor_outdoor='indoor',
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '이리온 백엔드 테스트베드 · 운영 화면 아님')
        self.assertContains(response, '실내외 분류')
        self.assertContains(response, '부산 해운대')
        self.assertEqual(response.context['snapshot']['total_places'], 1)
        self.assertEqual(response.context['snapshot']['classified_count'], 1)
        self.assertEqual(response.context['preview']['items'][0]['place']['name'], '테스트 장소')

    @override_settings(DEBUG=True)
    def test_weather_profile_panel_distinguishes_unknown_label_from_type_prior(self):
        palace = Place.objects.create(id=1, name='경복궁', category='관광지',
            subcategory='HS010100', region_code='11', address='서울',
            latitude=37.575, longitude=126.977)
        PlaceSource.objects.create(place=palace, source=ExternalSource.TOUR_API,
            external_id='126508', match_status='matched',
            raw_data={'lclsSystm3': 'HS010100'}, last_synced_at=timezone.now())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '실내외 분류가 미확인이어도')
        self.assertContains(response, '날씨 영향 큼')
        cases = response.context['weather_profile_cases']
        self.assertEqual(cases[0]['place'].id, 1)
        self.assertEqual((cases[0]['indoor_label'], cases[0]['profile']['source']),
                         ('미확인', 'type_prior'))

    @override_settings(DEBUG=True)
    def test_preview_uses_stored_data_without_enqueuing_jobs(self):
        Place.objects.create(
            name='추천 미리보기 장소', category='관광지', region_code='11', address='서울',
            latitude=37.5665, longitude=126.9780,
        )

        response = self.client.post(self.url, {
            'latitude': '37.5665', 'longitude': '126.9780', 'radius_km': '5',
            'limit': '10', 'crowd_level': 'any',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '추천 미리보기 장소')
        self.assertEqual(response.context['preview']['items'][0]['place']['name'], '추천 미리보기 장소')
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_invalid_preview_shows_validation_error(self):
        response = self.client.post(self.url, {
            'latitude': '999', 'longitude': '126.9780', 'radius_km': '5',
            'limit': '10', 'crowd_level': 'any',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '입력값을 확인해 주세요')
        self.assertIsNone(response.context['preview'])
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_weather_preview_does_not_enqueue_missing_forecast(self):
        Place.objects.create(
            name='예보 없는 실내 장소', category='관광지', region_code='11', address='서울',
            latitude=37.5665, longitude=126.9780, indoor_outdoor='indoor',
        )

        response = self.client.post(self.url, {
            'latitude': '37.5665', 'longitude': '126.9780', 'radius_km': '5',
            'limit': '10', 'crowd_level': 'any', 'weather_evidence_required': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['preview']['items'], [])
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_preview_can_filter_weather_evidence_without_scoring_weather(self):
        place = Place.objects.create(
            name='날씨 있는 실내', category='문화시설', region_code='11', address='서울',
            latitude=37.5665, longitude=126.9780, indoor_outdoor='indoor',
            indoor_outdoor_source='manual',
        )
        grid = grid_for(place.latitude, place.longitude)
        now = timezone.now()
        WeatherForecast.objects.create(grid_x=grid[0], grid_y=grid[1],
            issued_at=now - timedelta(hours=1),
            target_at=now.replace(minute=0, second=0, microsecond=0),
            precipitation_type=1, temperature_c=20, wind_mps=2)
        response = self.client.post(self.url, {
            'latitude': '37.5665', 'longitude': '126.9780', 'radius_km': '5',
            'limit': '10', 'crowd_level': 'any', 'weather_evidence_required': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form']['weather_aware'])
        preview = response.context['preview']
        self.assertEqual(len(preview['items']), 1)
        self.assertNotIn('weather', preview['items'][0]['score_contributors'])
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_valid_crowd_observation_is_visible_and_affects_requested_preference(self):
        place = Place.objects.create(
            name='혼잡도 시연 장소', category='관광지', region_code='11', address='서울',
            latitude=37.565055, longitude=126.976575,
        )
        area = CrowdArea.objects.create(
            source='seoul_realtime', external_id='POI009', name='광화문·덕수궁',
            last_synced_at=timezone.now(),
        )
        PlaceCrowdArea.objects.create(place=place, crowd_area=area)
        CrowdData.objects.create(crowd_area=area,
            observed_at=timezone.now() - timedelta(minutes=20), crowd_level='normal')

        response = self.client.post(self.url, {
            'latitude': '37.565055', 'longitude': '126.976575',
            'radius_km': '1', 'limit': '10', 'crowd_level': 'normal',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['snapshot']['crowd_valid'], 1)
        self.assertEqual(response.context['snapshot']['crowd_fresh'], 0)
        item = response.context['preview']['items'][0]
        self.assertEqual(item['crowd_label'], '보통')
        self.assertIn('crowd', item['score_contributors'])
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_delayed_crowd_is_labeled_in_temporary_dashboard(self):
        place = Place.objects.create(
            name='지연 관측 장소', category='관광지', region_code='11', address='서울',
            latitude=37.565055, longitude=126.976575,
        )
        area = CrowdArea.objects.create(source='seoul_realtime', external_id='POI009',
            name='광화문·덕수궁', last_synced_at=timezone.now())
        PlaceCrowdArea.objects.create(place=place, crowd_area=area)
        CrowdData.objects.create(crowd_area=area,
            observed_at=timezone.now() - timedelta(minutes=35), crowd_level='relaxed')
        response = self.client.post(self.url, {
            'latitude': '37.565055', 'longitude': '126.976575',
            'radius_km': '1', 'limit': '10', 'crowd_level': 'relaxed',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['snapshot']['crowd_delayed'], 1)
        self.assertEqual(response.context['snapshot']['crowd_valid'], 1)
        self.assertTrue(response.context['preview']['items'][0]['crowd']['is_delayed'])
        self.assertContains(response, '지연 관측 · 점수 영향 절반')

    @override_settings(DEBUG=True)
    def test_virtual_weather_comparison_uses_same_scorer_without_writing_forecasts(self):
        outdoor = Place.objects.create(name='가까운 야외', category='관광지', region_code='26',
            address='부산', latitude=35.160, longitude=129.160,
            indoor_outdoor='outdoor', indoor_outdoor_source='manual')
        indoor = Place.objects.create(name='가까운 실내', category='관광지', region_code='26',
            address='부산', latitude=35.160, longitude=129.160,
            indoor_outdoor='indoor', indoor_outdoor_source='manual')
        response = self.client.post(self.url, {'scenario': 'weather', 'latitude': '35.160',
            'longitude': '129.160', 'radius_km': '1', 'limit': '2',
            'crowd_level': 'any', 'weather_aware': 'on'})
        self.assertEqual(response.status_code, 200)
        experiment = response.context['experiment']
        self.assertTrue(experiment['virtual'])
        panels = [panel['preview'] for panel in experiment['panels']]
        self.assertEqual([panel['algorithm_version'] for panel in panels], ['mvp-7'] * 3)
        self.assertEqual([panel['items'][0]['place']['id'] for panel in panels],
                         [outdoor.id, indoor.id, indoor.id])
        self.assertTrue(all(panel['items'][0]['weather']['source'] == 'virtual_test_only'
                            for panel in panels))
        self.assertContains(response, '가상 날씨 실험 · 실제 예보가 아닙니다')
        self.assertEqual(WeatherForecast.objects.count(), 0)
        self.assertEqual(DataJob.objects.count(), 0)
        self.assertEqual(ProviderCallBudget.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_taste_and_distance_comparisons_use_real_places(self):
        shopping = Place.objects.create(name='가까운 쇼핑', category='쇼핑', region_code='26',
            address='부산', latitude=35.160, longitude=129.160)
        food = Place.objects.create(name='가까운 식당', category='음식점', region_code='26',
            address='부산', latitude=35.160, longitude=129.160)
        travel = Place.objects.create(name='관광 장소', category='관광지', region_code='26',
            address='부산', latitude=35.161, longitude=129.160)
        form = {'latitude': '35.160', 'longitude': '129.160', 'radius_km': '2',
                'limit': '3', 'crowd_level': 'any'}
        taste = self.client.post(self.url, {**form, 'scenario': 'taste'})
        self.assertEqual(taste.status_code, 200)
        panels = [p['preview'] for p in taste.context['experiment']['panels']]
        self.assertEqual([p['items'][0]['place']['id'] for p in panels],
                         [travel.id, food.id, shopping.id])
        distance = self.client.post(self.url, {**form, 'scenario': 'distance', 'category': '쇼핑'})
        self.assertEqual(distance.status_code, 200)
        before, after = [p['preview'] for p in distance.context['experiment']['panels']]
        self.assertTrue(before['is_distance'])
        self.assertEqual(before['items'][0]['place']['id'], shopping.id)
        self.assertEqual(after['items'][0]['place']['id'], travel.id)
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_strict_panels_show_shortage_without_relaxing_evidence(self):
        indoor = Place.objects.create(name='분류된 실내', category='관광지', region_code='11',
            address='서울', latitude=37.575, longitude=126.977,
            indoor_outdoor='indoor', indoor_outdoor_source='manual')
        Place.objects.create(name='미분류', category='관광지', region_code='11',
            address='서울', latitude=37.575, longitude=126.978)
        response = self.client.post(self.url, {'scenario': 'strict', 'latitude': '37.575',
            'longitude': '126.977', 'radius_km': '1', 'limit': '10', 'crowd_level': 'any'})
        self.assertEqual(response.status_code, 200)
        panels = [p['preview'] for p in response.context['experiment']['panels']]
        self.assertEqual([len(p['items']) for p in panels], [2, 0, 1, 0])
        self.assertEqual(panels[2]['items'][0]['place']['id'], indoor.id)
        self.assertIn('근거', panels[1]['message'])
        self.assertContains(response, '근거가 없거나 만료됐다면 빈 결과가 정상입니다')
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_public_scenarios_are_read_only_and_virtual_weather_is_isolated(self):
        Place.objects.create(name='공개 시안 장소', category='관광지', region_code='11',
            address='서울', latitude=37.575, longitude=126.977,
            indoor_outdoor='outdoor', indoor_outdoor_source='manual')
        with patch('recommendations.service._prepare_jobs') as enqueue_jobs:
            for scenario in ('live', 'weather', 'taste', 'strict', 'distance'):
                with self.subTest(scenario=scenario), CaptureQueriesContext(connection) as queries:
                    response = self.client.post(self.url, {
                        'scenario': scenario, 'latitude': '37.575', 'longitude': '126.977',
                        'radius_km': '3', 'limit': '3', 'crowd_level': 'any',
                        'weather_aware': 'on',
                    })
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context['form_errors'])
                self.assertFalse(any(q['sql'].lstrip().upper().startswith(
                    ('INSERT', 'UPDATE', 'DELETE', 'REPLACE')) for q in queries))
                if scenario == 'weather':
                    self.assertContains(response, '실제 예보가 아닙니다')
                    panels = response.context['experiment']['panels']
                    self.assertEqual([p['preview']['items'][0]['weather']['precipitation_type']
                                      for p in panels], [0, 1, 0])
                    self.assertNotEqual(panels[0]['preview']['items'][0]['recommendation_score'],
                                        panels[1]['preview']['items'][0]['recommendation_score'])
            enqueue_jobs.assert_not_called()
        self.assertEqual(WeatherForecast.objects.count(), 0)
        self.assertEqual(DataJob.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_public_api_does_not_use_testbed_weather_fields(self):
        Place.objects.create(name='야외', category='관광지', region_code='11',
            address='서울', latitude=37.575, longitude=126.977,
            indoor_outdoor='outdoor', indoor_outdoor_source='manual')
        with patch('recommendations.service._prepare_jobs', return_value=[]):
            response = self.client.post('/api/recommendations', {
                'latitude': 37.575, 'longitude': 126.977, 'radius_km': 1, 'limit': 1,
                'crowd_level': 'any', 'scenario': 'weather', 'virtual_weather': 'rain',
            }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('weather', response.json()['data']['items'][0]['score_contributors'])

    @override_settings(DEBUG=False)
    def test_public_preview_excludes_operational_diagnostics(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)
        self.assertContains(response, '이리온 추천 MVP 시안 · 개발 중')
        self.assertNotContains(response, '오늘의 호출 예산')
        self.assertNotContains(response, '백엔드 작업 현황')
        self.assertNotContains(response, 'AI 시도')
        self.assertNotIn('budgets', response.context['snapshot'])
        self.assertFalse(any('places_datajob' in q['sql'].lower() or
                             'places_providercallbudget' in q['sql'].lower() for q in queries))
        self.assertIn('no-store', response.headers['Cache-Control'])

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True, CSRF_COOKIE_SECURE=True)
    def test_public_form_preserves_csrf_protection_over_https(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get(self.url, secure=True)
        self.assertEqual(page.status_code, 200)
        self.assertTrue(client.cookies['csrftoken']['secure'])
        self.assertEqual(client.post(self.url, {}, secure=True).status_code, 403)
        response = client.post(self.url, {
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
            'latitude': '37.575', 'longitude': '126.977', 'radius_km': '3',
            'limit': '3', 'crowd_level': 'any', 'scenario': 'live',
        }, secure=True, HTTP_ORIGIN='https://testserver')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['form_errors'])
