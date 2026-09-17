import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from places.models import DataJob, ExternalSource, Place, PlaceInfo, PlaceSource, ProviderCallBudget
from places.services.jobs import enqueue, run_one
from places.services.scheduling import schedule, schedule_tour
from places.services.weather import KST


class ProductionScheduleTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 15, 5, 0, tzinfo=KST)

    def source(self, number, *, old=False):
        place = Place.objects.create(name=f'박물관 {number}', category='문화시설',
            region_code='11', address='서울', latitude=37.56, longitude=126.97)
        if old:
            info = PlaceInfo.objects.create(place=place)
            PlaceInfo.objects.filter(pk=info.pk).update(updated_at=self.now-timedelta(days=8))
        return PlaceSource.objects.create(place=place, source=ExternalSource.TOUR_API,
            external_id=str(number), match_status='matched', raw_data={'contenttypeid': '14'},
            last_synced_at=self.now)

    def complete_list(self):
        job = enqueue('tour_places', 'previous', payload={'page_size': 1000, 'max_pages': 100})
        DataJob.objects.filter(pk=job.pk).update(status='succeeded',
            created_at=self.now-timedelta(days=3), finished_at=self.now-timedelta(days=3))

    @patch.dict(os.environ, {}, clear=True)
    def test_no_keys_does_not_queue_provider_calls(self):
        schedule(self.now)
        self.assertFalse(DataJob.objects.exists())

    @patch.dict(os.environ, {'TOUR_API_SERVICE_KEY': 'test-only', 'TOUR_API_DAILY_LIMIT': '1000'}, clear=True)
    def test_initial_full_load_is_deduplicated_and_blocks_details(self):
        with patch('django.utils.timezone.now', return_value=self.now):
            self.source(1)
            schedule(self.now)
            schedule(self.now)
        self.assertEqual(DataJob.objects.count(), 1)
        job = DataJob.objects.get()
        self.assertEqual(job.target_key, 'scheduled:full')
        self.assertEqual(job.payload['max_pages'], 100)
        self.assertNotIn('modified_since', job.payload)

    @patch.dict(os.environ, {'TOUR_DETAIL_DAILY_PLACES': '2'}, clear=True)
    def test_detail_daily_cap_includes_completed_jobs_and_refreshes_stale(self):
        with patch('django.utils.timezone.now', return_value=self.now):
            self.complete_list()
            for i in range(5):
                self.source(i, old=True)
            schedule_tour(self.now)
            details = DataJob.objects.filter(kind='tour_detail')
            self.assertEqual(details.count(), 2)
            details.update(status='succeeded')
            schedule_tour(self.now)
            self.assertEqual(details.count(), 2)

    @patch.dict(os.environ, {}, clear=True)
    def test_missed_daily_increment_uses_last_success_start(self):
        with patch('django.utils.timezone.now', return_value=self.now):
            self.complete_list()
            schedule_tour(self.now)
        job = DataJob.objects.get(target_key='scheduled:changes')
        self.assertEqual(job.payload['modified_since'], '20260911')

    @patch.dict(os.environ, {}, clear=True)
    def test_sunday_full_scan_is_not_suppressed_by_daily_increment(self):
        sunday = datetime(2026, 9, 20, 3, 0, tzinfo=KST)
        with patch('django.utils.timezone.now', return_value=sunday):
            self.complete_list()
            schedule_tour(sunday)
            DataJob.objects.filter(target_key='scheduled:changes').update(status='succeeded', finished_at=sunday)
            schedule_tour(sunday.replace(hour=4))
            schedule_tour(sunday.replace(hour=4))
        self.assertEqual(DataJob.objects.filter(target_key='scheduled:full').count(), 1)

    @patch.dict(os.environ, {'SEOUL_OPEN_API_KEY': 'test-only', 'SEOUL_DAILY_LIMIT': '18000'}, clear=True)
    def test_seoul_windows_have_exactly_121_jobs_each(self):
        with patch('django.utils.timezone.now', return_value=self.now):
            schedule(self.now)
            schedule(self.now)
            self.assertEqual(DataJob.objects.count(), 121)
            schedule(self.now+timedelta(minutes=15))
            self.assertEqual(DataJob.objects.count(), 242)

    @patch.dict(os.environ, {'KMA_SERVICE_KEY': 'test-only', 'KMA_DAILY_LIMIT': '10000'}, clear=True)
    def test_weather_bootstraps_public_city_grids_without_user_requests(self):
        with patch('django.utils.timezone.now', return_value=self.now):
            schedule(self.now)
            schedule(self.now)
        self.assertEqual(DataJob.objects.filter(kind='weather').count(), 7)


class ProductionJobTests(TestCase):
    @patch.dict(os.environ, {'TOUR_API_DAILY_LIMIT': '1000'}, clear=True)
    def test_page_cap_is_failure_not_false_full_sync_success(self):
        page = SimpleNamespace(records=[SimpleNamespace(category='숙박')], has_next=True)
        with patch('places.integrations.tour_api.TourAPIClient') as client:
            client.return_value.fetch_places_page.return_value = page
            enqueue('tour_places', 'full', payload={'page_size': 1000, 'max_pages': 1})
            job = run_one()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error_code, 'PageLimitExceeded')
        self.assertEqual(ProviderCallBudget.objects.get().used, 1)

    def test_expired_crowd_does_not_consume_next_day_budget(self):
        job = enqueue('seoul_crowd', 'POI001')
        DataJob.objects.filter(pk=job.pk).update(created_at=timezone.now()-timedelta(minutes=16))
        with patch('places.services.jobs._execute') as execute:
            self.assertIsNone(run_one())
        execute.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.error_code, 'ExpiredWindow')
