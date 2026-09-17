"""Frozen independent shadow runs. Event models are never enabled by a legacy PASS."""
from datetime import timedelta
from django.db.models import Max
from django.utils import timezone
from places.models import MeanEvidence, EventExperimentRun
from places.hourly_models import HourlyObservation
from .hourly_store import calendar, digest
from .hourly_forecast import dt, samples
from .event_context import event_rows
from .event_forecast import predict_events, effect, VERSION, PARAMETERS


def inputs(target, at, frozen=None):
    at = dt(at)
    upper = frozen or {
        'observation_max': HourlyObservation.objects.aggregate(v=Max('pk'))['v'] or 0,
        'evidence_max': MeanEvidence.objects.aggregate(v=Max('pk'))['v'] or 0}
    start = at.replace(hour=0)-timedelta(days=30,minutes=15) if frozen else at-timedelta(days=400)
    observations = list(HourlyObservation.objects.filter(target=target, id__lte=upper['observation_max'],
        observed_at__gte=start, observed_at__lte=at, received_at__lte=at).order_by('received_at', 'id').values('id', 'observed_at', 'received_at', 'value'))
    for r in observations:
        for k in ('observed_at', 'received_at'):
            r[k] = dt(r[k]).isoformat()
    days = upper.get('calendar')
    if days is None:
        days = calendar(at, start)
    data = {'provider': target.study.provider, 'external_id': target.external_id, 'metric': target.metric,
            'observations': observations, 'calendar': days}
    families=upper.get('allowed_families') if frozen else target.study.state.get('event_contract',{}).get('families',{}).get(str(target.pk))
    if families is not None:
        data['allowed_families']=families
    events = frozen['events'] if frozen else event_rows(target, at, upper['evidence_max'])
    if frozen:
        effects = frozen['event_effects']
    else:
        points = samples(data, at)
        effects = {}
        for h in (0,1,2,3):
            t=at+timedelta(hours=h)
            value, reason, editions=effect(data,points,events,t,at)
            effects[t.isoformat()]={'value':value,'reason':reason,'editions':editions}
        # Freeze compact derived event evidence rather than requiring 700 days of raw history.
        from .event_rules import overlaps
        events=[e for e in events if any(overlaps(e,at+timedelta(hours=h)) for h in (0,1,2,3))]
    data['event_effects']=effects
    cutoff_start=at.replace(hour=0)-timedelta(days=30,minutes=15)
    data['observations']=[r for r in data['observations'] if dt(r['observed_at'])>=cutoff_start]
    metadata = {**upper, 'calendar': days, 'events':events, 'event_effects':effects,
                'hash': digest([data, events]), 'cutoff': at.isoformat()}
    if families is not None:
        metadata['allowed_families']=families
    if frozen and metadata != frozen:
        raise ValueError('Event experiment evidence expired or changed')
    return data, events, metadata


def issue(target, at, now=None):
    at, now = dt(at), dt(now or timezone.now())
    if at > now:
        raise ValueError('Cannot issue in the future')
    old = EventExperimentRun.objects.filter(target=target, issued_at=at, version=VERSION).first()
    if old:
        return old
    data, events, metadata = inputs(target, at)
    result = predict_events(data, at, events)
    # Real shadow means this hour was actually computed before its first target time.
    mode = 'shadow' if now < at+timedelta(hours=1) else 'retrospective'
    return EventExperimentRun.objects.get_or_create(target=target, issued_at=at, version=VERSION,
        defaults={'inputs': metadata, 'payload': result, 'mode': mode})[0]


def reproduce(run):
    data, events, _ = inputs(run.target, run.issued_at, run.inputs)
    return predict_events(data, run.issued_at, events)


def report(target):
    from .mean_validation import metrics
    from .hourly_decisions import percentile, assess_decisions
    from .event_forecast import history
    runs = list(EventExperimentRun.objects.filter(target=target, version=VERSION).order_by('issued_at'))
    rows = []
    for run in runs:
        data, _, _ = inputs(target, run.issued_at, run.inputs)
        values = sorted(r['value'] for r in history(samples(data, dt(run.issued_at)), run.issued_at).values())
        for f in run.payload:
            at = dt(f['valid_at'])
            raw = list(HourlyObservation.objects.filter(target=target, observed_at__gte=at-timedelta(minutes=15),
                observed_at__lte=at, received_at__lte=at).values('id','observed_at','received_at','value'))
            truth = samples({'observations': raw}, at).get(at)
            actual = truth['value'] if truth else None
            row = {'area_id': target.pk, 'provider': target.study.provider, 'external_id': target.external_id,
                'metric': target.metric, 'scope': target.scope, 'issued_at': f['issued_at'], 'valid_at': f['valid_at'],
                'hours_ahead': f['hours_ahead'], 'population': f['value'], 'arithmetic': f['comparisons']['arithmetic'],
                'unadjusted': f['unadjusted_value'], 'actual': actual, 'mode': run.mode, 'event_reason': f['event_reason'],
                'decision_contract_version': 'relative-choice-v2',
                'decision_scores': {k: percentile(values,v) for k,v in {'population': f['value'], 'arithmetic': f['comparisons']['arithmetic'], 'actual': actual}.items()},
                'tags': ['event'] if f['event_reason']!='no_registered_event' else ['no_registered_event']}
            row['decision_scores']['unadjusted']=percentile(values,f['unadjusted_value'])
            from .event_rules import overlaps
            active=[e for e in run.inputs.get('events',[]) if overlaps(e,at)]
            row['event_family']=active[0].get('family') if len(active)==1 else None
            row['event_edition']=active[0].get('edition') if len(active)==1 else None
            rows.append(row)
    paired = [r for r in rows if all(r[k] is not None for k in ('actual', 'population','arithmetic','unadjusted'))]
    training = list(HourlyObservation.objects.filter(target=target).order_by('observed_at').values('id','observed_at','received_at','value'))
    first = dt(training[0]['observed_at']) if training else None
    initial = [r['value'] for t,r in samples({'observations':training}, first+timedelta(days=56)).items() if t < first+timedelta(days=56)] if first else []
    scale = sum(initial)/len(initial) if initial else 0
    scales = {str(target.pk): scale} if scale > 0 else {}
    def measured(rs, key):
        return metrics(rs, key, scales, {}) if scale > 0 else {'status':'NEEDS_MORE_DATA', 'reason':'zero_or_missing_training_mean'}
    return {'status': 'NEEDS_MORE_DATA', 'decision': 'event_promotion_blocked', 'version': VERSION,
        'provider': target.study.provider, 'metric': target.metric, 'parameters': PARAMETERS,
        'reasons': ['independent_selection_holdout_and_14_day_shadow_required'],
        'planned': len(rows), 'truth_count': sum(r['actual'] is not None for r in rows),
        'prediction_count': sum(r['population'] is not None for r in rows), 'common_pairs': len(paired),
        'metrics': {k: measured(paired, k) for k in ('population','arithmetic','unadjusted')},
        'slices': {tag: {k: measured([r for r in paired if tag in r['tags']], k) for k in ('population','arithmetic','unadjusted')} for tag in ('event','no_registered_event')},
        'usability': assess_decisions(paired, {}, [target.pk]), 'rows': rows}
