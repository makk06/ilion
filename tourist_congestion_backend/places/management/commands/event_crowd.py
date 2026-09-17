import json
from datetime import timedelta
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from places.hourly_models import HourlyTarget, HourlyStudy
from places.models import EventExperimentRun, MeanEvidence
from places.services.event_experiment import issue, reproduce, report
from places.services.hourly_forecast import dt


class Command(BaseCommand):
    help = 'Independent event shadow/replay/report; never promotes a model.'
    def add_arguments(self, p):
        p.add_argument('action', choices=['init','tick','replay','report','reproduce','prune','freeze','validate','validate-shadow','promote','rollback','monitor'])
        p.add_argument('--study', type=int)
        p.add_argument('--target', type=int)
        p.add_argument('--start')
        p.add_argument('--end')
        p.add_argument('--output')
    def handle(self, *args, **o):
        if o['action']=='init':
            from places.models import TourEvent
            from places.services.event_context import archive_event
            now=timezone.now(); count=0
            for event in TourEvent.objects.filter(first_seen_at__isnull=True):
                if not event.active: event.status='unpublished'
                TourEvent.objects.filter(pk=event.pk).update(status=event.status)
                archive_event(event,now); count+=1
            self.stdout.write(json.dumps({'initialized':count,'received_at':now.isoformat()})); return
        if o['action'] in ('freeze','validate','validate-shadow','promote','rollback','monitor'):
            from places.services.event_validation import freeze, validate, promotion_allowed, monitor
            if not o['study']: raise CommandError('--study is required')
            study=HourlyStudy.objects.get(pk=o['study'])
            try:
                if o['action']=='freeze':
                    if not o['start']: raise ValueError('--start selection start is required')
                    result=freeze(study,o['start'])
                elif o['action'].startswith('validate'): result=validate(study,shadow=o['action']=='validate-shadow')
                elif o['action']=='monitor': result=monitor(study)
                else:
                    enabled=o['action']=='promote'
                    if enabled and not promotion_allowed(study): raise ValueError('Event promotion gates have not passed')
                    study.state={**study.state,'event_promoted':enabled}; study.save(update_fields=['state'])
                    result={'event_promoted':enabled}
            except ValueError as e: raise CommandError(str(e)) from e
            text=json.dumps(result,ensure_ascii=False,indent=2)
            if o['output']:
                path=Path(o['output']); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding='utf-8')
            else: self.stdout.write(text)
            return
        if o['action']=='prune':
            # Preserve last version per key, including active mappings older than 400 days.
            from django.db.models import Max
            cutoff=timezone.now()-timedelta(days=400)
            latest=MeanEvidence.objects.filter(kind__in=['event','event_link']).values('kind','key').annotate(last=Max('id')).values_list('last',flat=True)
            MeanEvidence.objects.filter(kind__in=['event','event_link'],received_at__lt=cutoff).exclude(id__in=list(latest)).delete()
            EventExperimentRun.objects.filter(issued_at__lt=timezone.now()-timedelta(days=300)).delete()
            self.stdout.write('pruned'); return
        targets=HourlyTarget.objects.filter(active=True).select_related('study')
        if o['target']:
            targets=targets.filter(pk=o['target'])
        if not targets.exists():
            self.stdout.write(json.dumps({'status':'NEEDS_MORE_DATA','reasons':['no_active_targets']})); return
        result=[]
        for target in targets:
            if o['action']=='report':
                result.append(report(target)); continue
            if o['action']=='reproduce':
                for run in EventExperimentRun.objects.filter(target=target).select_related('target__study'):
                    if reproduce(run)!=run.payload:
                        raise CommandError(f'Reproduction failed: {run.pk}')
                result.append({'target':target.pk,'status':'reproduced'}); continue
            start=dt(o['start']) if o['start'] else dt(timezone.now()).replace(minute=0,second=0,microsecond=0)
            end=dt(o['end']) if o['end'] else start+timedelta(hours=1)
            count=0
            while start<end:
                issue(target,start); count+=1; start+=timedelta(hours=1)
            result.append({'target':target.pk,'runs':count})
        if o['action']=='tick':
            from places.services.event_validation import monitor
            for study in HourlyStudy.objects.all():
                if study.state.get('event_promoted'): monitor(study)
        text=json.dumps(result,ensure_ascii=False,indent=2)
        if o['output']:
            path=Path(o['output']); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding='utf-8')
        else:
            self.stdout.write(text)
