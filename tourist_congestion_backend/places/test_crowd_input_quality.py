from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from places.models import Place, CrowdArea, PlaceCrowdArea, CrowdData, CollectorState
from places.services.crowd_inputs import load_inputs, estimates_for
from places.test_crowd_estimator import NOW


class InputQualityTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(name='test', latitude=37.57, longitude=126.97)
        self.area = CrowdArea.objects.create(name='area', source='seoul_realtime', external_id='POI008', last_synced_at=NOW)
        PlaceCrowdArea.objects.create(place=self.place, crowd_area=self.area, verified=True, is_primary=True)

    def observation(self, age=10, **kwargs):
        values = dict(crowd_area=self.area, observed_at=NOW-timedelta(minutes=age),
                      fetched_at=NOW-timedelta(minutes=1), population_min=70, population_max=80,
                      crowd_level='busy')
        values.update(kwargs)
        return CrowdData.objects.create(**values)

    def test_latest_unusable_never_masks_last_normal_observation(self):
        good = self.observation()
        self.observation(8, is_replaced=True)
        self.observation(6, raw_data={'dev_seed': True})
        self.observation(4, fetched_at=NOW+timedelta(minutes=10))
        self.observation(2, population_min=None, population_max=None)
        loaded = load_inputs([self.place], NOW)[self.place.pk]
        self.assertEqual(loaded['population']['observed_at'], good.observed_at)
        self.assertEqual(loaded['population']['fetched_at'], good.fetched_at)
        self.assertFalse(loaded['is_demo'])
        self.assertIsNone(load_inputs([self.place], NOW+timedelta(minutes=56))[self.place.pk]['population'])

    def test_null_received_time_uses_actual_creation_time(self):
        row = self.observation(fetched_at=None)
        CrowdData.objects.filter(pk=row.pk).update(created_at=NOW+timedelta(minutes=1))
        self.assertIsNone(load_inputs([self.place], NOW)[self.place.pk]['population'])
        CrowdData.objects.filter(pk=row.pk).update(created_at=NOW-timedelta(minutes=1))
        self.assertIsNotNone(load_inputs([self.place], NOW)[self.place.pk]['population'])

    def test_recalculation_does_not_restore_freshness(self):
        self.observation(age=20)
        first = estimates_for([self.place], NOW)[self.place.pk]
        later = estimates_for([self.place], NOW+timedelta(minutes=10))[self.place.pk]
        self.assertLess(later['confidence'], first['confidence'])
        self.assertEqual(later['data_as_of'], first['data_as_of'])

    def test_evaluation_cursor_cannot_disable_public_forecasts(self):
        before = estimates_for([self.place], NOW)[self.place.pk]
        CollectorState.objects.create(provider='system', key='evaluation', cursor={'disabled_horizons':[1,2,3]})
        after = estimates_for([self.place], NOW)[self.place.pk]
        self.assertEqual(before['forecast'], after['forecast'])

    @patch('requests.Session.request', side_effect=AssertionError('External request'))
    def test_mapped_batch_query_count_does_not_grow(self, _):
        self.observation()
        with CaptureQueriesContext(connection) as small:
            load_inputs([self.place], NOW)
        places = [self.place]
        for index in range(10):
            place = Place.objects.create(name=str(index), latitude=37.57, longitude=126.97)
            PlaceCrowdArea.objects.create(place=place, crowd_area=self.area, verified=True)
            places.append(place)
        with CaptureQueriesContext(connection) as large:
            result = load_inputs(places, NOW)
        self.assertEqual(len(small), len(large))
        self.assertTrue(all(value['population'] for value in result.values()))
