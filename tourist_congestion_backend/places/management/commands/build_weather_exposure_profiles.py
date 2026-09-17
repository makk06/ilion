"""Bounded offline persistence of versioned visitor weather exposure."""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from places.models import Place, PlaceWeatherExposure
from places.services.weather_exposure import (
    POLICY_VERSION, derive_exposure, source_codes_for, veto_ids_for,
)


class Command(BaseCommand):
    help = 'Dry-run or store bounded exposure profiles; no provider calls.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--place-id', type=int, action='append')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 500:
            raise CommandError('--limit must be between 1 and 500')
        qs = Place.objects.select_related('info', 'classification_record',
            'weather_exposure_record').order_by('id')
        if options['place_id']:
            qs = qs.filter(id__in=options['place_id'])
        places = list(qs[:limit])
        codes = source_codes_for([place.id for place in places])
        veto = veto_ids_for([place.id for place in places])
        counts = Counter()
        examples = []
        for place in places:
            profile = derive_exposure(place, codes.get(place.id, ()),
                                      veto=place.id in veto)
            counts[f'level_{profile.level}'] += 1
            counts[f'source_{profile.source}'] += 1
            counts['conflict'] += int(profile.conflict)
            try:
                stored = place.weather_exposure_record
            except PlaceWeatherExposure.DoesNotExist:
                stored = None
            if stored and stored.source == 'manual':
                counts['manual_protected'] += 1
                continue
            current = (stored.level, stored.source, stored.input_hash) if stored else None
            proposed = (profile.level, profile.source, profile.input_hash)
            if current != proposed:
                counts['would_change'] += 1
                if len(examples) < 30:
                    examples.append((place.id, place.name[:45],
                        current[:2] if current else None, proposed[:2], profile.type_code))
            if options['apply'] and current != proposed:
                # Recheck after acquiring the write transaction. A manual profile
                # created after the initial scan must never be overwritten.
                with transaction.atomic():
                    fresh = Place.objects.select_for_update().select_related(
                        'info', 'classification_record').get(pk=place.pk)
                    latest = PlaceWeatherExposure.objects.select_for_update().filter(
                        place_id=place.pk).first()
                    if latest and latest.source == 'manual':
                        counts['manual_protected'] += 1
                        continue
                    fresh_profile = derive_exposure(fresh, codes.get(place.id, ()),
                                                    veto=place.id in veto)
                    defaults = {
                        'level': fresh_profile.level, 'activity': fresh_profile.activity,
                        'source': fresh_profile.source, 'reason': fresh_profile.reason,
                        'conflict': fresh_profile.conflict,
                        'conflict_reason': fresh_profile.conflict_reason,
                        'type_code': fresh_profile.type_code,
                        'type_name': fresh_profile.type_name,
                        'factor': fresh_profile.factor, 'version': POLICY_VERSION,
                        'input_hash': fresh_profile.input_hash,
                        'classified_at': timezone.now(),
                    }
                    if latest:
                        # Guard at the SQL write as well as at the read: even an
                        # unexpected concurrent manual update fails closed.
                        changed = PlaceWeatherExposure.objects.filter(
                            pk=latest.pk).exclude(source='manual').update(**defaults)
                    else:
                        _, created = PlaceWeatherExposure.objects.get_or_create(
                            place_id=place.pk, defaults=defaults)
                        changed = int(created)
                    counts['changed'] += changed
        self.stdout.write(('APPLY' if options['apply'] else 'DRY-RUN') +
            f' scanned={len(places)} ' + ' '.join(f'{key}={value}'
            for key, value in sorted(counts.items())))
        for place_id, name, old, new, code in examples:
            self.stdout.write(f'  id={place_id} {name} {old} -> {new} type={code or "none"}')
