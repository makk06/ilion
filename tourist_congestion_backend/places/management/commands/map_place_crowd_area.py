from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.management.base import BaseCommand, CommandError

from places.models import CrowdArea, ExternalSource, Place, PlaceCrowdArea


class Command(BaseCommand):
    help = 'Map an internal place to a Seoul real-time crowd area.'

    def add_arguments(self, parser):
        parser.add_argument('--reviewer', required=True)
        parser.add_argument('--primary', action='store_true', help='Explicitly replace the primary mapping')
        parser.add_argument('--evidence', required=True, help='Document or URL and justification for approval')
        parser.add_argument('--valid-until', required=True, help='Approval expiry as timezone-aware ISO datetime')
        parser.add_argument('place_id', type=int)
        parser.add_argument('area_external_id', help='Seoul AREA_CD')
        parser.add_argument(
            '--method',
            choices=PlaceCrowdArea.MatchMethod.values,
            default=PlaceCrowdArea.MatchMethod.MANUAL,
        )

    def handle(self, *args, **options):
        expiry = parse_datetime(options['valid_until'])
        if not options['reviewer'].strip() or not options['evidence'].strip() or expiry is None or timezone.is_naive(expiry) or expiry <= timezone.now():
            raise CommandError('Evidence and a future timezone-aware expiry are required')
        try:
            place = Place.objects.get(pk=options['place_id'])
        except Place.DoesNotExist:
            raise CommandError(f"Place {options['place_id']} does not exist") from None

        try:
            crowd_area = CrowdArea.objects.get(
                source=ExternalSource.SEOUL_REALTIME,
                external_id=options['area_external_id'],
            )
        except CrowdArea.DoesNotExist:
            raise CommandError(
                f"Seoul crowd area {options['area_external_id']} does not exist; "
                'run sync_seoul_crowd first'
            ) from None

        reviewed_at = timezone.now()
        defaults = {'match_method': options['method'], 'verified': True, 'valid_from': reviewed_at,
                    'valid_until': expiry, 'evidence': {'type': 'manual_review',
                    'reason': options['evidence'], 'reviewer': options['reviewer'],
                    'place_id': place.pk, 'area_id': crowd_area.pk,
                    'area_external_id': crowd_area.external_id,
                    'reviewed_at': reviewed_at.isoformat()}}
        with transaction.atomic():
            if options['primary']:
                PlaceCrowdArea.objects.filter(place=place, is_primary=True).update(is_primary=False)
                defaults['is_primary'] = True
            mapping, created = PlaceCrowdArea.objects.update_or_create(
                place=place, crowd_area=crowd_area, defaults=defaults)
        action = 'created' if created else 'updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'{action} mapping place={mapping.place_id} '
                f'crowd_area={mapping.crowd_area.external_id} '
                f'method={mapping.match_method}'
            )
        )
