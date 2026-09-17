import json
from datetime import timedelta
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from places.models import CrowdArea, MeanStudy, MeanEvidence
from places.services.mean_forecast import dt
from places.services.mean_archive import backfill, append
from places.services.mean_study import audit, tick


class Command(BaseCommand):
    help = 'Isolated mean forecast: init, audit, archive, events, tick, backtest, promote, rollback, monitor.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['init', 'audit', 'archive', 'events', 'tick', 'backtest', 'validate-shadow', 'promote', 'rollback', 'monitor'])
        parser.add_argument('--manifest', help='Verified area/grid or event manifest JSON')
        parser.add_argument('--output', help='Write a reproducible JSON report')

    def handle(self, *args, **options):
        now, action = timezone.now(), options['action']
        study = MeanStudy.objects.filter(name='area-mean-v1').first()
        if action == 'audit':
            result = audit(now)
        elif action == 'archive':
            result = {'archived': backfill(), 'note': 'Original receipt times retained; no retroactive availability invented.'}
        elif action == 'init':
            if study:
                raise CommandError('Study already initialized; cohort cannot be silently reset.')
            if not options['manifest']:
                raise CommandError('--manifest with verified candidates and weather grids is required')
            config = json.loads(Path(options['manifest']).read_text(encoding='utf-8'))
            candidates = config.get('candidates', [])
            if len(candidates) < 3 or len(set(candidates)) != len(candidates):
                raise CommandError('At least three unique candidate area IDs required')
            if CrowdArea.objects.filter(pk__in=candidates, source='seoul_realtime').count() != len(candidates):
                raise CommandError('All candidates must have the existing population provider')
            for area in candidates:
                try:
                    gx, gy = map(int, config['grids'][str(area)].split(','))
                    if not (1 <= gx <= 149 and 1 <= gy <= 253):
                        raise ValueError()
                except (KeyError, TypeError, ValueError):
                    raise CommandError('Each area requires a valid verified KMA grid')
            if not config.get('mapping_evidence'):
                raise CommandError('Record the source used to verify area/grid correspondence')
            from places.services.crowd_collector import daily_limit, seoul_interval
            # Reserve headroom for retries and other jobs using the established quota.
            if daily_limit('seoul') <= 0:
                raise CommandError('Approved Seoul quota is required')
            config['interval_minutes'] = seoul_interval(daily_limit('seoul'), len(candidates))
            if config['interval_minutes'] > 10:
                raise CommandError('Reduce candidates: quota cannot provide three observations in 30 minutes')
            if int(.8*daily_limit('kma')) < len(set(config['grids'].values()))*56:
                raise CommandError('Approved weather quota cannot cover all candidate grids')
            study = MeanStudy.objects.create(started_at=now, config=config, state={'deployment': 'legacy'})
            result = {'status': 'collecting_selection_week', 'study': study.name,
                      'interval_minutes': config['interval_minutes'],
                      'note': 'Five-minute target is quota-limited; hourly coverage remains a required validation gate.'}
        elif action == 'events':
            if not options['manifest']:
                raise CommandError('--manifest is required')
            manifest = json.loads(Path(options['manifest']).read_text(encoding='utf-8'))
            if not manifest.get('verification_evidence') or not CrowdArea.objects.filter(pk=manifest.get('area_id')).exists():
                raise CommandError('Verified area and evidence required')
            try:
                from datetime import date
                if date.fromisoformat(manifest['start_date']) > date.fromisoformat(manifest['end_date']):
                    raise ValueError()
                for event in manifest['events']:
                    if not event['family'] or not event['edition']:
                        raise ValueError()
                    if date.fromisoformat(event['start_date']) > date.fromisoformat(event['end_date']):
                        raise ValueError()
                    if bool(event.get('starts_at')) != bool(event.get('ends_at')):
                        raise ValueError()
                    if event.get('starts_at') and dt(event['starts_at']) >= dt(event['ends_at']):
                        raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise CommandError('Invalid event interval, family or edition')
            manifest['received_at'] = now.isoformat()
            append('event_check', manifest['area_id'], now, manifest)
            result = {'status': 'verified_event_context_saved'}
        elif action == 'tick':
            result = tick(now)
        else:
            if not study:
                raise CommandError('Initialize the study first')
            if action == 'backtest':
                if study.state.get('shadow_start'):
                    raise CommandError('Weights and holdout are locked for this study; use validate-shadow')
                from places.services.mean_replay import run
                result = run(study, now)
                study.state['validation'] = result
                study.state['validated_at'] = now.isoformat()
                if result['status'] == 'PASS':
                    study.state.update(parameters=result['parameters'],
                        shadow_start=(now+timedelta(hours=1)).replace(minute=0, second=0, microsecond=0).isoformat())
                study.save(update_fields=['state'])
            elif action == 'validate-shadow':
                from places.services.mean_study import validate_shadow
                result = validate_shadow(study, now)
                study.state['shadow_validation'] = result
                study.save(update_fields=['state'])
            elif action == 'promote':
                result = study.state.get('validation', {})
                if result.get('status') != 'PASS' or study.state.get('shadow_validation', {}).get('status') != 'PASS':
                    raise CommandError('Real-data validation has not passed; production remains unchanged')
                study.state.update(parameters=result['parameters'], promotion=result, deployment='mean',
                                   promoted_at=now.isoformat())
                study.save(update_fields=['state'])
                result = {'status': 'approved_version_selected', 'parameters': result['parameters']}
            elif action == 'rollback':
                study.state['deployment'] = 'legacy'
                study.save(update_fields=['state'])
                result = {'status': 'legacy_restored'}
            else:
                from places.services.mean_monitor import monitor
                result = monitor(study, now)
        if options['output']:
            destination = Path(options['output'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        self.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))
