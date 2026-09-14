"""Visitor weather exposure, separate from the indoor/outdoor compatibility label.

TourAPI's official class names identify a venue *type*, not measured weather
exposure. This registry is our deliberately weak, versioned ranking policy.
"""

import hashlib
import json
from dataclasses import dataclass, replace

from places.models import ExternalSource, PlaceClassificationAttempt, PlaceSource
from places.services.classification import current_description_evidence, name_decision
from places.services.description_classification import normalized_description
from places.services.description_classification import AI_PROMPT_VERSION


POLICY_VERSION = 'weather_exposure_v1'
TYPE_PRIOR_FACTOR = 0.35

# Exact official TourAPI lclsSystm3 codes or wholly weather-exposed families.
# Omitted types (food, markets, generic halls, swimming, caves, mixed-use)
# remain unknown until venue-specific evidence is available.
TYPE_POLICY = {
    'HS010100': ('high', '궁궐 부지 관람', '고궁'),
    'HS010200': ('high', '성곽·산성 관람', '성ㆍ산성ㆍ성곽'),
    'HS010300': ('high', '성문 관람', '문'),
    'HS020100': ('high', '기념탑·비석 관람', '탑ㆍ비석ㆍ기념탑'),
    'VE010300': ('high', '다리 관람', '다리 / 대교'),
    'VE010400': ('high', '분수 관람', '분수'),
    'VE010500': ('high', '동상 관람', '동상'),
    'VE010800': ('high', '등대 관람', '등대'),
    'VE020400': ('low', '수족관 관람', '수족관 / 아쿠라리움'),
    'VE060200': ('low', '영화 관람', '영화관'),
    'VE070100': ('low', '박물관 관람', '박물관'),
    'VE070200': ('low', '기념관 관람', '기념관'),
    'VE070400': ('low', '컨벤션 시설 이용', '컨벤션센터'),
    'VE070500': ('low', '과학관 관람', '과학관'),
    'VE070600': ('low', '미술관·화랑 관람', '미술관/화랑'),
    'AC050100': ('high', '야영', '일반야영장'),
    'AC050200': ('high', '오토캠핑', '오토캠핑장'),
    'AC050300': ('medium', '카라반 숙박과 야외 활동', '카라반'),
    'AC050400': ('medium', '글램핑 숙박과 야외 활동', '글램핑장'),
    'LS010200': ('high', '자전거 하이킹', '자전거하이킹'),
    'LS010700': ('high', '승마', '승마'),
    'LS010800': ('high', '스키·스노보드', '스키/스노보드'),
    'LS011500': ('high', 'ATV 주행', 'ATV'),
    'LS011600': ('high', 'MTB 주행', 'MTB'),
    'LS011700': ('high', '오프로드 활동', '오프로드'),
    'LS011800': ('high', '번지점프', '번지점프'),
}
TYPE_FAMILIES = {
    'NA01': ('high', '산·숲·폭포·계곡 방문', '자연경관(산)'),
    'NA02': ('high', '하천·해양 경관 방문', '자연경관(하천‧해양)'),
    'NA04': ('high', '자연공원 방문', '자연공원'),
    'VE03': ('high', '도시공원 이용', '도시공원'),
}
# Only the live-verified LS02 leaf codes are eligible. Swimming is omitted
# because the official type includes both indoor and outdoor pools.
WATER_ACTIVITY_CODES = {
    'LS020100', 'LS020200', 'LS020300', 'LS020400', 'LS020500',
    'LS020600', 'LS020800', 'LS020900', 'LS021000', 'LS021100',
    'LS021200', 'LS021300', 'LS021400',
}
WEATHER_SENSITIVE_MIXED_CODES = {'LS020300', 'AC050100', 'AC050200'}


@dataclass(frozen=True)
class WeatherExposure:
    level: str = 'unknown'
    activity: str = ''
    source: str = 'unavailable'
    reason: str = '주된 방문 활동의 날씨 노출 근거가 없습니다.'
    conflict: bool = False
    conflict_reason: str = ''
    type_code: str = ''
    type_name: str = ''
    factor: float = 0.0
    input_hash: str = ''
    persisted: bool = False

    def as_dict(self):
        return {'level': self.level, 'activity': self.activity,
                'source': self.source, 'reason': self.reason,
                'conflict': self.conflict, 'conflict_reason': self.conflict_reason or None,
                'type_code': self.type_code or None, 'type_name': self.type_name or None,
                'weight_factor': self.factor, 'policy_version': POLICY_VERSION,
                'persisted': self.persisted}


def source_codes_for(place_ids):
    """One bounded query for all candidates; never a per-place source lookup."""
    result = {}
    for place_id, raw in PlaceSource.objects.filter(
        place_id__in=place_ids, source=ExternalSource.TOUR_API,
        match_status=PlaceSource.MatchStatus.MATCHED,
    ).values_list('place_id', 'raw_data'):
        raw = raw if isinstance(raw, dict) else {}
        code = str(raw.get('lclsSystm3') or raw.get('lclssystm3') or '').strip()
        result.setdefault(place_id, []).append(code)
    return result


def _verified_type(place, codes):
    distinct = set(codes or [])
    if not distinct:
        return '', '', False
    if len(distinct) != 1 or '' in distinct or place.subcategory not in distinct:
        return '', '', True
    code = distinct.pop()
    entry = TYPE_POLICY.get(code)
    if entry is None:
        entry = TYPE_FAMILIES.get(code[:4])
    if entry is None and code in WATER_ACTIVITY_CODES:
        entry = ('high', '수상 레저 활동', '수상레저스포츠')
    return code, entry, False


def _compatible_exposure(place):
    """Only current, provenance-checked labels may inform weather exposure."""
    label = place.indoor_outdoor
    source = place.indoor_outdoor_source
    if label not in {'indoor', 'outdoor', 'mixed'}:
        return None
    if source == 'manual':
        return label, 'manual', 1.0, '수동 분류'
    if source in {'description_rule', 'luna_validated'}:
        record = current_description_evidence(place)
        if record is None:
            return None
        factor = 0.75 if source == 'description_rule' else 0.5
        activity = record.primary_activity or '공개 설명의 방문 공간'
        return label, source, factor, activity
    if source.startswith('reviewed_name_rule_'):
        decision = name_decision(place)
        if decision and decision[0] == label and (
            decision[1] == source or
            (source == 'reviewed_name_rule_v1' and decision[2] == place.indoor_outdoor_evidence) or
            (source == 'reviewed_name_rule_v2' and decision[1] == 'reviewed_name_rule_v5' and
             decision[2] == place.indoor_outdoor_evidence)
        ):
            return label, 'name_rule', 0.5, '장소명에서 추정한 방문 공간'
    return None


def _digest(place, codes, veto):
    try:
        description = normalized_description(place.info.description)
    except AttributeError:
        description = ''
    evidence_hash = ''
    try:
        evidence_hash = place.classification_record.input_hash
    except AttributeError:
        pass
    material = [POLICY_VERSION, place.name, place.category, place.subcategory,
                sorted(codes or []), place.indoor_outdoor, place.indoor_outdoor_source,
                place.indoor_outdoor_evidence, evidence_hash, description, veto]
    return hashlib.sha256(json.dumps(material, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def derive_exposure(place, codes=(), *, veto=False):
    """No writes. Type is a low-weight prior; explicit current evidence wins."""
    digest = _digest(place, codes, veto)
    explicit = _compatible_exposure(place)
    if veto and (not explicit or explicit[1] != 'manual'):
        return WeatherExposure(source='audit_veto',
            reason='이 장소의 자동 날씨 노출 판정은 검수 후 운영에서 제외됐습니다.',
            input_hash=digest)
    code, entry, source_conflict = _verified_type(place, codes)
    type_level, type_activity, type_name = entry if entry else ('unknown', '', '')
    if explicit:
        label, source, factor, activity = explicit
        if source == 'luna_validated':
            record = current_description_evidence(place)
            if record and record.version == AI_PROMPT_VERSION and record.weather_exposure == 'unknown':
                return WeatherExposure(source='luna_exposure_unknown',
                    reason='AI가 주된 활동의 날씨 노출을 판정하지 못해 점수를 유보합니다.',
                    type_code=code, type_name=type_name, input_hash=digest)
            if record and record.weather_exposure in {'high', 'medium', 'low'}:
                level = record.weather_exposure
                direct_activity = record.weather_activity or activity
                conflict = source_conflict or (type_level not in {'unknown', level})
                return WeatherExposure(level, direct_activity, 'luna_exposure',
                    (record.weather_reason or '공개 설명을 바탕으로 한 AI 날씨 노출 추정입니다.')[:255],
                    conflict, '공식 유형 추정과 AI의 주활동 해석이 다릅니다.' if conflict else '',
                    code, type_name, factor, digest)
        level = {'indoor': 'low', 'outdoor': 'high', 'mixed': 'medium'}[label]
        if source == 'name_rule' and (source_conflict or
            (type_level not in {'unknown', level})):
            return WeatherExposure(source='inference_conflict', conflict=True,
                conflict_reason='장소명 추정과 공식 유형 추정이 다르거나 유형 출처가 불일치합니다.',
                reason='두 추정 근거가 충돌해 날씨 노출 점수를 유보합니다.',
                type_code=code, type_name=type_name, input_hash=digest)
        # A mixed venue whose official main activity is outdoor (e.g. a yacht
        # with a cabin) can still be highly weather-exposed. This fusion does
        # not turn its compatibility label into outdoor or permit strict indoor.
        if label == 'mixed' and code in WEATHER_SENSITIVE_MIXED_CODES and type_level == 'high':
            level, factor = 'high', min(factor, TYPE_PRIOR_FACTOR)
            source = f'{source}_and_type'
        conflict = source_conflict or (type_level not in {'unknown', level} and
                                       not (label == 'mixed' and type_level == 'low'))
        reason = (f'{activity}을(를) 주된 방문 활동으로 보아 날씨 노출을 '
                  f'{level}로 추정했습니다.')
        if source.endswith('_and_type'):
            reason += ' 실내외를 모두 이용하지만 공식 유형의 주활동은 야외입니다.'
        return WeatherExposure(level, activity, source, reason[:255], conflict,
            '공식 유형과 장소별 근거의 노출 방향이 다릅니다.' if conflict else '',
            code, type_name, factor, digest)
    if source_conflict:
        return WeatherExposure(source='source_conflict', conflict=True,
            conflict_reason='저장된 세부분류와 TourAPI 매칭 코드가 일치하지 않습니다.',
            reason='공식 유형 코드를 확인할 수 없어 날씨 노출을 추정하지 않습니다.',
            input_hash=digest)
    if type_level != 'unknown':
        return WeatherExposure(type_level, type_activity, 'type_prior',
            f'한국관광공사 유형 「{type_name}」을 바탕으로 한 약한 날씨 노출 추정입니다. '
            '이 유형만으로 개별 장소의 실제 이용방식을 확인할 수 없습니다.', False, '', code,
            type_name, TYPE_PRIOR_FACTOR, digest)
    return WeatherExposure(type_code=code, input_hash=digest)


def veto_ids_for(place_ids):
    return set(PlaceClassificationAttempt.objects.filter(
        place_id__in=place_ids, status='review_after_audit',
    ).values_list('place_id', flat=True))


def exposure_for(place, codes=(), *, veto=False):
    profile = derive_exposure(place, codes, veto=veto)
    try:
        stored = place.weather_exposure_record
    except AttributeError:
        return profile
    if stored.source == 'manual':
        return WeatherExposure(stored.level, stored.activity, 'manual', stored.reason,
            stored.conflict, stored.conflict_reason, stored.type_code,
            stored.type_name, 1.0, stored.input_hash, True)
    if stored.input_hash == profile.input_hash and stored.version == POLICY_VERSION:
        return replace(profile, persisted=True)
    return profile
