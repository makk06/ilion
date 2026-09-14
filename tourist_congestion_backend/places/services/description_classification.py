"""Conservative, reproducible evidence from public TourAPI descriptions."""

import hashlib
import html
import json
import re
from dataclasses import dataclass


RULE_VERSION = 'description_v2'
LEGACY_AI_PROMPT_VERSION = 'luna_description_v2'
AI_CONTEXT_PROMPT_VERSION = 'luna_context_v3'
AI_PROMPT_VERSION = 'luna_weather_v4'


@dataclass(frozen=True)
class Decision:
    label: str
    quote: str
    span_start: int
    span_end: int
    method: str = 'description_rule'
    version: str = RULE_VERSION
    evidence_quotes: tuple[str, ...] = ()
    primary_activity: str = ''
    scope: str = 'principal_place'
    rationale: str = ''
    weather_exposure: str = ''
    weather_activity: str = ''
    weather_reason: str = ''


def normalized_description(description):
    # TourAPI descriptions are plain text or HTML snippets. Offsets refer to
    # this normalized public text, not to a mutable HTML byte offset.
    plain = re.sub(r'<[^>]*>', ' ', html.unescape(description or ''))
    return re.sub(r'\s+', ' ', plain).strip()


def is_placeholder_description(description):
    text = normalized_description(description)
    return '개발용 상세정보' in text and '실제 운영에서는 TourAPI 상세정보로 갱신됩니다' in text


def source_hash(name, category, description, *, version=RULE_VERSION):
    source = [version, name or '', category or '', normalized_description(description)]
    return hashlib.sha256(json.dumps(source, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


_MIXED = (
    re.compile(r'실내와\s*실외\s*모두'),
    re.compile(r'실내\s*휴식\s*공간과\s*야외\s*데크'),
    re.compile(r'(?:상설\s*전시장|체험\s*전시실|전시실).{0,45}야외\s*전시장'),
    re.compile(r'실내\s*공간과\s*야외\s*(?:공간|테이블|데크|정원)'),
)
_INDOOR = (
    re.compile(r'실내\s*(?:사격장|공간|휴식\s*공간|전시실|전시장|체험장|놀이터)'),
    re.compile(r'(?<![가-힣])지하\s*(?:도\s*)?상가'),
)
_OUTDOOR = (
    re.compile(r'야외\s*(?:스케이트장|캠핑장|야영장|체험장|놀이터|전시장)'),
    re.compile(r'실외\s*(?:활동\s*공간|체험장|놀이터)'),
)
_BROAD_INDOOR = re.compile(r'실내|건물\s*내부|내부\s*공간|지하\s*(?:도\s*)?상가|전시실')
_BROAD_OUTDOOR = re.compile(r'야외|실외|옥외|노천|외부\s*(?:테이블|정원|데크|전시장)')
_UNSAFE_CONTEXT = re.compile(r'아닌|아니며|않|없[는다]|폐쇄|폐지|과거|예전|옛날|근처|인근|주변|인접|맞은편|일반\s*야외')


def _safe_match(text, match):
    # A sentence mentioning another nearby, past, or negated facility is not
    # evidence of the principal place. We intentionally lose some coverage.
    left = max(0, text.rfind('.', 0, match.start()) + 1)
    right = text.find('.', match.end())
    sentence = text[left:right if right >= 0 else len(text)]
    return not _UNSAFE_CONTEXT.search(sentence)


def _decision(text, match, label):
    return Decision(label, match.group(), match.start(), match.end())


def _safe_broad_hits(text, pattern):
    return [match for match in pattern.finditer(text) if _safe_match(text, match)]


def _classify_description_v1(name, category, description):
    text = normalized_description(description)
    if not text:
        return None
    for pattern in _MIXED:
        match = pattern.search(text)
        if match and _safe_match(text, match):
            return _decision(text, match, 'mixed')
    hits = []
    for label, patterns in (('indoor', _INDOOR), ('outdoor', _OUTDOOR)):
        for pattern in patterns:
            for match in pattern.finditer(text):
                if _safe_match(text, match):
                    hits.append((label, match))
    if not hits or len({label for label, _ in hits}) != 1:
        return None
    label, match = min(hits, key=lambda item: item[1].start())
    # Explicit outdoor seating/decks in another sentence must stop an indoor
    # hard-filter label, even if this first rule cannot prove a mixed visit.
    opposite = _BROAD_OUTDOOR if label == 'indoor' else _BROAD_INDOOR
    if _safe_broad_hits(text, opposite):
        return None
    # A separate indoor institution's yard, or a park's indoor side room,
    # must not flip the principal place into a single-exposure strict label.
    if label == 'outdoor' and re.search(r'도서관|박물관|미술관|전시관|과학관', name):
        return None
    if label == 'indoor' and re.search(r'공원$|광장$|해수욕장$|해변$', name):
        return None
    return _decision(text, match, label)


def _sentences(text):
    start = 0
    for match in re.finditer(r'[.!?](?:\s|$)', text):
        end = match.start() + 1
        sentence = text[start:end].strip()
        if sentence:
            yield sentence
        start = match.end()
    rest = text[start:].strip()
    if rest:
        yield rest


def _context_decision(text, label, quotes, activity, rationale):
    quotes = tuple(quotes)
    if not quotes or any(not quote or len(quote) > 255 or quote not in text for quote in quotes):
        return None
    first = quotes[0]
    start = text.find(first)
    return Decision(label, first, start, start + len(first),
                    evidence_quotes=quotes, primary_activity=activity,
                    scope='principal_mixed' if label == 'mixed' else 'principal_place',
                    rationale=rationale)


def _safe_sentence(text, sentence):
    return not _UNSAFE_CONTEXT.search(sentence)


def _contextual_description(name, category, text):
    """Type + principal-activity context; no individual place-name exceptions."""
    sentences = list(_sentences(text))
    if not sentences:
        return None

    # The target itself is a gate or outdoor monument. An entrance to a
    # different, connected underground exhibition does not make it mixed.
    if category == '관광지' and re.search(r'(?:동상|조각상|기념비)$', name):
        for sentence in sentences[:4]:
            if (name in sentence and re.search(r'광장|공원|거리|길', sentence) and
                re.search(r'동상|조각상|기념비', sentence) and
                re.search(r'있다|자리|설치|세워|조성', sentence) and
                _safe_sentence(text, sentence)):
                return _context_decision(text, 'outdoor', [sentence],
                    '야외 동상·기념물 관람', '방문 대상인 기념물 자체가 광장·공원·거리의 설치물입니다.')
    if category == '관광지' and len(name) >= 2 and name.endswith('문'):
        for sentence in sentences[:3]:
            if (name in sentence and re.search(r'궁궐|경복궁|왕궁|궁성|성곽|도성', sentence) and
                re.search(r'정문|성문|문루|궐문', sentence) and
                not re.search(r'실내|전시실|전시관|복제품|복제|모형|재현품|실내\s*설치', sentence) and
                _safe_sentence(text, sentence)):
                return _context_decision(text, 'outdoor', [sentence],
                    '문·성문 외관 및 출입 관람', '방문 대상은 건물 내부 시설이 아닌 궁궐·성곽의 문입니다.')
    if category == '관광지' and re.search(r'스크린|미디어파사드', name):
        for sentence in sentences:
            if ('외벽' in sentence and re.search(r'스크린|화면|미디어아트', sentence) and
                re.search(r'설치|상영|선보', sentence) and _safe_sentence(text, sentence)):
                return _context_decision(text, 'outdoor', [sentence],
                    '외벽 미디어아트 관람', '스크린은 건물 외벽의 관람 대상이며 건물 이름은 위치 설명입니다.')

    # Explicitly co-located principal activities. Words in another named
    # attraction, or an adjacent library/park, are not merged into the target.
    for sentence in sentences:
        if not _safe_sentence(text, sentence):
            continue
        if (re.search(r'실내\s*수족관', sentence) and
            re.search(r'생태\s*연못|자연\s*연못', sentence) and
            re.search(r'구성|볼\s*수', sentence)):
            return _context_decision(text, 'mixed', [sentence],
                '실내 수족관과 야외 연못 관람', '같은 전시 장소의 구성에 실내 수족관과 자연 연못이 함께 있습니다.')
        if (re.search(r'실내\s*체육관', sentence) and re.search(r'야구장', sentence) and
            re.search(r'운영|준공|구성', sentence) and re.search(r'운동장|체육공원', name)):
            return _context_decision(text, 'mixed', [sentence],
                '실내 체육시설과 경기장 이용', '종합운동장의 구성 시설에 실내 체육관과 경기장이 함께 있습니다.')

    if category == '음식점':
        outdoor = next((s for s in sentences if re.search(r'야외\s*테이블|외부\s*테이블', s)
                        and re.search(r'먹|식사|고기|즐', s) and _safe_sentence(text, s)), None)
        indoor = next((s for s in sentences if re.search(r'내부\s*공간|실내\s*공간', s)
                       and re.search(r'먹|식사|음식|즐|테이블', s) and _safe_sentence(text, s)), None)
        if indoor and outdoor:
            return _context_decision(text, 'mixed', [outdoor, indoor],
                '실내외 좌석에서 식사', '같은 음식점의 실내 공간과 야외 테이블에서 모두 식사합니다.')
        if not outdoor and not _safe_broad_hits(text, _BROAD_OUTDOOR):
            room = next((s for s in sentences if re.search(r'식사\s*장소.{0,20}룸', s)
                         and _safe_sentence(text, s)), None)
            interior = next((s for s in sentences if re.search(r'실내는.{0,40}(?:층|회의실)', s)
                             and _safe_sentence(text, s)), None)
            if room and interior:
                return _context_decision(text, 'indoor', [room, interior],
                    '실내 룸 식사', '주된 식사 공간이 룸이며 설명이 실내 층 구성을 확인합니다.')

    if category == '쇼핑' and re.search(r'시장|상가', name):
        basement = next((s for s in sentences if re.search(r'지하에는.{0,70}(?:센터|점포|상가)', s)
                         and _safe_sentence(text, s)), None)
        floors = next((s for s in sentences if re.search(r'1층에는.{0,70}(?:점포|가게|활어)', s)
                       and _safe_sentence(text, s)), None)
        if basement and floors and not _safe_broad_hits(text, _BROAD_OUTDOOR):
            return _context_decision(text, 'indoor', [basement, floors],
                '건물 안 시장 쇼핑', '해당 시장의 지하와 지상층에 점포가 배치되어 있습니다.')

    if re.search(r'실내\s*수영장', name) and re.search(r'수영장|수영\s*강습', text):
        sentence = next((s for s in sentences[:3] if name.replace(' ', '') in s.replace(' ', '')
                         and re.search(r'수영|레인|풀', s) and _safe_sentence(text, s)), None)
        if sentence and not _safe_broad_hits(text, _BROAD_OUTDOOR):
            return _context_decision(text, 'indoor', [sentence],
                '실내 수영장 이용', '실내 시설로 명시된 수영장이 실제 수영 운영 장소입니다.')

    return None


def classify_description(name, category, description):
    text = normalized_description(description)
    if not text or is_placeholder_description(text):
        return None
    decision = _contextual_description(name, category, text)
    if decision is not None:
        return decision
    return _classify_description_v1(name, category, text)


def validate_ai_decision(name, category, description, *, label, quote, scope):
    """Accept only a narrow, source-verifiable quote, never model confidence."""
    if label not in {'indoor', 'outdoor', 'mixed', 'unknown'} or scope not in {
        'principal_place', 'mixed_place', 'uncertain', 'other_place',
    }:
        return None
    text = normalized_description(description)
    if label == 'unknown' or scope not in {'principal_place', 'mixed_place'}:
        return None
    if not isinstance(quote, str) or not quote or len(quote) > 255:
        return None
    # Repeating the venue name from the description is not independent
    # evidence of the visitor environment, even if the name says "indoor".
    if quote.strip() in name or (
        quote.strip().startswith(name) and len(quote.strip()) <= len(name) + 2
    ):
        return None
    start = text.find(quote)
    source_match = re.search(re.escape(quote), text) if start >= 0 else None
    if source_match is None or not _safe_match(text, source_match):
        return None
    # A quote is not independently verified semantics. Require an explicit
    # exposure anchor and reject contradictory or nearby/past source context;
    # this remains a low-weight AI inference, never hard indoor evidence.
    indoor = bool(_safe_broad_hits(quote, _BROAD_INDOOR))
    outdoor = bool(_safe_broad_hits(quote, _BROAD_OUTDOOR))
    if label == 'indoor' and (not indoor or outdoor or _safe_broad_hits(text, _BROAD_OUTDOOR)):
        return None
    if label == 'outdoor' and (not outdoor or indoor or _safe_broad_hits(text, _BROAD_INDOOR)):
        return None
    if label == 'mixed' and not (indoor and outdoor):
        return None
    return Decision(label, quote, start, start + len(quote),
                    method='luna_validated', version=LEGACY_AI_PROMPT_VERSION)


_CONTEXT_LABELS = {'indoor', 'outdoor', 'mixed', 'unknown'}
_CONTEXT_SCOPES = {'principal_place', 'principal_mixed', 'ancillary_only',
                   'other_place', 'uncertain'}
_ANCILLARY_ONLY = re.compile(
    r'(?:다른|별도(?:의)?|인접한|맞은편(?:의)?)\s*(?:[가-힣\s]{0,18})?'
    r'(?:시설|전시관|박물관|미술관|도서관|공연장)|'
    r'(?:전시관|박물관|미술관).{0,12}(?:통하는|연결된)\s*입구'
)
_NEGATED_INDOOR = re.compile(r'(?:실내|내부\s*공간|건물\s*내부).{0,14}(?:없|아니|폐쇄|폐지)')
_NEGATED_OUTDOOR = re.compile(r'(?:야외|실외|옥외|노천).{0,14}(?:없|아니|폐쇄|폐지)')


def validate_contextual_ai_proposal(name, category, description, proposal):
    """Return (decision, reason code, safe audit fields), never raw provider text.

    Exact source quotes and scope are mechanically checked. The model's
    interpretation remains an inference, not regex-certified truth.
    """
    keys = {'label', 'primary_activity', 'evidence_quotes', 'scope',
            'ancillary_note', 'rationale'}
    if not isinstance(proposal, dict) or set(proposal) != keys:
        return None, 'invalid_schema', {}
    label = proposal['label']
    scope = proposal['scope']
    if not isinstance(label, str) or not isinstance(scope, str) or (
        label not in _CONTEXT_LABELS or scope not in _CONTEXT_SCOPES
    ):
        return None, 'invalid_enum', {}
    fields = {'primary_activity': 120, 'ancillary_note': 255, 'rationale': 255}
    if any(not isinstance(proposal[key], str) or len(proposal[key]) > limit
           for key, limit in fields.items()):
        return None, 'invalid_text_field', {}
    quotes = proposal['evidence_quotes']
    if not isinstance(quotes, list) or len(quotes) > 2 or any(
        not isinstance(quote, str) or len(quote) > 255 for quote in quotes
    ):
        return None, 'invalid_quote_shape', {}
    text = normalized_description(description)
    safe_quotes = [quote for quote in quotes if quote and quote in text]
    safe = {key: proposal[key].strip() for key in ('label', 'primary_activity',
            'scope', 'ancillary_note', 'rationale')}
    safe['evidence_quotes'] = safe_quotes
    if len(safe_quotes) != len(quotes):
        return None, 'quote_not_in_source', safe
    if label == 'unknown':
        return None, 'model_unknown', safe
    if scope not in {'principal_place', 'principal_mixed'}:
        return None, 'not_principal_place', safe
    if (label == 'mixed') != (scope == 'principal_mixed'):
        return None, 'inconsistent_scope', safe
    if not safe['primary_activity'] or not safe['rationale'] or not safe_quotes:
        return None, 'missing_primary_evidence', safe
    if len(set(safe_quotes)) != len(safe_quotes):
        return None, 'duplicate_quote', safe
    if any(quote.strip() in name or (
        quote.strip().startswith(name) and len(quote.strip()) <= len(name) + 2
    ) for quote in safe_quotes):
        return None, 'name_only_quote', safe
    # Nearby/previous mentions are not automatically invalid: "a concert hall
    # on the second floor of a building near a park" can describe this very
    # venue. Reject only explicit negation or a quote solely about a separate
    # facility. Semantic subject/scope remains the low-weight model inference.
    if any(_ANCILLARY_ONLY.search(quote) or
           (label == 'indoor' and _NEGATED_INDOOR.search(quote)) or
           (label == 'outdoor' and _NEGATED_OUTDOOR.search(quote))
           for quote in safe_quotes):
        return None, 'unsafe_quote_context', safe
    first = safe_quotes[0]
    start = text.find(first)
    decision = Decision(label, first, start, start + len(first),
                        method='luna_validated', version=AI_CONTEXT_PROMPT_VERSION,
                        evidence_quotes=tuple(safe_quotes),
                        primary_activity=safe['primary_activity'], scope=scope,
                        rationale=safe['rationale'])
    return decision, '', safe


def validate_weather_ai_proposal(name, category, description, proposal):
    """Validate a v4 direct exposure judgement without claiming measured truth."""
    from dataclasses import replace

    base_keys = {'label', 'primary_activity', 'evidence_quotes', 'scope',
                 'ancillary_note', 'rationale'}
    extra_keys = {'weather_exposure', 'exposure_activity', 'exposure_reason'}
    if not isinstance(proposal, dict) or set(proposal) != base_keys | extra_keys:
        return None, 'invalid_schema', {}
    decision, reason, safe = validate_contextual_ai_proposal(name, category,
        description, {key: proposal[key] for key in base_keys})
    if decision is None:
        return None, reason, safe
    level = proposal['weather_exposure']
    activity = proposal['exposure_activity']
    exposure_reason = proposal['exposure_reason']
    if not isinstance(level, str) or level not in {'high', 'medium', 'low', 'unknown'} or not isinstance(
        activity, str) or not isinstance(exposure_reason, str) or len(activity) > 120 or (
        len(exposure_reason) > 255
    ):
        return None, 'invalid_exposure_field', safe
    if level != 'unknown' and (not activity.strip() or not exposure_reason.strip()):
        return None, 'missing_exposure_reason', safe
    safe.update({'weather_exposure': level, 'exposure_activity': activity.strip(),
                 'exposure_reason': exposure_reason.strip()})
    return replace(decision, version=AI_PROMPT_VERSION, weather_exposure=level,
                   weather_activity=activity.strip(),
                   weather_reason=exposure_reason.strip()), '', safe
