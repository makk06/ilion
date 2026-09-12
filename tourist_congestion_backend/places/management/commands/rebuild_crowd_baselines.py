from django.core.management.base import BaseCommand
from places.services.crowd_baseline import rebuild_baselines, prune_evidence


class Command(BaseCommand):
    help = 'Build 84-day baselines from observed evidence, then optionally prune raw rows.'

    def add_arguments(self, parser):
        parser.add_argument('--prune', action='store_true')

    def handle(self, *args, **options):
        count = rebuild_baselines()
        if options['prune']:
            prune_evidence()
        self.stdout.write(f'baselines={count}')
