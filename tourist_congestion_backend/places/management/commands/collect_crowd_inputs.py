import json
from django.core.management.base import BaseCommand, CommandError
from places.services.crowd_collector import run_once, LIMIT_ENV


class Command(BaseCommand):
    help = 'Run due free API collection once (invoke every minute from the OS scheduler).'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--provider', choices=list(LIMIT_ENV))
        parser.add_argument('--max-seconds', type=int, default=45)

    def handle(self, *args, **options):
        if not 1 <= options['max_seconds'] <= 120:
            raise CommandError('--max-seconds must be 1..120')
        report = run_once(max_seconds=options['max_seconds'], provider_filter=options['provider'])
        self.stdout.write(json.dumps(report, ensure_ascii=False))
