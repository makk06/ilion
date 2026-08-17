from django.core.management.base import BaseCommand, CommandError

from places.integrations import ExternalAPIError
from places.integrations.tour_api import TourAPIClient
from places.models import ExternalSource, PlaceSource
from places.services import TourPlaceDetailSyncService


class Command(BaseCommand):
    help = 'Enrich matched TourAPI places with common and introduction details.'

    def add_arguments(self, parser):
        parser.add_argument('content_ids', nargs='*')
        parser.add_argument('--region-code', help='Internal region code prefix')
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--skip-intro', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= 100:
            raise CommandError('--limit must be between 1 and 100')

        queryset = PlaceSource.objects.filter(
            source=ExternalSource.TOUR_API,
            match_status=PlaceSource.MatchStatus.MATCHED,
            place__isnull=False,
        ).select_related('place').order_by('external_id')
        if options['content_ids']:
            queryset = queryset.filter(external_id__in=options['content_ids'])
        if options['region_code']:
            queryset = queryset.filter(
                place__region_code__startswith=options['region_code']
            )

        sources = list(queryset[: options['limit']])
        if not sources:
            raise CommandError('No matched TourAPI places found for detail sync')

        try:
            result = TourPlaceDetailSyncService(TourAPIClient()).sync(
                sources,
                include_intro=not options['skip_intro'],
                dry_run=options['dry_run'],
            )
        except ExternalAPIError as error:
            raise CommandError(str(error)) from None

        prefix = '[dry-run] ' if options['dry_run'] else ''
        request_count = result.processed * (1 if options['skip_intro'] else 2)
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}processed={result.processed} '
                f'infos_created={result.infos_created} '
                f'infos_updated={result.infos_updated} '
                f'skipped={result.skipped} external_requests={request_count}'
            )
        )
