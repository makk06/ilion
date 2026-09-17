"""Verified event advice, independent of crowd scores and promotion."""
from datetime import timedelta
from django.utils import timezone
from places.models import TourEvent, MeanEvidence, CollectorState, EventTargetLink
from .hourly_forecast import dt
from .hourly_store import digest


def source_status(old, published):
    if old and old.status == 'cancelled':
        return 'cancelled'
    return 'scheduled' if published else 'unpublished'


def archive_event(event, received):
    from .mean_archive import append
    fields = ('external_id', 'name', 'source', 'source_url', 'source_modified_at', 'start_date',
              'end_date', 'starts_at', 'ends_at', 'time_quality', 'status', 'family', 'edition',
              'latitude', 'longitude', 'active')
    payload = {k: getattr(event, k) for k in fields}
    payload = {k: v.isoformat() if hasattr(v, 'isoformat') else v for k, v in payload.items()}
    fingerprint = digest(payload)
    stored_hash = TourEvent.objects.filter(pk=event.pk).values_list('content_hash', flat=True).first()
    if fingerprint == stored_hash:
        return
    append('event', event.external_id, received, payload)
    TourEvent.objects.filter(pk=event.pk).update(content_hash=fingerprint,
        first_seen_at=event.first_seen_at or received, changed_at=received, detail_pending=event.source == 'tour_api')


def snapshots(kind, cutoff, *, watermark=None):
    query = MeanEvidence.objects.filter(kind=kind, received_at__lte=cutoff)
    if watermark is not None:
        query = query.filter(id__lte=watermark)
    found = {}
    for r in query.order_by('received_at', 'id'):
        found[r.key] = {**r.payload, 'received_at': r.received_at.isoformat(), 'version_id': r.id}
    return found


def event_rows(target, cutoff, watermark=None):
    events = snapshots('event', cutoff, watermark=watermark)
    links = snapshots('event_link', cutoff, watermark=watermark)
    result = []
    for link in links.values():
        if link['target_id'] != target.pk or not link['verified']:
            continue
        e = events.get(link['event_id'])
        if not e or e.get('status') != 'scheduled':
            continue
        result.append({**e, 'provider': target.study.provider, 'external_id': target.external_id,
            'metric': target.metric, 'event_id': link['event_id'], 'verified': True,
            'starts_at': link.get('starts_at') or e.get('starts_at'),
            'ends_at': link.get('ends_at') or e.get('ends_at'),
            'received_at': max(dt(e['received_at']), dt(link['received_at'])).isoformat(), 'link_version': link['version_id']})
    return result


def overlaps(e, at):
    at = dt(at)
    if e.get('starts_at') and e.get('ends_at'):
        return dt(e['starts_at']) <= at < dt(e['ends_at'])
    return e['start_date'] <= at.date().isoformat() <= e['end_date']


def context(events, at, now, checked):
    notices = []
    for e in events:
        if not overlaps(e, at):
            continue
        timed = bool(e.get('starts_at') and e.get('ends_at'))
        notices.append({k: e.get(k) for k in ('event_id', 'name', 'source', 'source_url',
            'start_date', 'end_date', 'starts_at', 'ends_at', 'received_at')} | {
            'time_quality': 'verified_time' if timed else 'date_only',
            'reason': 'event_overlap' if timed else 'event_time_unknown',
            'message': '해당 시각 행사 예정 · 평소보다 붐빌 수 있어요' if timed else '이날 행사 예정 · 진행 시간 미확인'})
    return {'valid_at': dt(at).isoformat(), 'checked_at': checked.isoformat() if checked else None,
        'collection_status': 'fresh' if checked and now-checked < timedelta(hours=3) else 'delayed',
        'coverage': 'registered_events_only', 'events': notices}


def attach_context(results, now):
    # Batch the event/link reads; API requests never access external providers.
    from places.hourly_models import HourlyTarget
    events, links = {}, {}
    for row in MeanEvidence.objects.filter(kind__in=['event', 'event_link'], received_at__lte=now).order_by('received_at','id'):
        destination = events if row.kind == 'event' else links
        destination[row.key] = {**row.payload, 'received_at':row.received_at.isoformat(), 'version_id':row.id}
    state = CollectorState.objects.filter(provider='tour_api', key='events').first()
    checked = state.last_success_at if state else None
    by_place = {}
    for target in HourlyTarget.objects.filter(active=True).select_related('study'):
        matched = []
        for link in links.values():
            e = events.get(link['event_id'])
            if link['target_id'] == target.pk and link['verified'] and e and e.get('status') == 'scheduled':
                matched.append({**e, 'event_id': link['event_id'],
                    'starts_at': link.get('starts_at') or e.get('starts_at'),
                    'ends_at': link.get('ends_at') or e.get('ends_at')})
        for p in target.mapping.get('place_ids', []):
            by_place.setdefault(p, {}).update({e['event_id']: e for e in matched})
    for p, payload in results.items():
        es = list(by_place.get(p, {}).values())
        payload['event_context'] = context(es, now, now, checked)
        payload['event_contexts'] = [context(es, dt(now).replace(minute=0, second=0, microsecond=0)+timedelta(hours=h), now, checked) for h in (1,2,3)]
        for f in payload.get('forecast', []):
            if f.get('valid_at'):
                f['event_context'] = context(es, f['valid_at'], now, checked)
    return results


def prune(now):
    from django.db.models import Max
    from places.models import EventExperimentRun
    cutoff=now-timedelta(days=400)
    latest=MeanEvidence.objects.filter(kind__in=['event','event_link']).values('kind','key').annotate(last=Max('id')).values_list('last',flat=True)
    MeanEvidence.objects.filter(kind__in=['event','event_link'],received_at__lt=cutoff).exclude(id__in=list(latest)).delete()
    EventExperimentRun.objects.filter(issued_at__lt=now-timedelta(days=300)).delete()
