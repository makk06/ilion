"""Provider-wide event selection contract and independent holdout/shadow gates."""
from datetime import timedelta
from statistics import mean
from django.utils import timezone
from places.hourly_models import HourlyObservation
from .hourly_forecast import dt, samples
from .hourly_store import digest
from .hourly_decisions import CONTRACT, assess_decisions
from .mean_validation import assess
from .event_experiment import report
from .event_forecast import PARAMETERS, VERSION
from .event_context import event_rows, overlaps


def targets(study):
    return list(study.targets.filter(active=True, selected=True).order_by('pk'))


def contract(study):
    c = study.state.get('event_contract', {})
    if (not c or c.get('hash') != digest({k:v for k,v in c.items() if k!='hash'})
            or c['decision'] != CONTRACT or c['model'] != VERSION or c['parameters'] != PARAMETERS
            or c['targets'] != [t.pk for t in targets(study)]):
        raise ValueError('Missing or changed event selection contract')
    return c


def evaluate(study, c, start, end, *, shadow=False):
    start, end = dt(start), dt(end)
    all_rows, excluded, edition_counts = [], 0, {}
    for target in targets(study):
        reports = report(target)
        stored = {(r['issued_at'],r['hours_ahead']):r for r in reports['rows'] if not shadow or r['mode']=='shadow'}
        es = event_rows(target, end)
        crossing = [e for e in es if e.get('starts_at') and e.get('ends_at') and
                    any(dt(e['starts_at']) < boundary < dt(e['ends_at']) for boundary in (start,end))]
        families=c.get('families',{}).get(str(target.pk),[])
        for family in families:
            editions = {e['edition'] for e in es if e.get('family')==family and e.get('edition') and e.get('starts_at') and e.get('ends_at')
                        and start <= dt(e['starts_at']) < dt(e['ends_at']) <= end}
            edition_counts[f'{target.pk}:{family}'] = len(editions)
        at = start
        while at < end:
            for h in (1,2,3):
                valid = at+timedelta(hours=h)
                if valid >= end or any(overlaps(e, valid) or overlaps(e, at) for e in crossing):
                    excluded += 1; continue
                r = stored.get((at.isoformat(),h))
                if r is None:
                    obs = list(HourlyObservation.objects.filter(target=target,observed_at__gte=valid-timedelta(minutes=15),
                        observed_at__lte=valid,received_at__lte=valid).values('id','observed_at','received_at','value'))
                    truth = samples({'observations':obs},valid).get(valid)
                    r = {'area_id':target.pk,'issued_at':at.isoformat(),'valid_at':valid.isoformat(),'hours_ahead':h,
                         'actual':truth['value'] if truth else None,'population':None,'arithmetic':None,'unadjusted':None}
                all_rows.append({**r,'reference':r.get(c['reference']),
                    'decision_scores':{**r.get('decision_scores',{}),'reference':r.get('decision_scores',{}).get(c['reference'])}})
            at += timedelta(hours=1)
    result = assess(all_rows, c['targets'], c['scales'], {}, reference='reference', required_areas=None,
                    date_field='valid_at', relative_peak_threshold=85)
    result['usability'] = assess_decisions(all_rows, {}, c['targets'])
    result['edition_counts'] = edition_counts
    result['excluded_boundary_pairs'] = excluded
    result['contract_hash'] = c['hash']
    result['evaluated_at'] = timezone.now().isoformat()
    result['start'],result['end'] = start.isoformat(),end.isoformat()
    problems = []
    if not edition_counts or any(n<1 for n in edition_counts.values()): problems.append('independent_event_edition_missing')
    for t in c['targets']:
        if not any(r['area_id']==t and r.get('event_reason')=='event_adjusted' for r in all_rows):
            problems.append('three_training_editions_missing:'+str(t))
    for key, cell in result.get('coverage_cells',{}).items():
        if any(cell[k]<.9 for k in ('provided_rate','label_rate','paired_rate')): problems.append('coverage:'+key)
    if result['usability']['guidance']['status'] != 'PASS': problems.append('decision_guidance_not_passed')
    if result['status'] == 'PASS' and problems: result['status']='NEEDS_MORE_DATA'
    result['reasons'] += problems
    return result


def freeze(study, selection_start, now=None):
    now=dt(now or timezone.now()); start=dt(selection_start); end=start+timedelta(days=14)
    if study.state.get('event_contract'): raise ValueError('Event contract already frozen; use a new study for changes')
    if now < end: raise ValueError('Selection period is incomplete')
    ts=targets(study)
    if not ts: raise ValueError('No fixed selected targets')
    scales={}
    for t in ts:
        obs=list(HourlyObservation.objects.filter(target=t, observed_at__gte=start-timedelta(days=56),
            observed_at__lt=start,received_at__lte=start).values('id','observed_at','received_at','value'))
        sampled=samples({'observations':obs},start)
        if len({t.date() for t in sampled})<56: raise ValueError('56 initial training dates are required')
        values=[r['value'] for r in sampled.values()]
        if not values or mean(values)<=0: raise ValueError('Missing or zero training mean')
        scales[str(t.pk)]=mean(values)
    # Same pairs, equal target/horizon weighting for the reference choice.
    rs=[r for t in ts for r in report(t)['rows'] if start<=dt(r['issued_at']) and dt(r['valid_at'])<end
        and all(r.get(k) is not None for k in ('arithmetic','unadjusted','population','actual'))]
    def score(key):
        cells=[[abs(r[key]-r['actual'])/scales[str(t.pk)] for r in rs if r['area_id']==t.pk and r['hours_ahead']==h] for t in ts for h in (1,2,3)]
        return mean(mean(v) for v in cells) if all(cells) else float('inf')
    reference=min(('arithmetic','unadjusted'),key=score)
    # Start holdout strictly after freezing, never retroactively approve an inspected interval.
    holdout=now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    c={'model':VERSION,'parameters':PARAMETERS,'decision':CONTRACT,'targets':[t.pk for t in ts],
       'scales':scales,'reference':reference,'selection_start':start.isoformat(),'selection_end':end.isoformat(),
       'frozen_at':now.isoformat(),'holdout_start':holdout.isoformat()}
    c['families']={str(t.pk):sorted({r['event_family'] for r in rs if r['area_id']==t.pk and r.get('event_family') and r.get('event_reason')=='event_adjusted'}) for t in ts}
    c['hash']=digest(c)
    selection=evaluate(study,c,start,end)
    study.state={**study.state,'event_contract':c,'event_selection':selection,'event_promoted':False}
    study.save(update_fields=['state'])
    return selection


def validate(study, *, shadow=False, now=None):
    now=dt(now or timezone.now()); c=contract(study)
    if study.state.get('event_selection',{}).get('status')!='PASS':
        raise ValueError('Event selection did not pass')
    start=dt(c['holdout_start'])+timedelta(days=14 if shadow else 0); end=start+timedelta(days=14)
    if now<end: raise ValueError('Evaluation period incomplete')
    if shadow and study.state.get('event_holdout',{}).get('status')!='PASS': raise ValueError('Holdout did not pass')
    result=evaluate(study,c,start,end,shadow=shadow)
    study.state={**study.state, 'event_shadow' if shadow else 'event_holdout':result}
    study.save(update_fields=['state']); return result


def promotion_allowed(study):
    try: c=contract(study)
    except ValueError: return False
    return all(study.state.get(k,{}).get('status')=='PASS' and study.state[k].get('contract_hash')==c['hash']
               for k in ('event_selection','event_holdout','event_shadow'))


def adapt(results, now):
    from places.hourly_models import HourlyStudy
    from places.models import EventExperimentRun
    from .hourly_decisions import relative_label
    from .crowd_estimator import level
    hour=dt(now).replace(minute=0,second=0,microsecond=0)
    for study in HourlyStudy.objects.all():
        if not study.state.get('event_promoted') or not promotion_allowed(study): continue
        ranking=all(study.state[k]['usability']['ranking']['status']=='PASS' for k in ('event_selection','event_holdout','event_shadow'))
        for target in targets(study):
            if not target.promoted: continue
            run=EventExperimentRun.objects.filter(target=target,issued_at=hour,version=VERSION,mode='shadow').first()
            if not run: continue
            for p in target.mapping.get('place_ids',[]):
                if p not in results: continue
                for old in results[p].get('forecast',[]):
                    if old.get('provider')!=study.provider or old.get('external_id')!=target.external_id: continue
                    new=next((f for f in run.payload if f['valid_at']==old.get('valid_at')),None)
                    if not new or new['value'] is None: continue
                    allowed=set(study.state['event_contract']['families'].get(str(target.pk),[]))
                    involved={e.get('family') for e in run.inputs.get('events',[]) if overlaps(e,hour) or overlaps(e,dt(new['valid_at']))}
                    if not involved.issubset(allowed): continue
                    old.update(new)
                    old.update(relative_label=relative_label(new['crowd_score']),crowd_level=level(new['crowd_score'])[0],
                        ranking_eligible=ranking,normalization='within_target_empirical_percentile',guidance_eligible=True,
                        population=new['value'] if target.metric=='population_count' else None,
                        area_population=new['value'] if target.metric=='population_count' else None)
    return results


def monitor(study, now=None):
    now=dt(now or timezone.now()); date=now.date().isoformat()
    previous=study.state.get('event_monitor',{})
    if previous.get('date')==date: return previous
    ts=targets(study)
    rows=[r for t in ts for r in report(t)['rows'] if now-timedelta(days=7)<=dt(r['valid_at'])<now and r['mode']=='shadow']
    paired=[r for r in rows if all(r.get(k) is not None for k in ('population','arithmetic','actual'))]
    sufficient=bool(ts) and all(sum(r['area_id']==t.pk and r['hours_ahead']==h for r in paired)>=100 for t in ts for h in (1,2,3))
    decisions=assess_decisions(paired,{},[t.pk for t in ts],min_days=7)
    bad=decisions['guidance']['status']=='FAIL'
    if sufficient:
        for t in ts:
            for h in (1,2,3):
                cell=[r for r in paired if r['area_id']==t.pk and r['hours_ahead']==h]
                bad |= mean(abs(r['population']-r['actual']) for r in cell)>1.1*mean(abs(r['arithmetic']-r['actual']) for r in cell)
    consecutive=previous.get('date')==(now.date()-timedelta(days=1)).isoformat()
    streak=(previous.get('streak',0) if consecutive else 0)+1 if sufficient and bad else 0
    result={'date':date,'streak':streak,'sufficient':sufficient,'regressed':bad}
    study.state={**study.state,'event_monitor':result}
    if streak>=3: study.state['event_promoted']=False
    study.save(update_fields=['state']); return result
