from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from places.models import (
    ExternalSource, Place, PlaceClassificationAttempt,
    PlaceClassificationEvidence, PlaceInfo, PlaceSource, PlaceWeatherExposure,
    WeatherForecast,
)
from places.services.classification import current_description_evidence
from places.services.description_classification import AI_PROMPT_VERSION, source_hash
from places.services.weather import grid_for
from places.services.weather_exposure import (
    POLICY_VERSION, derive_exposure, exposure_for, source_codes_for,
)
from recommendations.service import recommend


NOW = datetime(2026, 9, 14, 6, tzinfo=dt_timezone.utc)
CRITERIA = {'latitude': 37.575, 'longitude': 126.977,
            'radius_km': 10, 'limit': 10, 'crowd_level': 'any'}


def venue(name, code, *, label='unknown', source='', category='관광지',
          latitude=37.575, longitude=126.977):
    place = Place.objects.create(name=name, category=category, subcategory=code,
        region_code='11', address='서울', latitude=latitude, longitude=longitude,
        indoor_outdoor=label, indoor_outdoor_source=source)
    if code:
        PlaceSource.objects.create(place=place, source=ExternalSource.TOUR_API,
            external_id=f'test-{place.id}', match_status='matched',
            raw_data={'lclsSystm3': code}, last_synced_at=NOW)
    return place


class WeatherExposureTests(TestCase):
    def test_verified_type_is_weak_weather_prior_not_indoor_label(self):
        palace = venue('고궁', 'HS010100')
        profile = exposure_for(palace, source_codes_for([palace.id])[palace.id])
        self.assertEqual((profile.level, profile.source, profile.factor),
                         ('high', 'type_prior', .35))
        self.assertEqual(palace.indoor_outdoor, 'unknown')
        grid = grid_for(palace.latitude, palace.longitude)
        WeatherForecast.objects.create(grid_x=grid[0], grid_y=grid[1],
            issued_at=NOW - timedelta(hours=2), target_at=NOW,
            precipitation_type=1, temperature_c=20, wind_mps=2)
        result, _ = recommend(CRITERIA, now=NOW, supplement=False)
        item = result['items'][0]
        self.assertEqual(item['place']['weather_exposure']['source'], 'type_prior')
        self.assertIn('weather', item['score_contributors'])
        self.assertEqual(item['score_effective_breakdown']['weather'], 50)
        strict_weather, _ = recommend({**CRITERIA, 'weather_evidence_required': True},
                                      now=NOW, supplement=False)
        strict_indoor, _ = recommend({**CRITERIA, 'required_indoor_outdoor': 'indoor'},
                                     now=NOW, supplement=False)
        self.assertEqual(strict_weather['items'], [])
        self.assertEqual(strict_indoor['items'], [])

    def test_verified_codes_must_match_and_unmapped_types_remain_unknown(self):
        museum = venue('미술관', 'VE070600')
        self.assertEqual(derive_exposure(museum, ['VE070600']).level, 'low')
        self.assertEqual(derive_exposure(museum, ['VE070600', 'NA010100']).source,
                         'source_conflict')
        self.assertEqual(derive_exposure(museum, ['VE070300']).source,
                         'source_conflict')
        exhibition = venue('전시시설', 'VE070300')
        pool = venue('수영장', 'LS020700', category='레포츠')
        self.assertEqual(derive_exposure(exhibition, ['VE070300']).level, 'unknown')
        self.assertEqual(derive_exposure(pool, ['LS020700']).level, 'unknown')

    def test_inferred_name_type_conflict_abstains_but_manual_wins_audit_veto(self):
        inferred = venue('바다 도서관', 'NA010100', label='indoor',
                         source='reviewed_name_rule_v5', category='문화시설')
        inferred.indoor_outdoor_evidence = 'name:도서관'
        inferred.save(update_fields=['indoor_outdoor_evidence'])
        profile = derive_exposure(inferred, ['NA010100'])
        self.assertEqual((profile.level, profile.source, profile.factor),
                         ('unknown', 'inference_conflict', 0))
        manually_checked = venue('수동 실내', 'NA010100', label='indoor', source='manual')
        self.assertEqual(derive_exposure(manually_checked, ['NA010100'], veto=True).level,
                         'low')
        self.assertEqual(derive_exposure(manually_checked, ['NA010100'], veto=True).source,
                         'manual')
        self.assertEqual(derive_exposure(inferred, ['NA010100'], veto=True).source,
                         'audit_veto')

    def test_placeholder_invalidates_old_description_evidence(self):
        p = venue('임시 장소', '')
        description = ('개발용 상세정보입니다. 실제 운영에서는 TourAPI 상세정보로 갱신됩니다. '
                       '실내 사격장입니다.')
        PlaceInfo.objects.create(place=p, description=description)
        p.indoor_outdoor = 'indoor'
        p.indoor_outdoor_source = 'description_rule'
        p.save(update_fields=['indoor_outdoor', 'indoor_outdoor_source'])
        quote = '실내 사격장'
        start = description.index(quote)
        PlaceClassificationEvidence.objects.create(place=p, label='indoor',
            method='description_rule', version='description_v2',
            input_hash=source_hash(p.name, p.category, description,
                                   version='description_v2'),
            quote=quote, span_start=start, span_end=start + len(quote))
        self.assertIsNone(current_description_evidence(p))
        self.assertEqual(derive_exposure(p).level, 'unknown')

    def test_audit_veto_prevents_type_prior_resurrection(self):
        p = venue('검수 회수', 'VE070200')
        PlaceClassificationAttempt.objects.create(place=p, input_hash='a' * 64,
            model='gpt-5.6-luna', status='review_after_audit')
        self.assertEqual(derive_exposure(p, ['VE070200'], veto=True).source, 'audit_veto')

    def test_v4_explicit_unknown_is_not_revived_from_label_or_type(self):
        p = venue('바다 요트', 'LS020300', label='mixed', source='luna_validated',
                  category='레포츠')
        description = '요트의 선실에서 쉬고 야외 갑판에서 항해를 즐긴다.'
        PlaceInfo.objects.create(place=p, description=description)
        record = PlaceClassificationEvidence.objects.create(place=p, label='mixed',
            method='luna_validated', version=AI_PROMPT_VERSION,
            input_hash=source_hash(p.name, p.category, description,
                                   version=AI_PROMPT_VERSION),
            quote=description, span_start=0, span_end=len(description),
            evidence_quotes=[description], primary_activity='요트 항해',
            scope='principal_mixed', rationale='선실과 갑판을 함께 이용한다.',
            weather_exposure='unknown')
        self.assertIsNotNone(current_description_evidence(p))
        uncertain = derive_exposure(p, ['LS020300'])
        self.assertEqual((uncertain.level, uncertain.source, uncertain.factor),
                         ('unknown', 'luna_exposure_unknown', 0))
        record.weather_exposure = 'high'
        record.weather_activity = '요트 항해'
        record.weather_reason = '주된 항해는 바람과 비의 영향을 받는다.'
        record.save(update_fields=['weather_exposure', 'weather_activity', 'weather_reason'])
        direct = derive_exposure(p, ['LS020300'])
        self.assertEqual((direct.level, direct.source, direct.factor),
                         ('high', 'luna_exposure', .5))

    def test_offline_cli_is_idempotent_and_protects_manual_at_write(self):
        p = venue('고궁', 'HS010100')
        out = StringIO()
        call_command('build_weather_exposure_profiles', '--place-id', str(p.id),
                     stdout=out)
        self.assertFalse(PlaceWeatherExposure.objects.filter(place=p).exists())
        call_command('build_weather_exposure_profiles', '--place-id', str(p.id),
                     '--apply', stdout=StringIO())
        first = PlaceWeatherExposure.objects.get(place=p)
        self.assertEqual((first.level, first.version), ('high', POLICY_VERSION))
        first_time = first.classified_at
        call_command('build_weather_exposure_profiles', '--place-id', str(p.id),
                     '--apply', stdout=StringIO())
        first.refresh_from_db()
        self.assertEqual(first.classified_at, first_time)
        first.source = 'manual'
        first.level = 'low'
        first.save(update_fields=['source', 'level'])
        call_command('build_weather_exposure_profiles', '--place-id', str(p.id),
                     '--apply', stdout=StringIO())
        first.refresh_from_db()
        self.assertEqual((first.source, first.level), ('manual', 'low'))

    def test_offline_cli_rechecks_manual_profile_after_initial_scan(self):
        p = venue('고궁', 'HS010100')
        original = derive_exposure
        first_call = True

        def create_manual_during_scan(*args, **kwargs):
            nonlocal first_call
            result = original(*args, **kwargs)
            if first_call:
                first_call = False
                PlaceWeatherExposure.objects.create(place=p, level='low', source='manual',
                    reason='수동 확인', factor=1, version='manual', input_hash='')
            return result

        with patch('places.management.commands.build_weather_exposure_profiles.derive_exposure',
                   side_effect=create_manual_during_scan):
            call_command('build_weather_exposure_profiles', '--place-id', str(p.id),
                         '--apply', stdout=StringIO())
        stored = PlaceWeatherExposure.objects.get(place=p)
        self.assertEqual((stored.source, stored.level), ('manual', 'low'))

    def test_candidate_bulk_profile_lookup_has_bounded_query_count(self):
        places = [Place(name=f'공원 {i}', category='관광지', subcategory='VE030100',
            region_code='11', address='서울', latitude=37.575, longitude=126.977)
            for i in range(150)]
        Place.objects.bulk_create(places)
        place_ids = list(Place.objects.values_list('id', flat=True))
        PlaceSource.objects.bulk_create([PlaceSource(place_id=place_id,
            source=ExternalSource.TOUR_API, external_id=f'bulk-{place_id}',
            match_status='matched', raw_data={'lclsSystm3': 'VE030100'},
            last_synced_at=NOW) for place_id in place_ids])
        with CaptureQueriesContext(connection) as queries:
            result, _ = recommend(CRITERIA, now=NOW, supplement=False)
        self.assertEqual(result['candidate_count'], 150)
        self.assertLessEqual(len(queries), 10)
