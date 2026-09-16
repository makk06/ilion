import json
import os
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
import requests

from places.job_models import ProviderCallBudget
from places.models import Place, PlaceClassificationAttempt, PlaceClassificationEvidence, PlaceInfo
from places.services.classification import classify_place
from places.services.description_classification import (
    AI_PROMPT_VERSION, LEGACY_AI_PROMPT_VERSION, classify_description,
    is_placeholder_description, normalized_description, source_hash,
    validate_ai_decision, validate_contextual_ai_proposal,
    validate_weather_ai_proposal,
)
from places.services.luna_classification import (
    MODEL, _parse_response, classify_with_luna, promote_reviewed_proposal,
)
from recommendations.service import _classification_quality, recommend


NOW = datetime(2026, 9, 14, 6, tzinfo=dt_timezone.utc)
CRITERIA = {'latitude': 37.5665, 'longitude': 126.978, 'radius_km': 10,
            'crowd_level': 'any', 'limit': 10}


def place(name='테스트 장소', label='unknown', source='', category='관광지'):
    return Place.objects.create(name=name, category=category, region_code='11',
        address='테스트 주소', latitude=37.5665, longitude=126.978,
        indoor_outdoor=label, indoor_outdoor_source=source)


class DescriptionRuleTests(SimpleTestCase):
    def classify(self, name, description):
        decision = classify_description(name, '관광지', description)
        return decision.label if decision else None

    def test_frozen_examples_and_conflicts(self):
        self.assertEqual(self.classify('놀이마루', '실내와 실외 모두를 아우르는 활동 공간이다.'), 'mixed')
        self.assertEqual(self.classify('요트투어', '실내 휴식공간과 야외 데크에서 감상한다.'), 'mixed')
        self.assertEqual(self.classify('제주교육박물관', '상설 전시장과 기획 및 체험전시실, 야외전시장으로 구성된다.'), 'mixed')
        self.assertEqual(self.classify('슈터스클럽', '실내 사격장이다.'), 'indoor')
        self.assertEqual(self.classify('싱싱뽈락회', '해수욕장 근처에 있다. 넓은 실내 공간에서 회를 즐긴다.'), 'indoor')
        self.assertEqual(self.classify('남포동 지하도상가', '쾌적한 지하상가이다.'), 'indoor')
        self.assertEqual(self.classify('서울광장 스케이트장', '겨울철 야외 스케이트장이다. 도서관이 인접한다.'), 'outdoor')
        self.assertIsNone(self.classify('서울도서관', '도서관이다. 야외도서관은 근처 광장에 있다.'))
        self.assertIsNone(self.classify('카페', '실내 공간에서 먹는다. 야외 테이블도 있다.'))
        self.assertIsNone(self.classify('박물관', '야외전시장을 둘러볼 수 있다.'))
        self.assertIsNone(self.classify('시장', '남포지하상가와 협력했다.'))
        self.assertIsNone(self.classify('체험장', '실내 체험장은 과거에 폐쇄되었다.'))

    def test_quote_is_exact_normalized_source_span(self):
        text = '<b>실내 사격장</b>이다.  방문 가능'
        decision = classify_description('사격장', '레포츠', text)
        normalized = normalized_description(text)
        self.assertEqual(normalized[decision.span_start:decision.span_end], decision.quote)

    def test_placeholder_is_not_description_evidence(self):
        description = '경복궁의 개발용 상세정보입니다. 실제 운영에서는 TourAPI 상세정보로 갱신됩니다.'
        self.assertTrue(is_placeholder_description(description))
        self.assertIsNone(classify_description('경복궁', '관광지', description))

    def test_gate_requires_palace_context_and_is_not_an_indoor_replica(self):
        self.assertEqual(self.classify('정화문', '정화문은 옛 궁궐의 정문으로 길에 서 있다.'), 'outdoor')
        self.assertNotEqual(self.classify('정화문',
            '정화문은 박물관 실내 전시실에 설치한 옛 궁궐 정문의 모형이다.'),
            'outdoor')
        self.assertIsNone(self.classify('정화문', '정화문은 전시관의 출입문이다.'))

    def test_contextual_ai_scope_and_quote_validation(self):
        desc = '공원 근처의 건물 2층 공연장에서 연극을 관람한다.'
        proposal = {'label': 'indoor', 'primary_activity': '공연 관람',
                    'evidence_quotes': [desc], 'scope': 'principal_place',
                    'ancillary_note': '공원은 위치 정보',
                    'rationale': '주된 연극 관람이 건물 2층 공연장에서 이뤄진다.'}
        decision, reason, safe = validate_contextual_ai_proposal(
            '작은 공연장', '문화시설', desc, proposal)
        self.assertEqual((decision.label, reason), ('indoor', ''))
        self.assertEqual(safe['evidence_quotes'], [desc])
        with_outdoor_word = '야외 공원 근처의 건물 2층 공연장에서 연극을 관람한다.'
        decision, reason, _ = validate_contextual_ai_proposal(
            '작은 공연장', '문화시설', with_outdoor_word,
            {**proposal, 'evidence_quotes': [with_outdoor_word]})
        self.assertEqual((decision.label, reason), ('indoor', ''))
        rejected, why, _ = validate_contextual_ai_proposal(
            '작은 공연장', '문화시설', desc,
            {**proposal, 'scope': 'principal_mixed'})
        self.assertIsNone(rejected)
        self.assertEqual(why, 'inconsistent_scope')
        for bad_desc, bad_quote in (
            ('실내 공간이 없다.', '실내 공간이 없다.'),
            ('다른 박물관의 실내 전시실이다.', '다른 박물관의 실내 전시실이다.'),
        ):
            rejected, why, _ = validate_contextual_ai_proposal(
                '작은 공연장', '문화시설', bad_desc,
                {**proposal, 'evidence_quotes': [bad_quote]})
            self.assertIsNone(rejected)
            self.assertEqual(why, 'unsafe_quote_context')
        rejected, why, _ = validate_contextual_ai_proposal(
            '작은 공연장', '문화시설', desc,
            {**proposal, 'evidence_quotes': ['없는 인용문']})
        self.assertEqual(why, 'quote_not_in_source')
        self.assertIsNone(rejected)

    def test_v4_ai_weather_exposure_is_direct_but_not_verified(self):
        desc = '요트의 선실에서 쉬고 야외 갑판에서 항해를 즐긴다.'
        proposal = {'label': 'mixed', 'primary_activity': '요트 항해',
                    'evidence_quotes': [desc], 'scope': 'principal_mixed',
                    'ancillary_note': '', 'rationale': '선실과 갑판을 함께 이용한다.',
                    'weather_exposure': 'high', 'exposure_activity': '요트 항해',
                    'exposure_reason': '주된 항해는 바람과 비의 영향을 받는다.'}
        decision, reason, safe = validate_weather_ai_proposal(
            '바다 요트', '레포츠', desc, proposal)
        self.assertEqual((decision.label, decision.weather_exposure, reason),
                         ('mixed', 'high', ''))
        self.assertEqual(safe['evidence_quotes'], [desc])
        invalid, reason, _ = validate_weather_ai_proposal(
            '바다 요트', '레포츠', desc,
            {**proposal, 'weather_exposure': 'very_high'})
        self.assertIsNone(invalid)
        self.assertEqual(reason, 'invalid_exposure_field')
        invalid, reason, _ = validate_weather_ai_proposal(
            '바다 요트', '레포츠', desc,
            {**proposal, 'weather_exposure': ['high']})
        self.assertIsNone(invalid)
        self.assertEqual(reason, 'invalid_exposure_field')

    def test_ai_quote_validation_is_not_rule_identity(self):
        desc = '건물 내부에서 관람하는 장소다.'
        self.assertIsNone(classify_description('체험관', '관광지', desc))
        decision = validate_ai_decision('체험관', '관광지', desc,
            label='indoor', quote='건물 내부에서 관람하는 장소다', scope='principal_place')
        self.assertEqual(decision.label, 'indoor')
        self.assertIsNone(validate_ai_decision('체험관', '관광지', desc,
            label='indoor', quote='건물 안에서 관람', scope='principal_place'))
        self.assertIsNone(validate_ai_decision('체험관', '관광지', '실내 공간과 야외 테이블이 있다.',
            label='indoor', quote='실내 공간', scope='principal_place'))
        self.assertIsNone(validate_ai_decision('체험관', '관광지', '근처 박물관은 실내 공간이다.',
            label='indoor', quote='실내 공간', scope='other_place'))
        self.assertIsNone(validate_ai_decision('홍리실내수영장', '레포츠',
            '홍리실내수영장은 수영 교육 장소다.', label='indoor',
            quote='홍리실내수영장', scope='principal_place'))
        self.assertIsNone(validate_ai_decision('홍리실내수영장', '레포츠',
            '홍리실내수영장은 수영 교육 장소다.', label='indoor',
            quote='실내수영장', scope='principal_place'))
        self.assertEqual(validate_ai_decision('식당', '음식점',
            '야외 테이블에서 먹는다. 내부 공간에서 먹는다.', label='mixed',
            quote='야외 테이블에서 먹는다. 내부 공간에서 먹는다.',
            scope='principal_place').label, 'mixed')


@override_settings(RECOMMENDATION_CONTEXT_CACHE_SECONDS=0)
class DescriptionPersistenceTests(TestCase):
    def test_rule_reclassifies_name_and_stale_input_becomes_inactive(self):
        p = place('제주교육박물관', 'indoor', 'reviewed_name_rule_v2')
        info = PlaceInfo.objects.create(place=p,
            description='상설 전시장과 체험전시실, 야외전시장으로 구성된다.')
        self.assertTrue(classify_place(p, info))
        p.refresh_from_db()
        self.assertEqual((p.indoor_outdoor, p.indoor_outdoor_source), ('mixed', 'description_rule'))
        record = PlaceClassificationEvidence.objects.get(place=p)
        self.assertEqual(_classification_quality(p)[0], 'inferred_from_description')
        self.assertEqual(record.quote, info.description[record.span_start:record.span_end])
        info.description = '설명을 수정했다.'
        info.save()
        p.refresh_from_db()
        self.assertEqual(_classification_quality(p)[0], 'stale_auto_evidence')
        strict, _ = recommend({**CRITERIA, 'required_indoor_outdoor': 'mixed'},
                              now=NOW, supplement=False)
        self.assertEqual(strict['items'], [])
        classify_place(p, info)
        p.refresh_from_db()
        self.assertEqual((p.indoor_outdoor, p.indoor_outdoor_source),
                         ('indoor', 'reviewed_name_rule_v5'))
        self.assertFalse(PlaceClassificationEvidence.objects.filter(place=p).exists())

    def test_manual_is_protected_and_description_arrival_reclassifies_unknown(self):
        manual = place('수동', 'outdoor', 'manual')
        info = PlaceInfo.objects.create(place=manual, description='실내 사격장이다.')
        self.assertFalse(classify_place(manual, info))
        manual.refresh_from_db()
        self.assertEqual(manual.indoor_outdoor, 'outdoor')
        unknown = place('슈터스클럽')
        self.assertFalse(classify_place(unknown))
        detail = PlaceInfo.objects.create(place=unknown, description='도심의 실내 사격장이다.')
        self.assertTrue(classify_place(unknown, detail))
        unknown.refresh_from_db()
        self.assertEqual(unknown.indoor_outdoor, 'indoor')
        strict, _ = recommend({**CRITERIA, 'required_indoor_outdoor': 'indoor'},
                              now=NOW, supplement=False)
        self.assertEqual([i['place']['id'] for i in strict['items']], [unknown.id])

    def test_name_rule_and_mixed_do_not_satisfy_required_indoor(self):
        named = place('우리동네 도서관', 'indoor', 'reviewed_name_rule_v2')
        mixed = place('복합시설', 'mixed', 'manual')
        strict, _ = recommend({**CRITERIA, 'required_indoor_outdoor': 'indoor'},
                              now=NOW, supplement=False)
        self.assertNotIn(named.id, [i['place']['id'] for i in strict['items']])
        self.assertNotIn(mixed.id, [i['place']['id'] for i in strict['items']])

    def test_dryrun_does_not_mutate_and_apply_is_idempotent(self):
        p = place('사격장')
        PlaceInfo.objects.create(place=p, description='실내 사격장이다.')
        call_command('classify_place_descriptions', '--limit', '1')
        p.refresh_from_db()
        self.assertEqual(p.indoor_outdoor, 'unknown')
        call_command('classify_place_descriptions', '--limit', '1', '--apply')
        digest = PlaceClassificationEvidence.objects.get(place=p).input_hash
        call_command('classify_place_descriptions', '--limit', '1', '--apply')
        self.assertEqual(PlaceClassificationEvidence.objects.get(place=p).input_hash, digest)
        self.assertEqual(PlaceClassificationEvidence.objects.count(), 1)


@override_settings(RECOMMENDATION_CONTEXT_CACHE_SECONDS=0)
class LunaOfflineTests(TestCase):
    class Response:
        status_code = 200

        def json(self):
            return {'status': 'completed', 'usage': {'input_tokens': 50, 'output_tokens': 20},
                    'output': [{'content': [{'type': 'output_text', 'text': json.dumps({
                        'label': 'indoor', 'primary_activity': '실내 관람',
                        'evidence_quotes': ['건물 내부에서 관람하는 장소'],
                        'scope': 'principal_place', 'ancillary_note': '',
                        'rationale': '방문 활동이 건물 내부 관람이다.',
                        'weather_exposure': 'low',
                        'exposure_activity': '건물 내부 관람',
                        'exposure_reason': '주된 관람 공간이 건물 내부이다.',
                    })}]}]}

    def test_opt_in_mock_only_once_and_strict_rejects_ai(self):
        p = place('체험관')
        PlaceInfo.objects.create(place=p, description='건물 내부에서 관람하는 장소다.')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'mock-only'}):
            with patch('places.services.luna_classification.requests.post',
                       return_value=self.Response()) as post:
                self.assertEqual(classify_with_luna(p.id), 'validated')
                self.assertEqual(classify_with_luna(p.id), 'already_attempted')
        post.assert_called_once()
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], MODEL)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['reasoning']['effort'], 'none')
        p.refresh_from_db()
        self.assertEqual(_classification_quality(p)[0], 'inferred_from_luna')
        self.assertEqual(PlaceClassificationAttempt.objects.count(), 1)
        attempt = PlaceClassificationAttempt.objects.get()
        self.assertEqual(attempt.proposal['primary_activity'], '실내 관람')
        self.assertEqual(PlaceClassificationEvidence.objects.get(place=p).version,
                         AI_PROMPT_VERSION)
        self.assertEqual(PlaceClassificationEvidence.objects.get(place=p).previous_label,
                         'unknown')
        self.assertEqual(ProviderCallBudget.objects.get(provider='openai_luna').used, 1)
        strict, _ = recommend({**CRITERIA, 'required_indoor_outdoor': 'indoor'},
                              now=NOW, supplement=False)
        self.assertEqual(strict['items'], [])

    def test_invalid_output_and_refusal_fail_closed(self):
        for value in (None, [], {'status': 'completed', 'output': [None]},
                      {'status': 'incomplete', 'output': []},
                      {'status': 'completed', 'output': [{'content': [{'type': 'refusal'}]}]}):
            parsed, error = _parse_response(value)
            self.assertIsNone(parsed)
            self.assertTrue(error)
        p = place('체험관')
        PlaceInfo.objects.create(place=p, description='건물 내부에서 관람하는 장소다.')
        class Refused:
            status_code = 200
            def json(self):
                return {'status': 'completed', 'usage': {'input_tokens': 'bad'},
                        'output': [{'content': [{'type': 'refusal'}]}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'mock-only'}):
            with patch('places.services.luna_classification.requests.post', return_value=Refused()):
                self.assertEqual(classify_with_luna(p.id), 'failed')
        self.assertEqual(PlaceClassificationAttempt.objects.get().input_tokens, 0)
        p.refresh_from_db()
        self.assertEqual(p.indoor_outdoor, 'unknown')

    def test_public_recommend_never_calls_luna(self):
        p = place('체험관')
        PlaceInfo.objects.create(place=p, description='건물 내부에서 관람하는 장소다.')
        with patch('places.services.luna_classification.classify_with_luna') as ai:
            recommend(CRITERIA, now=NOW, supplement=False)
            response = self.client.post('/api/recommendations', data={
                'latitude': 37.5665, 'longitude': 126.978, 'radius_km': 10,
            }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        ai.assert_not_called()

    def test_daily_cap_rolls_back_reservation_without_network(self):
        p = place('체험관')
        PlaceInfo.objects.create(place=p, description='건물 내부에서 관람하는 장소다.')
        ProviderCallBudget.objects.create(provider='openai_luna',
            date=timezone.localdate(), lane='classification', used=20)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'mock-only'}):
            with patch('places.services.luna_classification.requests.post') as post:
                self.assertEqual(classify_with_luna(p.id), 'daily_cap')
        post.assert_not_called()
        self.assertFalse(PlaceClassificationAttempt.objects.exists())
        self.assertEqual(ProviderCallBudget.objects.get(provider='openai_luna').used, 20)

    def test_timeout_is_recorded_once_without_replacing_old_label(self):
        p = place('체험관', 'indoor', 'reviewed_name_rule_v2')
        PlaceInfo.objects.create(place=p, description='건물 내부에서 관람하는 장소다.')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'mock-only'}):
            with patch('places.services.luna_classification.requests.post',
                       side_effect=requests.Timeout) as post:
                self.assertEqual(classify_with_luna(p.id), 'failed')
                self.assertEqual(classify_with_luna(p.id), 'already_attempted')
        post.assert_called_once()
        p.refresh_from_db()
        self.assertEqual((p.indoor_outdoor, p.indoor_outdoor_source),
                         ('indoor', 'reviewed_name_rule_v2'))
        self.assertEqual(PlaceClassificationAttempt.objects.get().error_code,
                         'transport_or_parse_error')

    def test_reviewed_proposal_can_be_promoted_only_with_same_input_and_quote(self):
        p = place('식당', category='음식점')
        info = PlaceInfo.objects.create(place=p,
            description='야외 테이블에서 먹는다. 건물 내부에서 먹는다.')
        # Direct validation now accepts the principal-place mixed scope. Seed
        # an old review attempt to exercise the no-network promotion path.
        digest = source_hash(p.name, p.category, info.description,
                             version=LEGACY_AI_PROMPT_VERSION)
        PlaceClassificationAttempt.objects.create(place=p, input_hash=digest,
            model=MODEL, status='review', error_code='invalid_evidence')
        self.assertEqual(promote_reviewed_proposal(p.id, label='mixed',
            quote=info.description, scope='principal_place'), 'validated_after_review')
        self.assertEqual(promote_reviewed_proposal(p.id, label='mixed',
            quote=info.description, scope='principal_place'), 'not_eligible')
        info.description = '입력이 바뀌었다.'
        info.save()
        p.refresh_from_db()
        self.assertEqual(_classification_quality(p)[0], 'stale_auto_evidence')
