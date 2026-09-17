from collections import Counter
import os

from django.core.management.base import BaseCommand, CommandError

from places.models import PlaceClassificationEvidence, PlaceInfo
from places.services.classification import classify_place, current_description_evidence, name_decision
from places.services.description_classification import classify_description, source_hash
from places.services.luna_classification import DAILY_CALL_CAP, classify_with_luna


class Command(BaseCommand):
    help = 'Review or apply conservative indoor/outdoor classification from stored public descriptions.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--place-id', type=int, action='append')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--ai', action='store_true', help='Explicit opt-in for ambiguous descriptions')
        parser.add_argument('--allow-live-ai', action='store_true', help='Second live-call safety switch')
        parser.add_argument('--max-calls', type=int, default=0)

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 500:
            raise CommandError('--limit must be between 1 and 500')
        if options['ai']:
            if not options['apply'] or not options['allow_live_ai']:
                raise CommandError('Live AI requires --apply --ai --allow-live-ai')
            if not 1 <= options['max_calls'] <= DAILY_CALL_CAP:
                raise CommandError(f'--max-calls must be between 1 and {DAILY_CALL_CAP}')
            if not os.environ.get('OPENAI_API_KEY'):
                raise CommandError('OPENAI_API_KEY is not configured')
        elif options['max_calls'] or options['allow_live_ai']:
            raise CommandError('--max-calls and --allow-live-ai require --ai')
        queryset = PlaceInfo.objects.exclude(description='').select_related('place').order_by('place_id')
        if options['place_id']:
            queryset = queryset.filter(place_id__in=options['place_id'])
        infos = list(queryset[:limit])
        counts = Counter()
        examples = []
        ai_calls = 0
        for info in infos:
            place = info.place
            if place.indoor_outdoor_source == 'manual':
                counts['manual_protected'] += 1
                continue
            decision = classify_description(place.name, place.category, info.description)
            predicted = ((decision.label, 'description_rule') if decision else
                         (place.indoor_outdoor, place.indoor_outdoor_source)
                         if place.indoor_outdoor_source == 'luna_validated' and
                         current_description_evidence(place) else
                         (name_decision(place) or ('unknown', '', ''))[:2])
            current = (place.indoor_outdoor, place.indoor_outdoor_source)
            counts['description_rule' if decision else 'ambiguous'] += 1
            if decision is not None:
                existing = PlaceClassificationEvidence.objects.filter(place=place).first()
                if existing is None or (existing.version, existing.input_hash) != (
                    decision.version, source_hash(place.name, place.category, info.description),
                ):
                    counts['would_refresh_evidence'] += 1
            if current != predicted:
                counts['would_change'] += 1
                examples.append((place.id, place.name[:50], current, predicted,
                                 decision.quote[:70] if decision else ''))
            if options['apply']:
                counts['changed'] += int(classify_place(place, info))
                if options['ai'] and decision is None and ai_calls < options['max_calls']:
                    outcome = classify_with_luna(place.id)
                    counts[f'ai_{outcome}'] += 1
                    if outcome not in {'already_attempted', 'daily_cap', 'manual_or_missing',
                                       'no_bounded_description', 'deterministic_available', 'missing_key'}:
                        ai_calls += 1
        self.stdout.write(('APPLY' if options['apply'] else 'DRY-RUN') +
                          f' scanned={len(infos)} ' + ' '.join(f'{k}={v}' for k, v in sorted(counts.items())))
        for place_id, name, old, new, quote in examples:
            self.stdout.write(f'  id={place_id} {name} {old[0]}/{old[1]} -> '
                              f'{new[0]}/{new[1]} quote={quote}')
