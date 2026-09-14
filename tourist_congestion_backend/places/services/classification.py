import re

from django.db import transaction
from django.utils import timezone

from places.models import Place, PlaceClassificationEvidence, PlaceInfo
from places.services.description_classification import (
    RULE_VERSION, LEGACY_AI_PROMPT_VERSION, AI_CONTEXT_PROMPT_VERSION,
    AI_PROMPT_VERSION,
    classify_description, source_hash,
)


# Deliberately narrow: content type alone is not evidence of an individual venue.
NAME_RULES = (
    (r'도서관$|박물관$|미술관$|과학관$|전시관$', Place.IndoorOutdoor.INDOOR,
     {'관광지', '문화시설'}),
    (r'해수욕장|해변|일출봉|수목원|자연휴양림', Place.IndoorOutdoor.OUTDOOR,
     {'관광지', '레포츠'}),
)

# Audited against deterministic name samples from the nationwide local list
# (see docs/pilot-improvement-2026-09-12.md). Category and suffix together
# describe the visitor's principal exposure; individual mixed venues can be
# corrected manually without this rule overwriting their evidence.
NEW_NAME_RULES = (
    (r'공원$', Place.IndoorOutdoor.OUTDOOR, {'관광지'}),
    (r'둘레길$|산책로$|등산로$', Place.IndoorOutdoor.OUTDOOR, {'관광지', '레포츠'}),
    (r'폭포$|계곡$', Place.IndoorOutdoor.OUTDOOR, {'관광지'}),
    (r'오름$', Place.IndoorOutdoor.OUTDOOR, {'관광지'}),
    (r'광장$', Place.IndoorOutdoor.OUTDOOR, {'관광지'}),
    (r'캠핑장$|야영장$', Place.IndoorOutdoor.OUTDOOR, {'레포츠'}),
    (r'아쿠아리움$|수족관$', Place.IndoorOutdoor.INDOOR, {'관광지', '문화시설', '쇼핑'}),
    (r'기념관$|역사관$', Place.IndoorOutdoor.INDOOR, {'관광지', '문화시설'}),
    (r'극장$|영화관$', Place.IndoorOutdoor.INDOOR, {'문화시설'}),
)

def name_decision(place):
    """The existing narrow name rule, recomputed when a name changes."""
    matches = []
    for version, rules in (('v5', NAME_RULES[:1]), ('v2', NAME_RULES[1:]),
                           ('v3', NEW_NAME_RULES)):
        for pattern, label, categories in rules:
            if place.category not in categories:
                continue
            if version == 'v3' and pattern == r'극장$|영화관$' and re.search(
                r'노천|자동차|야외|드라이브', place.name,
            ):
                continue
            match = re.search(pattern, place.name)
            if match:
                matches.append((label, match.group(), version))
    if len(matches) != 1:
        return None
    label, evidence, version = matches[0]
    return label, f'reviewed_name_rule_{version}', f'name:{evidence}'


def current_description_evidence(place):
    """A stored automatic label is usable only with its exact current input."""
    try:
        record = place.classification_record
    except PlaceClassificationEvidence.DoesNotExist:
        return None
    if record.method not in {'description_rule', 'luna_validated'}:
        return None
    try:
        description = place.info.description
    except PlaceInfo.DoesNotExist:
        description = ''
    if record.method == 'description_rule' and record.version not in {'description_v1', RULE_VERSION}:
        return None
    if record.method == 'luna_validated' and record.version not in {
        LEGACY_AI_PROMPT_VERSION, AI_CONTEXT_PROMPT_VERSION, AI_PROMPT_VERSION,
    }:
        return None
    version = record.version
    if record.input_hash != source_hash(place.name, place.category, description, version=version):
        return None
    if record.label != place.indoor_outdoor or place.indoor_outdoor_source != record.method:
        return None
    from places.services.description_classification import (
        is_placeholder_description, normalized_description,
    )
    text = normalized_description(description)
    if is_placeholder_description(text):
        return None
    if text[record.span_start:record.span_end] != record.quote:
        return None
    if record.evidence_quotes and any(quote not in text for quote in record.evidence_quotes):
        return None
    if record.method == 'luna_validated':
        if record.version == LEGACY_AI_PROMPT_VERSION:
            from places.services.description_classification import validate_ai_decision
            if validate_ai_decision(place.name, place.category, description,
                label=record.label, quote=record.quote, scope='principal_place') is None:
                return None
        elif record.version == AI_CONTEXT_PROMPT_VERSION:
            from places.services.description_classification import validate_contextual_ai_proposal
            proposal = {'label': record.label, 'primary_activity': record.primary_activity,
                        'evidence_quotes': record.evidence_quotes, 'scope': record.scope,
                        'ancillary_note': record.ancillary_note, 'rationale': record.rationale}
            if validate_contextual_ai_proposal(place.name, place.category,
                description, proposal)[0] is None:
                return None
        else:
            from places.services.description_classification import validate_weather_ai_proposal
            proposal = {'label': record.label, 'primary_activity': record.primary_activity,
                        'evidence_quotes': record.evidence_quotes, 'scope': record.scope,
                        'ancillary_note': record.ancillary_note, 'rationale': record.rationale,
                        'weather_exposure': record.weather_exposure,
                        'exposure_activity': record.weather_activity,
                        'exposure_reason': record.weather_reason}
            if validate_weather_ai_proposal(place.name, place.category,
                description, proposal)[0] is None:
                return None
    return record


@transaction.atomic
def classify_place(place, info=None):
    """Re-evaluate automatic labels; never overwrite a manual judgement."""
    locked = Place.objects.select_for_update().get(pk=place.pk)
    if locked.indoor_outdoor_source == 'manual':
        return False
    if info is None and locked.indoor_outdoor_source in {'description_rule', 'luna_validated'}:
        info = PlaceInfo.objects.filter(place_id=locked.pk).first()
    description = info.description if info is not None else ''
    decision = classify_description(locked.name, locked.category, description) if description else None
    if decision is not None:
        new_values = (decision.label, decision.method, f'description:{decision.quote}'[:255])
    elif locked.indoor_outdoor_source == 'luna_validated' and current_description_evidence(locked):
        return False
    else:
        new_values = name_decision(locked) or (Place.IndoorOutdoor.UNKNOWN, '', '')
    old_values = (locked.indoor_outdoor, locked.indoor_outdoor_source,
                  locked.indoor_outdoor_evidence)
    changed = old_values != new_values
    if changed:
        locked.indoor_outdoor, locked.indoor_outdoor_source, locked.indoor_outdoor_evidence = new_values
        locked.save(update_fields=['indoor_outdoor', 'indoor_outdoor_source',
                                   'indoor_outdoor_evidence', 'updated_at'])
    if decision is not None:
        digest = source_hash(locked.name, locked.category, description)
        existing = PlaceClassificationEvidence.objects.filter(place=locked).first()
        quotes = list(decision.evidence_quotes or (decision.quote,))
        if existing is None or (existing.label, existing.method, existing.version,
                existing.input_hash, existing.quote, existing.span_start, existing.span_end,
                existing.evidence_quotes, existing.primary_activity, existing.scope,
                existing.rationale) != (
                decision.label, decision.method, decision.version, digest, decision.quote,
                decision.span_start, decision.span_end, quotes, decision.primary_activity,
                decision.scope, decision.rationale):
            PlaceClassificationEvidence.objects.update_or_create(place=locked, defaults={
                'label': decision.label, 'method': decision.method, 'version': decision.version,
                'input_hash': digest, 'quote': decision.quote, 'span_start': decision.span_start,
                'span_end': decision.span_end, 'evidence_quotes': quotes,
                'primary_activity': decision.primary_activity, 'scope': decision.scope,
                'ancillary_note': '', 'rationale': decision.rationale,
                'previous_label': old_values[0] if changed else
                                  (existing.previous_label if existing else old_values[0]),
                'previous_source': old_values[1] if changed else
                                   (existing.previous_source if existing else old_values[1]),
                'model': '', 'classified_at': timezone.now(),
            })
    else:
        PlaceClassificationEvidence.objects.filter(place=locked).delete()
    place.indoor_outdoor, place.indoor_outdoor_source, place.indoor_outdoor_evidence = new_values
    return changed
