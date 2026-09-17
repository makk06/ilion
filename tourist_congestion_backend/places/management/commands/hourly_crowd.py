import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from places.hourly_models import HourlyStudy, HourlyRun
from places.services.hourly_collector import create_study, discover_tmap, tick, capacity
from places.services.hourly_evaluation import evaluate, select_parameters, validate_shadow, promote, monitor, advance
from places.services.hourly_store import reproduce, prune
from places.services.crowd_collector import acquire_lease, release_lease


class Command(BaseCommand):
    help = 'Independent hourly population/density pilot; never fabricates accuracy.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['init', 'discover', 'status', 'tick', 'select', 'advance', 'evaluate', 'shadow', 'promote', 'rollback', 'monitor', 'prune', 'reproduce'])
        parser.add_argument('--provider', choices=['seoul', 'tmap'])
        parser.add_argument('--run', type=int)
        parser.add_argument('--target', type=int, action='append', help='Explicit target IDs for promotion/rollback')
        parser.add_argument('--output')
        parser.add_argument('--artifacts', help='Directory for metrics, per-hour rows and full-period plots')

    def handle(self, *args, **options):
        action, provider = options['action'], options['provider']
        if action in ('init', 'discover', 'select', 'evaluate', 'shadow', 'promote', 'rollback') and not provider:
            raise CommandError('--provider is required')
        try:
            if action == 'init':
                study = create_study(provider)
                result = {'study_id': study.pk, 'candidates': study.targets.count(), 'capacity': capacity(provider)}
            elif action == 'status':
                result = [{'study_id': s.pk, 'provider': s.provider, 'capacity': capacity(s.provider),
                           'state': s.state, 'targets': list(s.targets.values('id', 'external_id', 'name', 'metric', 'active', 'selected', 'promoted'))}
                          for s in HourlyStudy.objects.all()]
            elif action == 'advance':
                result = advance(provider=provider, output=options['artifacts'])
            elif action == 'tick':
                owner = acquire_lease()
                if not owner:
                    result = {'status': 'already_running'}
                else:
                    try:
                        result = tick()
                    finally:
                        release_lease(owner)
            elif action == 'reproduce':
                result = reproduce(HourlyRun.objects.select_related('target__study').get(pk=options['run']))
            elif action in ('monitor', 'prune'):
                {'monitor': monitor, 'prune': prune}[action]()
                result = {'status': 'done'}
            else:
                study = HourlyStudy.objects.get(provider=provider)
                if action == 'rollback':
                    targets = study.targets.all()
                    if options['target']:
                        targets = targets.filter(pk__in=options['target'])
                    targets.update(promoted=False)
                    result = {'status': 'legacy_restored'}
                elif action == 'promote':
                    result = promote(study, target_ids=options['target'])
                elif action in ('evaluate', 'shadow'):
                    result = {'evaluate': evaluate, 'shadow': validate_shadow}[action](study, output=options['artifacts'])
                else:
                    result = {'discover': discover_tmap, 'select': select_parameters}[action](study)
        except (ValueError, HourlyStudy.DoesNotExist, HourlyRun.DoesNotExist) as exc:
            raise CommandError(str(exc)) from None
        if options['artifacts'] and isinstance(result, dict) and result.get('status') == 'NEEDS_MORE_DATA':
            from places.services.hourly_reporting import export_report
            export_report(options['artifacts'], {**result, 'provider': provider}, [])
        encoded = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if options['output']:
            path = Path(options['output'])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded, encoding='utf-8')
        self.stdout.write(encoded)
