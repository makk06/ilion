from unittest.mock import patch

from django.db import OperationalError, connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from places.models import Place, PlaceSource


class CrowdAPITests(TestCase):
    def setUp(self):
        self.place=Place.objects.create(name='해운대',latitude=35.16,longitude=129.16,category='관광지',region_code='26',address='부산')

    @patch('requests.Session.request',side_effect=AssertionError('API view made external request'))
    def test_nationwide_contract_and_query_count_is_bounded(self,_):
        response=self.client.get(f'/api/places/{self.place.pk}/crowd')
        self.assertEqual(response.status_code,200)
        data=response.json()['data']; self.assertEqual(data['tier'],'C')
        self.assertIsNone(data['estimated_visitors']); self.assertEqual(len(data['forecast']),3)
        with CaptureQueriesContext(connection) as small:
            self.client.get('/api/places')
        Place.objects.bulk_create([Place(name=f'p{i}',latitude=35,longitude=129,category='관광지',region_code='26',address='부산') for i in range(19)])
        with CaptureQueriesContext(connection) as large:
            response=self.client.get('/api/places')
        self.assertEqual(len(small),len(large)); self.assertLessEqual(len(large),15)
        self.assertIsNotNone(response.json()['data']['items'][0]['crowd_estimate'])

    def test_filter_before_pagination_legacy_conflict_and_inactive(self):
        result=self.client.get(f'/api/places/{self.place.pk}/crowd').json()['data']
        response=self.client.get('/api/places',{'estimate_level':result['crowd_level'],'page_size':1})
        self.assertEqual(response.status_code,200); self.assertEqual(response.json()['data']['pagination']['total'],1)
        self.assertEqual(self.client.get('/api/places',{'estimate_level':'LOW','crowd_level':'relaxed'}).status_code,400)
        PlaceSource.objects.create(place=self.place,source='tour_api',external_id='1',match_status='inactive',last_synced_at=timezone.now())
        self.assertEqual(self.client.get(f'/api/places/{self.place.pk}/crowd').status_code,404)

    def test_database_failure_is_503(self):
        with patch('places.views.estimates_for',side_effect=OperationalError('locked')):
            self.assertEqual(self.client.get(f'/api/places/{self.place.pk}/crowd').status_code,503)

    @override_settings(CROWD_ESTIMATION_ENABLED=False)
    def test_feature_switch_preserves_old_response(self):
        data=self.client.get(f'/api/places/{self.place.pk}').json()['data']
        self.assertNotIn('crowd_estimate',data); self.assertIn('latest_crowd',data)
