from collections import Counter
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from places.job_models import DataJob
from places.management.commands.run_data_worker import Command as WorkerCommand
from places.models import Place, PlaceSource
from places.services.pilot import CATEGORIES, select_pilot_cohort
from places.services.classification import classify_place
from places.services.jobs import _execute, enqueue


class PilotSelectionTests(TestCase):
    def test_cohort_is_balanced_and_chooses_nearby_source_deterministically(self):
        centers = {'11': (37.575, 126.977), '26': (35.160, 129.160),
                   '50': (33.500, 126.530)}
        for prefix, (lat, lon) in centers.items():
            for index, category in enumerate(CATEGORIES):
                for suffix, offset in (('near', 0.001), ('far', 0.4)):
                    place = Place.objects.create(
                        name=f'{prefix}-{index}-{suffix}', category=category,
                        region_code=f'{prefix}-001', address='공개 장소',
                        latitude=lat + offset, longitude=lon + offset,
                    )
                    PlaceSource.objects.create(
                        place=place, source='tour_api',
                        external_id=f'{prefix}-{index}-{suffix}',
                        match_status='matched', raw_data={'contenttypeid': '12'},
                        last_synced_at=timezone.now(),
                    )
        first = select_pilot_cohort(per_city=6)
        self.assertEqual(first, select_pilot_cohort(per_city=6))
        self.assertEqual(len(first), 18)
        self.assertEqual(Counter(row['city'] for row in first),
                         {'seoul': 6, 'busan': 6, 'jeju': 6})
        self.assertEqual(Counter(row['category'] for row in first),
                         {category: 3 for category in CATEGORIES})
        self.assertTrue(all(row['external_id'].endswith('-near') for row in first))

    def test_new_name_rules_keep_ambiguous_and_manual_places_unchanged(self):
        cases = (
            ('강변공원', '관광지', 'outdoor'),
            ('제주오름', '관광지', 'outdoor'),
            ('산속캠핑장', '레포츠', 'outdoor'),
            ('해오름', '음식점', 'unknown'),
            ('해변기념관', '관광지', 'unknown'),
            ('코엑스 아쿠아리움', '관광지', 'indoor'),
            ('노천극장', '문화시설', 'unknown'),
            ('자동차극장', '문화시설', 'unknown'),
        )
        for name, category, expected in cases:
            with self.subTest(name=name):
                place = Place.objects.create(name=name, category=category,
                    region_code='11', address='공개 장소', latitude=37.5, longitude=127)
                classify_place(place)
                place.refresh_from_db()
                self.assertEqual(place.indoor_outdoor, expected)
                if expected != 'unknown':
                    self.assertEqual(place.indoor_outdoor_source, 'reviewed_name_rule_v3')
        manual = Place.objects.create(name='해변공원', category='관광지',
            region_code='11', address='공개 장소', latitude=37.5, longitude=127,
            indoor_outdoor='mixed', indoor_outdoor_source='manual')
        self.assertFalse(classify_place(manual))
        manual.refresh_from_db()
        self.assertEqual((manual.indoor_outdoor, manual.indoor_outdoor_source), ('mixed', 'manual'))

    def test_screen_needs_its_own_description_not_a_parenthesized_museum_name(self):
        facade = Place.objects.create(name='K-컬처 스크린(대한민국역사박물관)', category='관광지',
            region_code='11', address='서울', latitude=37.575, longitude=126.977)
        other = Place.objects.create(name='K-컬처 스크린(다른박물관)', category='관광지',
            region_code='11', address='서울', latitude=37.575, longitude=126.978)
        self.assertFalse(classify_place(facade))
        self.assertFalse(classify_place(other))
        facade.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((facade.indoor_outdoor, facade.indoor_outdoor_source),
                         ('unknown', ''))
        self.assertEqual((other.indoor_outdoor, other.indoor_outdoor_source),
                         ('unknown', ''))

    def test_dev_scheduler_uses_fixed_pilot_manifest_and_daily_cap(self):
        place = Place.objects.create(name='시범 장소', category='관광지',
            region_code='11', address='공개 장소', latitude=37.5, longitude=127)
        PlaceSource.objects.create(place=place, source='tour_api', external_id='pilot-fixed',
            match_status='matched', raw_data={'contenttypeid': '12'},
            last_synced_at=timezone.now())
        manifest = json.dumps({'selection_version': 'pilot-1',
                               'entries': [{'external_id': 'pilot-fixed'}]})
        local = timezone.localtime().replace(hour=5, minute=0)
        with patch.dict('os.environ', {'PILOT_COHORT_MANIFEST': 'pilot.json',
                                    'PILOT_DETAIL_DAILY_PLACES': '1'}), \
             patch('places.management.commands.run_data_worker.load_seoul_crowd_catalog',
                   return_value=SimpleNamespace(areas=[])), \
             patch('places.management.commands.run_data_worker.timezone.localtime', return_value=local), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.read_text', return_value=manifest):
            WorkerCommand._schedule_dev()
            WorkerCommand._schedule_dev()
        self.assertEqual(DataJob.objects.filter(kind='tour_detail').count(), 1)


class TourDetailJobTests(TestCase):
    def test_common_only_detail_uses_one_budgeted_call(self):
        place = Place.objects.create(name='설명 수집 대상', category='관광지',
            region_code='11', address='서울', latitude=37.5, longitude=127)
        source = PlaceSource.objects.create(place=place, source='tour_api',
            external_id='common-only', match_status='matched',
            raw_data={'contenttypeid': '12'}, last_synced_at=timezone.now())
        job = enqueue('tour_detail', str(source.pk),
            payload={'source_id': source.pk, 'include_intro': False})

        with patch('places.integrations.tour_api.TourAPIClient'), \
             patch('places.services.jobs.debit') as debit, \
             patch('places.services.jobs.TourPlaceDetailSyncService') as service:
            service.return_value.sync.return_value = SimpleNamespace(processed=1)
            self.assertFalse(_execute(job))

        debit.assert_called_once_with('tour_api', 'regular')
        service.return_value.sync.assert_called_once()
        self.assertFalse(service.return_value.sync.call_args.kwargs['include_intro'])
        self.assertEqual(job.processed, 1)

    def test_default_detail_keeps_two_budgeted_calls(self):
        place = Place.objects.create(name='전체 상세 대상', category='관광지',
            region_code='11', address='서울', latitude=37.5, longitude=127)
        source = PlaceSource.objects.create(place=place, source='tour_api',
            external_id='common-and-intro', match_status='matched',
            raw_data={'contenttypeid': '12'}, last_synced_at=timezone.now())
        job = enqueue('tour_detail', str(source.pk), payload={'source_id': source.pk})

        with patch('places.integrations.tour_api.TourAPIClient'), \
             patch('places.services.jobs.debit') as debit, \
             patch('places.services.jobs.TourPlaceDetailSyncService') as service:
            service.return_value.sync.return_value = SimpleNamespace(processed=1)
            self.assertFalse(_execute(job))

        self.assertEqual(debit.call_count, 2)
        self.assertTrue(service.return_value.sync.call_args.kwargs['include_intro'])
