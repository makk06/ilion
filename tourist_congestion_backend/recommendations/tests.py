from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from users.models import User

from places.integrations.exceptions import ExternalAPIError
from places.integrations.seoul_realtime import SeoulPopulationRecord
from places.job_models import DataJob
from places.models import CrowdArea, CrowdData, Place, PlaceCrowdArea, PlaceInfo, WeatherForecast
from places.services.jobs import _execute, debit, enqueue, run_one
from places.services.weather import (
    forecasts_for, grid_for, latest_available_issue, parse_forecast_page, save_forecast,
)
from places.integrations.tour_api import TourAPIPage, normalize_tour_place
from places.views import _visible_places
from places.dev_seed_data import TOUR_PLACE_ITEMS
from places.job_models import ProviderCallBudget
from .service import (
    clear_recommendation_context_cache, _load_candidates, _prepare_jobs, recommend,
)


NOW = datetime(2026, 9, 12, 5, 0, tzinfo=dt_timezone.utc)
BASE = {'latitude': 35.16, 'longitude': 129.16, 'radius_km': 10,
        'crowd_level': 'any', 'limit': 10}


def place(name, lat, lon, indoor='unknown', category='관광지', source=None):
    return Place.objects.create(name=name, category=category, region_code='26',
        address='테스트 주소', latitude=lat, longitude=lon, indoor_outdoor=indoor,
        indoor_outdoor_source=source if source is not None else ('manual' if indoor != 'unknown' else ''))


@override_settings(RECOMMENDATION_CONTEXT_CACHE_SECONDS=0)
class RecommendationTests(TestCase):
    def _forecast(self, place_obj, *, pty=0, temperature=20, wind=2,
                  issued_at=NOW - timedelta(hours=3)):
        grid = grid_for(place_obj.latitude, place_obj.longitude)
        return WeatherForecast.objects.create(grid_x=grid[0], grid_y=grid[1],
            issued_at=issued_at, target_at=NOW,
            precipitation_type=pty, temperature_c=temperature, wind_mps=wind)

    def test_non_seoul_weather_changes_order_and_missing_is_not_assumed(self):
        outdoor = place('해변', 35.16, 129.16, 'outdoor')
        indoor = place('실내', 35.16, 129.161, 'indoor')
        unknown = place('미확인', 35.16, 129.162)
        grid = grid_for(outdoor.latitude, outdoor.longitude)
        self.assertEqual(grid, grid_for(indoor.latitude, indoor.longitude))
        WeatherForecast.objects.create(grid_x=grid[0], grid_y=grid[1],
            issued_at=NOW - timedelta(hours=3), target_at=NOW,
            precipitation_type=1, temperature_c=20, wind_mps=11)
        nearby, _ = recommend(BASE, now=NOW, supplement=False)
        ids = [item['place']['id'] for item in nearby['items']]
        self.assertLess(ids.index(indoor.id), ids.index(outdoor.id))
        self.assertLess(ids.index(indoor.id), ids.index(unknown.id))
        self.assertEqual(nearby['ranking_basis'], 'weather_and_travel_discovery')
        self.assertIn('weather', next(i for i in nearby['items'] if i['place']['id'] == unknown.id)['missing_data'])
        weather_aware, _ = recommend({**BASE, 'weather_evidence_required': True}, now=NOW, supplement=False)
        ids = [item['place']['id'] for item in weather_aware['items']]
        self.assertNotIn(unknown.id, ids)

    def test_forecast_lookup_is_shared_by_grid_and_skips_unknown_places(self):
        indoor = place('실내 A', 35.16, 129.16, 'indoor')
        place('실내 B', 35.161, 129.161, 'indoor')
        place('미확인', 35.162, 129.162)
        with patch('recommendations.service.forecasts_for', return_value={}) as lookup:
            recommend(BASE, now=NOW, supplement=False)
        lookup.assert_called_once()
        self.assertEqual(set(lookup.call_args.args[0]), {
            grid_for(indoor.latitude, indoor.longitude),
        })

    def test_recommendation_batches_forecasts_and_omits_large_detail_fields(self):
        first = place('첫 실내', 35.16, 129.16, 'indoor')
        second = place('둘째 실내', 35.20, 129.16, 'indoor')
        self._forecast(first)
        self._forecast(second)
        with CaptureQueriesContext(connection) as queries:
            recommend(BASE, now=NOW, supplement=False)
        self.assertLessEqual(len(queries), 6)
        candidate_sql = next(
            query['sql'] for query in queries
            if 'FROM "places_place"' in query['sql']
        )
        self.assertNotIn('"places_placeinfo"."raw_data"', candidate_sql)
        self.assertNotIn('places_crowddata', candidate_sql.lower())

    def test_supplement_enqueues_without_polling_running_jobs(self):
        place('실내', 35.16, 129.16, 'indoor')
        running = DataJob(id=999, status=DataJob.Status.RUNNING)
        with patch('recommendations.service._prepare_jobs', return_value=[running]) as prepare, \
             CaptureQueriesContext(connection) as queries:
            response, _ = recommend(BASE, now=NOW, supplement=True)
        self.assertEqual(len(response['items']), 1)
        prepare.assert_called_once()
        self.assertFalse(any('places_datajob' in query['sql'].lower() for query in queries))

    @override_settings(RECOMMENDATION_CONTEXT_CACHE_SECONDS=60)
    def test_static_context_cache_reuses_candidates_but_refreshes_crowd(self):
        candidate = place('캐시 후보', 35.16, 129.16)
        clear_recommendation_context_cache()
        try:
            with patch('recommendations.service._load_candidates',
                       wraps=_load_candidates) as load:
                first, _ = recommend(BASE, now=NOW, supplement=False)
                area = CrowdArea.objects.create(source='seoul_realtime', external_id='POI777',
                                                name='cache-test', last_synced_at=NOW)
                PlaceCrowdArea.objects.create(place=candidate, crowd_area=area)
                CrowdData.objects.create(crowd_area=area,
                                         observed_at=NOW - timedelta(minutes=5),
                                         crowd_level='relaxed')
                second, _ = recommend(BASE, now=NOW, supplement=False)
            self.assertEqual(load.call_count, 1)
            self.assertIsNone(first['items'][0]['crowd'])
            self.assertEqual(second['items'][0]['crowd']['level'], 'relaxed')
        finally:
            clear_recommendation_context_cache()

    def test_weather_opt_out_and_required_evidence_are_independent(self):
        outdoor = place('가까운 야외', 35.16, 129.16, 'outdoor')
        indoor = place('실내', 35.16, 129.161, 'indoor')
        unclassified = place('미분류', 35.16, 129.1605)
        self._forecast(outdoor, pty=1)
        opt_out, _ = recommend({**BASE, 'weather_aware': False}, now=NOW, supplement=False)
        self.assertEqual(opt_out['items'][0]['place']['id'], outdoor.id)
        self.assertEqual(opt_out['ranking_basis'], 'travel_discovery')
        self.assertNotIn('weather', opt_out['items'][0]['score_contributors'])
        self.assertFalse(any('날씨 점수' in reason for reason in opt_out['items'][0]['reasons']))
        strict, _ = recommend({**BASE, 'weather_aware': False,
            'weather_evidence_required': True}, now=NOW, supplement=False)
        self.assertEqual([i['place']['id'] for i in strict['items']], [outdoor.id, indoor.id])
        self.assertNotIn(unclassified.id, [i['place']['id'] for i in strict['items']])
        self.assertEqual(strict['ranking_factors'], ['distance', 'category'])
        self.assertTrue(strict['weather_evidence_required'])

    def test_strict_filter_can_request_weather_refresh_with_ranking_opted_out(self):
        place('실내', 35.16, 129.16, 'indoor')
        with patch('recommendations.service._prepare_jobs', return_value=[]) as prepare:
            recommend({**BASE, 'weather_aware': False}, now=NOW, supplement=True)
            self.assertFalse(prepare.call_args.kwargs['weather_requested'])
            recommend({**BASE, 'weather_aware': False,
                       'weather_evidence_required': True}, now=NOW, supplement=True)
            self.assertTrue(prepare.call_args.kwargs['weather_requested'])

    def test_complete_fair_rain_and_partial_forecast_are_distinct(self):
        outdoor = place('야외', 35.16, 129.16, 'outdoor')
        indoor = place('실내', 35.16, 129.167, 'indoor')
        forecast = self._forecast(outdoor)
        fair, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertEqual(fair['items'][0]['place']['id'], outdoor.id)
        forecast.precipitation_type = 1
        forecast.save()
        rain, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertEqual(rain['items'][0]['place']['id'], indoor.id)
        self.assertGreater(rain['items'][0]['distance_km'], fair['items'][0]['distance_km'])
        forecast.precipitation_type = None
        forecast.wind_mps = None
        forecast.save()
        partial_benign, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertEqual(partial_benign['ranking_factors'], ['distance', 'category'])
        self.assertEqual(partial_benign['items'][0]['weather_status'], 'partial_uninformative')
        self.assertIsNone(partial_benign['items'][0]['score_breakdown']['weather'])
        forecast.precipitation_type = 1
        forecast.temperature_c = None
        forecast.save()
        partial_hazard, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertEqual(partial_hazard['items'][0]['place']['id'], indoor.id)
        self.assertEqual(partial_hazard['items'][0]['weather_status'], 'partial_hazard')
        self.assertIn('확인된 악조건만', ' '.join(partial_hazard['items'][0]['reasons']))

    def test_expired_issue_is_missing_and_queued_for_refresh(self):
        indoor = place('실내', 35.16, 129.16, 'indoor')
        self._forecast(indoor, pty=1, issued_at=NOW - timedelta(hours=6))
        result, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertIsNone(result['items'][0]['weather'])
        self.assertIsNone(result['items'][0]['score_breakdown']['weather'])
        strict, _ = recommend({**BASE, 'weather_evidence_required': True},
                              now=NOW, supplement=False)
        self.assertEqual(strict['items'], [])
        with patch('recommendations.service.enqueue') as enqueue_job:
            _prepare_jobs([(0, _visible_places().get(pk=indoor.pk))], NOW, NOW,
                          weather_requested=True)
        self.assertEqual(enqueue_job.call_args.args[:2], ('weather', f'{grid_for(indoor.latitude, indoor.longitude)[0]}:{grid_for(indoor.latitude, indoor.longitude)[1]}'))

    def test_future_visit_uses_target_forecast_but_not_current_crowd(self):
        future = NOW + timedelta(hours=2)
        outdoor = place('야외', 35.16, 129.16, 'outdoor')
        indoor = place('실내', 35.16, 129.161, 'indoor')
        grid = grid_for(outdoor.latitude, outdoor.longitude)
        WeatherForecast.objects.create(grid_x=grid[0], grid_y=grid[1],
            issued_at=NOW - timedelta(hours=2), target_at=future,
            precipitation_type=1, temperature_c=20, wind_mps=2)
        area = CrowdArea.objects.create(source='seoul_realtime', external_id='POI099',
                                        name='test', last_synced_at=NOW)
        PlaceCrowdArea.objects.create(place=indoor, crowd_area=area)
        CrowdData.objects.create(crowd_area=area, observed_at=NOW - timedelta(minutes=5),
                                 crowd_level='relaxed')
        result, _ = recommend({**BASE, 'visit_at': future}, now=NOW, supplement=False)
        self.assertEqual(result['items'][0]['place']['id'], indoor.id)
        self.assertIn('weather', result['items'][0]['score_contributors'])
        self.assertIsNone(result['items'][0]['crowd'])
        forecast = WeatherForecast.objects.get()
        forecast.issued_at = NOW - timedelta(hours=6)
        forecast.save()
        expired, _ = recommend({**BASE, 'visit_at': future}, now=NOW, supplement=False)
        self.assertNotIn('weather', expired['ranking_factors'])

    def test_name_inference_is_weaker_and_unattributed_label_is_not_evidence(self):
        manual = place('수동 실내', 35.16, 129.16, 'indoor')
        inferred = place('이름 추론 도서관', 35.16, 129.16, 'indoor', source='reviewed_name_rule_v5')
        unattributed = place('출처 없음', 35.16, 129.16, 'indoor', source='')
        self._forecast(manual, pty=1)
        result, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertEqual([i['place']['id'] for i in result['items']],
                         [manual.id, inferred.id, unattributed.id])
        by_id = {i['place']['id']: i for i in result['items']}
        self.assertEqual(by_id[inferred.id]['place']['indoor_outdoor_evidence_quality'], 'inferred_from_name')
        self.assertEqual(by_id[inferred.id]['score_effective_breakdown']['weather'], 72.5)
        self.assertIsNone(by_id[unattributed.id]['score_breakdown']['weather'])
        self.assertNotIn('weather', by_id[unattributed.id]['score_contributors'])
        strict, _ = recommend({**BASE, 'weather_evidence_required': True}, now=NOW, supplement=False)
        self.assertEqual([i['place']['id'] for i in strict['items']], [manual.id, inferred.id])
        hard, _ = recommend({**BASE, 'required_indoor_outdoor': 'indoor'},
                            now=NOW, supplement=False)
        self.assertNotIn(unattributed.id, [i['place']['id'] for i in hard['items']])
        self.assertNotIn(inferred.id, [i['place']['id'] for i in hard['items']])

    def test_default_travel_intent_is_soft_and_explicit_preference_replaces_it(self):
        shop = place('가까운 상점', 35.16, 129.16, category='쇼핑')
        landmark = place('약간 먼 명소', 35.16, 129.166, category='관광지')
        default, _ = recommend({**BASE, 'weather_aware': False}, now=NOW, supplement=False)
        self.assertEqual(default['items'][0]['place']['id'], landmark.id)
        self.assertEqual(default['preference_source'], 'default_travel_intent')
        explicit, _ = recommend({**BASE, 'category': '쇼핑', 'weather_aware': False},
                                now=NOW, supplement=False)
        self.assertEqual(explicit['items'][0]['place']['id'], shop.id)
        self.assertEqual(explicit['preference_source'], 'request')
        user = User.objects.create(email='visitor@example.com', nickname='visitor',
                                   preferred_categories=['쇼핑'])
        profile, _ = recommend({**BASE, 'weather_aware': False}, user=user,
                               now=NOW, supplement=False)
        self.assertEqual(profile['items'][0]['place']['id'], shop.id)
        self.assertEqual(profile['preference_source'], 'profile')

    def test_large_radius_does_not_allow_distant_weather_jump(self):
        near = place('10km 야외', 35.25, 129.16, 'outdoor')
        far = place('80km 실내', 35.88, 129.16, 'indoor')
        self._forecast(near, pty=1)
        # Use a second forecast grid so both venues have the same adverse evidence.
        self._forecast(far, pty=1)
        data, _ = recommend({**BASE, 'radius_km': 100}, now=NOW, supplement=False)
        self.assertEqual(data['items'][0]['place']['id'], near.id)
        self.assertLess(data['items'][0]['distance_km'], data['items'][1]['distance_km'])
        self.assertLess(data['items'][1]['distance_adjustment']['factor'],
                        data['items'][0]['distance_adjustment']['factor'])


    def test_weather_evidence_required_excludes_unverified_candidates(self):
        verified = place('실내', 35.16, 129.16, 'indoor')
        place('가까운 미확인', 35.16, 129.1601)
        grid = grid_for(verified.latitude, verified.longitude)
        WeatherForecast.objects.create(grid_x=grid[0], grid_y=grid[1],
            issued_at=NOW - timedelta(hours=3), target_at=NOW,
            precipitation_type=1, temperature_c=20, wind_mps=2)
        data, message = recommend({**BASE, 'weather_evidence_required': True},
                                  now=NOW, supplement=False)
        self.assertEqual([item['place']['id'] for item in data['items']], [verified.id])
        self.assertEqual(data['ranking_basis'], 'weather_and_travel_discovery')
        self.assertTrue(data['weather_evidence_required'])
        self.assertIsNotNone(data['items'][0]['weather'])
        self.assertIn('근거', message)

    def test_supplement_does_not_queue_weather_for_unknown_place(self):
        unknown = place('미확인', 35.16, 129.16)
        with patch('recommendations.service.enqueue') as enqueue_job:
            _prepare_jobs([(0, _visible_places().get(pk=unknown.pk))], NOW, NOW,
                          weather_requested=True)
        enqueue_job.assert_not_called()

    def test_supplement_finds_verified_grid_after_many_unknown_places(self):
        Place.objects.bulk_create([Place(name=f'미분류 {index}', category='관광지',
            region_code='26', address='테스트 주소', latitude=35.16,
            longitude=129.16) for index in range(501)])
        verified = place('분류된 장소', 35.16, 129.161, 'indoor')
        candidates = [(0, candidate) for candidate in _visible_places().order_by('id')]
        with patch('recommendations.service.enqueue') as enqueue_job:
            _prepare_jobs(candidates, NOW, NOW, weather_requested=True)
        self.assertEqual(enqueue_job.call_args.args[0], 'weather')
        self.assertEqual(enqueue_job.call_count, 1)
        self.assertEqual(candidates[-1][1].id, verified.id)

    def test_default_supplement_does_not_query_crowd_mapping_per_candidate(self):
        Place.objects.bulk_create([Place(name=f'미분류 {index}', category='관광지',
            region_code='26', address='테스트 주소', latitude=35.16,
            longitude=129.16) for index in range(120)])
        with CaptureQueriesContext(connection) as queries:
            recommend(BASE, now=NOW, supplement=True)
        self.assertLess(len(queries), 12)

    def test_default_crowd_only_adds_a_bounded_risk_penalty(self):
        near = place('관측 있는 근처', 35.16, 129.16)
        unknown = place('관측 없는 먼 곳', 35.16, 129.17)
        area = CrowdArea.objects.create(source='seoul_realtime', external_id='POI008',
                                        name='test', last_synced_at=NOW)
        PlaceCrowdArea.objects.create(place=near, crowd_area=area)
        CrowdData.objects.create(crowd_area=area, observed_at=NOW - timedelta(minutes=10),
                                 crowd_level='crowded')
        data, _ = recommend(BASE, now=NOW, supplement=False)
        observed = next(i for i in data['items'] if i['place']['id'] == near.id)
        unobserved = next(i for i in data['items'] if i['place']['id'] == unknown.id)
        self.assertIn('crowd', observed['score_contributors'])
        self.assertNotIn('crowd', unobserved['score_contributors'])
        self.assertIsNone(unobserved['score_breakdown']['crowd'])
        self.assertLess(observed['recommendation_score'], 100)
        self.assertEqual(observed['crowd']['level'], 'crowded')

    def test_events_require_verified_dates_covering_visit_day(self):
        active = place('진행 중 행사', 35.16, 129.16, category='축제/공연/행사')
        expired = place('지난 행사', 35.16, 129.161, category='축제/공연/행사')
        place('기간 미확인 행사', 35.16, 129.162, category='축제/공연/행사')
        PlaceInfo.objects.create(place=active, raw_data={'intro': {
            'eventstartdate': '20260901', 'eventenddate': '20260930'}})
        PlaceInfo.objects.create(place=expired, raw_data={'intro': {
            'eventstartdate': '20260801', 'eventenddate': '20260831'}})
        data, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertEqual([item['place']['id'] for item in data['items']], [active.id])
        outside, _ = recommend({**BASE, 'visit_at': NOW + timedelta(days=30)},
                               now=NOW, supplement=False)
        self.assertEqual(outside['items'], [])

    def test_future_visit_does_not_reuse_current_crowd_and_expired_crowd_is_excluded(self):
        p = place('부산', 35.16, 129.16)
        area = CrowdArea.objects.create(source='seoul_realtime', external_id='POI001', name='test', last_synced_at=NOW)
        PlaceCrowdArea.objects.create(place=p, crowd_area=area)
        obs = CrowdData.objects.create(crowd_area=area, observed_at=NOW - timedelta(minutes=10), crowd_level='relaxed')
        current, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertIsNotNone(current['items'][0]['crowd'])
        obs.observed_at = NOW - timedelta(minutes=20)
        obs.save()
        stale, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertTrue(stale['items'][0]['crowd']['is_stale'])
        future, _ = recommend({**BASE, 'visit_at': NOW + timedelta(hours=2)}, now=NOW, supplement=False)
        self.assertIsNone(future['items'][0]['crowd'])
        obs.observed_at = NOW - timedelta(minutes=46)
        obs.save()
        expired, _ = recommend(BASE, now=NOW, supplement=False)
        self.assertIsNone(expired['items'][0]['crowd'])

    def test_delayed_crowd_halves_effective_weight_and_cannot_prove_quiet(self):
        p = place('서울 관측 장소', 35.16, 129.16)
        area = CrowdArea.objects.create(source='seoul_realtime', external_id='POI001',
                                        name='test', last_synced_at=NOW)
        PlaceCrowdArea.objects.create(place=p, crowd_area=area)
        obs = CrowdData.objects.create(crowd_area=area,
            observed_at=NOW - timedelta(minutes=20), crowd_level='busy')
        criteria = {**BASE, 'crowd_level': 'relaxed'}
        normal, _ = recommend(criteria, now=NOW, supplement=False)
        self.assertEqual(normal['items'][0]['recommendation_score'], 74.62)
        self.assertEqual(normal['items'][0]['data_coverage'], .65)

        obs.observed_at = NOW - timedelta(minutes=35)
        obs.save()
        delayed, _ = recommend(criteria, now=NOW, supplement=False)
        item = delayed['items'][0]
        self.assertEqual(item['recommendation_score'], 78.46)
        self.assertEqual(item['data_coverage'], .55)
        self.assertEqual(item['score_breakdown']['crowd'], 25)
        self.assertEqual(item['crowd']['type'], 'delayed_observation')
        self.assertEqual(item['crowd']['score_weight_factor'], .5)
        self.assertTrue(item['crowd']['is_delayed'])

        obs.crowd_level = 'relaxed'
        obs.save()
        strict, _ = recommend({**criteria, 'quiet_required': True}, now=NOW,
                              supplement=False)
        self.assertEqual(strict['items'], [])
        obs.observed_at = NOW - timedelta(minutes=20)
        obs.save()
        strict_fresh, _ = recommend({**criteria, 'quiet_required': True}, now=NOW,
                                    supplement=False)
        self.assertEqual([item['place']['id'] for item in strict_fresh['items']], [p.id])

    def test_hard_filters_shortage_and_deterministic_tie(self):
        a = place('a', 35.16, 129.16, 'outdoor')
        b = place('b', 35.16, 129.16, 'outdoor')
        place('c', 35.16, 129.16, 'indoor')
        criteria = {**BASE, 'required_indoor_outdoor': 'outdoor'}
        first, message = recommend(criteria, now=NOW, supplement=False)
        second, _ = recommend(criteria, now=NOW, supplement=False)
        self.assertEqual([i['place']['id'] for i in first['items']], [a.id, b.id])
        self.assertEqual(first['items'], second['items'])
        self.assertIn('후보', message)
        self.assertEqual(first['items'][0]['travel_time_minutes'], None)
        self.assertEqual(first['items'][0]['data_coverage'], .45)

    def test_quiet_required_never_treats_unknown_as_quiet(self):
        place('미확인', 35.16, 129.16)
        result, _ = recommend({**BASE, 'quiet_required': True}, now=NOW, supplement=False)
        self.assertEqual(result['items'], [])

    def test_api_limit_and_validation(self):
        place('부산', 35.16, 129.16)
        response = self.client.post('/api/recommendations', {**BASE, 'limit': 11}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        with patch('recommendations.service._prepare_jobs'):
            response = self.client.post('/api/recommendations', BASE, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['data']['items']), 1)
        self.assertEqual(response.json()['data']['ranking_basis'], 'travel_discovery')
        with patch('recommendations.service._prepare_jobs'):
            strict = self.client.post('/api/recommendations',
                {**BASE, 'weather_evidence_required': True},
                content_type='application/json')
        self.assertEqual(strict.status_code, 200)
        self.assertEqual(strict.json()['data']['items'], [])
        self.assertEqual(strict.json()['data']['ranking_basis'], 'travel_discovery')
        self.assertTrue(strict.json()['data']['weather_evidence_required'])

    def test_api_default_opt_out_and_strict_modes_expose_rank_policy(self):
        outdoor = place('야외', 35.16, 129.16, 'outdoor')
        indoor = place('실내', 35.16, 129.161, 'indoor')
        unknown = place('미확인', 35.16, 129.162)
        self._forecast(outdoor, pty=1)
        with patch('recommendations.service.timezone.now', return_value=NOW), \
             patch('recommendations.service._prepare_jobs', return_value=[]):
            default = self.client.post('/api/recommendations', BASE, content_type='application/json')
            opt_out = self.client.post('/api/recommendations', {**BASE, 'weather_aware': False},
                                       content_type='application/json')
            strict = self.client.post('/api/recommendations',
                {**BASE, 'weather_aware': False, 'weather_evidence_required': True},
                content_type='application/json')
        self.assertEqual([response.status_code for response in (default, opt_out, strict)], [200, 200, 200])
        default_data, opt_out_data, strict_data = (response.json()['data'] for response in (default, opt_out, strict))
        self.assertEqual(default_data['items'][0]['place']['id'], indoor.id)
        self.assertIn('weather', default_data['ranking_factors'])
        self.assertEqual(opt_out_data['items'][0]['place']['id'], outdoor.id)
        self.assertNotIn('weather', opt_out_data['ranking_factors'])
        self.assertEqual(strict_data['items'][0]['place']['id'], outdoor.id)
        self.assertNotIn(unknown.id, [item['place']['id'] for item in strict_data['items']])
        self.assertTrue(strict_data['weather_evidence_required'])
        self.assertEqual(strict_data['ranking_policy']['missing_evidence_baseline'], 50)
        self.assertIn('distance_adjustment', default_data['items'][0])


class WeatherAndJobTests(TestCase):
    def test_forecasts_for_loads_latest_rows_for_all_grids_in_one_query(self):
        first_grid = (60, 127)
        second_grid = (98, 76)
        older = WeatherForecast.objects.create(
            grid_x=first_grid[0], grid_y=first_grid[1],
            issued_at=NOW - timedelta(hours=4), target_at=NOW,
        )
        latest = WeatherForecast.objects.create(
            grid_x=first_grid[0], grid_y=first_grid[1],
            issued_at=NOW - timedelta(hours=3), target_at=NOW,
        )
        other = WeatherForecast.objects.create(
            grid_x=second_grid[0], grid_y=second_grid[1],
            issued_at=NOW - timedelta(hours=3), target_at=NOW,
        )
        with CaptureQueriesContext(connection) as queries:
            result = forecasts_for({first_grid, second_grid}, NOW, NOW)
        self.assertEqual(len(queries), 1)
        self.assertEqual(result[first_grid].id, latest.id)
        self.assertEqual(result[second_grid].id, other.id)
        self.assertNotEqual(result[first_grid].id, older.id)
        self.assertIn('raw_data', result[first_grid].get_deferred_fields())

    def test_issue_selection_respects_release_and_first_target_independently(self):
        utc = dt_timezone.utc
        now = datetime(2026, 9, 13, 5, 20, tzinfo=utc)  # KST 14:20
        self.assertEqual(latest_available_issue(now, now), datetime(2026, 9, 13, 2, tzinfo=utc))
        self.assertEqual(latest_available_issue(now, datetime(2026, 9, 13, 6, tzinfo=utc)),
                         datetime(2026, 9, 13, 5, tzinfo=utc))
        self.assertEqual(latest_available_issue(datetime(2026, 9, 13, 5, 5, tzinfo=utc),
                                                datetime(2026, 9, 13, 6, tzinfo=utc)),
                         datetime(2026, 9, 13, 2, tzinfo=utc))
        self.assertEqual(latest_available_issue(datetime(2026, 9, 13, 14, 20, tzinfo=utc),
                                                datetime(2026, 9, 13, 15, tzinfo=utc)),
                         datetime(2026, 9, 13, 14, tzinfo=utc))

    def test_target_aware_worker_keeps_covering_issue_and_checks_response_target(self):
        now = datetime(2026, 9, 13, 5, 20, tzinfo=dt_timezone.utc)
        issue = datetime(2026, 9, 13, 2, tzinfo=dt_timezone.utc)
        target = datetime(2026, 9, 13, 5, tzinfo=dt_timezone.utc)
        job = DataJob(kind='weather', target_key='60:127', lane='supplemental',
                      payload={'grid': [60, 127], 'issued_at': issue.isoformat(), 'target_at': target.isoformat()})
        # A cached later target does not prove the requested hour is covered.
        WeatherForecast.objects.create(grid_x=60, grid_y=127, issued_at=issue,
                                       target_at=target + timedelta(hours=1), raw_data={'PTY': '0'})
        with patch('places.services.jobs.timezone.now', return_value=now), \
             patch('places.services.jobs.KMAForecastClient') as client, \
             patch('places.services.jobs.save_forecast', return_value=1):
            client.return_value.fetch.return_value = [(target, 'PTY', '0')]
            self.assertFalse(_execute(job))
            self.assertEqual(client.return_value.fetch.call_args.args[1], issue)
            client.return_value.fetch.return_value = [(target + timedelta(hours=1), 'PTY', '0')]
            with self.assertRaises(ExternalAPIError):
                _execute(job)

    def test_old_visit_does_not_queue_weather_or_raise(self):
        venue = place('실내', 35.16, 129.16, 'indoor')
        with patch('recommendations.service.enqueue') as schedule:
            self.assertEqual(_prepare_jobs([(0.0, venue)], NOW - timedelta(days=4), NOW,
                                           weather_requested=True), [])
        schedule.assert_not_called()

    def test_weather_parser_rejects_mismatched_grid_and_keeps_issuance(self):
        issue = NOW - timedelta(hours=3)
        local = issue.astimezone(dt_timezone(timedelta(hours=9)))
        payload = {'response': {'header': {'resultCode': '00'}, 'body': {
            'totalCount': 1, 'items': {'item': [{
                'baseDate': local.strftime('%Y%m%d'), 'baseTime': local.strftime('%H%M'),
                'fcstDate': '20260912', 'fcstTime': '1400', 'nx': 60, 'ny': 127,
                'category': 'PTY', 'fcstValue': '1'}]}}}}
        rows, count = parse_forecast_page(payload, (60, 127), issue)
        self.assertEqual(count, 1)
        save_forecast((60, 127), issue, rows)
        self.assertEqual(WeatherForecast.objects.get().issued_at, issue)
        with self.assertRaises(ExternalAPIError):
            parse_forecast_page(payload, (61, 127), issue)

    def test_job_dedupe_retry_and_expired_lease_recovery(self):
        job = enqueue('weather', '60:127', payload={'grid': (60, 127), 'issued_at': NOW.isoformat()}, window='fixed')
        self.assertEqual(enqueue('weather', '60:127', window='fixed').id, job.id)
        with patch('places.services.jobs._execute', side_effect=ExternalAPIError('fixture failure')):
            run_one()
        job.refresh_from_db()
        self.assertEqual(job.status, DataJob.Status.PENDING)
        self.assertEqual(job.attempts, 1)
        job.status = DataJob.Status.RUNNING
        job.leased_at = timezone.now() - timedelta(minutes=6)
        job.save()
        with patch('places.services.jobs._execute', return_value=False):
            run_one()
        job.refresh_from_db()
        self.assertEqual(job.status, DataJob.Status.SUCCEEDED)

    @patch.dict('os.environ', {'TOUR_API_DAILY_LIMIT': '0'})
    def test_budget_zero_stops_before_provider_call(self):
        enqueue('tour_places', 'nationwide', payload={'page_size': 1000, 'max_pages': 1}, window='fixed')
        with patch('places.integrations.tour_api.TourAPIClient') as client:
            job = run_one()
        self.assertEqual(job.status, DataJob.Status.PENDING)
        self.assertEqual(job.cursor, 1)
        client.return_value.fetch_places_page.assert_not_called()

    @patch.dict('os.environ', {'SEOUL_DAILY_LIMIT': '-1'})
    def test_seoul_without_daily_cap_still_counts_calls(self):
        debit('seoul', 'regular')
        debit('seoul', 'regular')
        self.assertEqual(ProviderCallBudget.objects.get(provider='seoul', lane='regular').used, 2)

    @patch.dict('os.environ', {'SEOUL_DAILY_LIMIT': '-1'})
    def test_seoul_job_collects_catalog_area_missing_from_database(self):
        record = SeoulPopulationRecord('POI066', '테스트 영역', NOW, 'relaxed', '',
                                       100, 200, False, {'AREA_CD': 'POI066'})
        enqueue('seoul_crowd', 'POI066', window='fixed')
        with patch('places.integrations.seoul_realtime.SeoulRealtimeClient') as client:
            client.return_value.fetch_population.return_value = record
            job = run_one()
        self.assertEqual((job.status, job.processed), (DataJob.Status.SUCCEEDED, 1))
        self.assertTrue(CrowdArea.objects.filter(external_id='POI066').exists())
        client.return_value.fetch_population.assert_called_once_with('POI066')

    @patch.dict('os.environ', {'TOUR_API_DAILY_LIMIT': '10'})
    def test_nationwide_page_cursor_and_budget_resume(self):
        records = [normalize_tour_place(dict(item)) for item in TOUR_PLACE_ITEMS[:2]]
        pages = [TourAPIPage([records[0]], 1, 1, 2), TourAPIPage([records[1]], 2, 1, 2)]
        job = enqueue('tour_places', 'nationwide', payload={'page_size': 1, 'max_pages': 2}, window='fixed')
        with patch('places.integrations.tour_api.TourAPIClient') as client:
            client.return_value.fetch_places_page.side_effect = pages
            run_one()
            job.refresh_from_db()
            self.assertEqual((job.status, job.cursor), (DataJob.Status.PENDING, 2))
            run_one()
        job.refresh_from_db()
        self.assertEqual(job.status, DataJob.Status.SUCCEEDED)
        self.assertEqual(client.return_value.fetch_places_page.call_args_list[1].kwargs['page_number'], 2)
        self.assertEqual(ProviderCallBudget.objects.get(provider='tour_api', lane='regular').used, 2)

    @patch.dict('os.environ', {'MVP_AUTO_TOUR_SYNC': 'true', 'TOUR_SYNC_MAX_PAGES': '3'})
    def test_sunday_scheduler_queues_bounded_nationwide_jobs(self):
        from places.management.commands.run_data_worker import Command
        sunday = datetime(2026, 9, 13, 5, 0, tzinfo=dt_timezone(timedelta(hours=9)))
        with patch('places.management.commands.run_data_worker.timezone.localtime', return_value=sunday):
            Command._schedule_dev()
        jobs = list(DataJob.objects.filter(kind='tour_places'))
        self.assertEqual(len(jobs), 2)
        self.assertEqual({job.payload['max_pages'] for job in jobs}, {3})
        self.assertEqual([job.payload.get('modified_since') for job in jobs if job.payload.get('modified_since')], ['20260912'])
