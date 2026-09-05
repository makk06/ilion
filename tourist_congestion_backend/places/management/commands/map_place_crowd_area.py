from django.core.management.base import BaseCommand, CommandError

from places.models import CrowdArea, ExternalSource, Place, PlaceCrowdArea


class Command(BaseCommand):
    help = 'Map an internal place to a Seoul real-time crowd area.'

    def add_arguments(self, parser):
        parser.add_argument('place_id', type=int)
        parser.add_argument('area_external_id', help='Seoul AREA_CD')
        parser.add_argument(
            '--method',
            choices=PlaceCrowdArea.MatchMethod.values,
            default=PlaceCrowdArea.MatchMethod.MANUAL,
        )

    def handle(self, *args, **options):
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

        mapping, created = PlaceCrowdArea.objects.update_or_create(
            place=place,
            crowd_area=crowd_area,
            defaults={'match_method': options['method']},
        )
        action = 'created' if created else 'updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'{action} mapping place={mapping.place_id} '
                f'crowd_area={mapping.crowd_area.external_id} '
                f'method={mapping.match_method}'
            )
        )
