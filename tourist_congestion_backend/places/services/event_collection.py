from datetime import timedelta
from django.db.models import Exists, OuterRef
from places.models import TourEvent, EventTargetLink
from places.integrations.exceptions import ExternalAPIError
from .input_sync import save_event
from .hourly_forecast import dt


def collect_page(client, state, now):
    page = state.cursor.get('page', 1)
    started = state.cursor.get('started_at', now.isoformat())
    watermark = state.cursor.get('watermark')
    if watermark:
        result = client.fetch_places_page(page_number=page, content_type_id='15',
            modified_since=(dt(watermark)-timedelta(days=1)).strftime('%Y%m%d'))
        if result.page_number != page:
            raise ExternalAPIError('Incorrect event page')
        items, total = [r.raw_data for r in result.records], result.total_count
    else:
        items, total = client.fetch_events_page(page_number=page)
    if len(items) < min(100, max(0, total-(page-1)*100)):
        raise ExternalAPIError('Incomplete event page')
    invalid = state.cursor.get('invalid', 0)
    completed = set(state.cursor.get('page_done', []))
    state.cursor.update(page=page, started_at=started, watermark=watermark)
    for item in items:
        identity = str(item.get('contentid')) + ':' + str(item.get('modifiedtime',''))
        if identity in completed:
            continue
        if watermark and 'eventstartdate' not in item:
            # Sync lists omit event dates. Retrieve the intro before advancing this page.
            record = client.fetch_place_detail(str(item['contentid']), '15')
            item = {**item, **record.raw_data.get('common', {}), **record.raw_data.get('intro', {})}
        invalid += int(not save_event(item, now))
        completed.add(identity)
        state.cursor.update(page_done=sorted(completed), invalid=invalid)
    if page*100 < total:
        state.cursor = {'page': page+1, 'started_at': started, 'watermark': watermark, 'invalid': invalid}
        return False
    state.cursor = {'watermark': started, 'coverage': max(0, 1-invalid/max(1,total))}
    return True


def collect_details(client, state, now):
    active = EventTargetLink.objects.filter(event_id=OuterRef('pk'), target__active=True)
    pending = TourEvent.objects.filter(source='tour_api', detail_pending=True).annotate(
        priority=Exists(active)).order_by('-priority', 'fetched_at', 'pk')[:5]
    for event in pending:
        record = client.fetch_place_detail(event.external_id, '15')
        item = {**event.raw_data, **record.raw_data.get('common', {}), **record.raw_data.get('intro', {}), 'contentid': event.external_id}
        if not save_event(item, now):
            raise ExternalAPIError('Invalid event detail')
        TourEvent.objects.filter(pk=event.pk).update(detail_pending=False)
    return not TourEvent.objects.filter(source='tour_api', detail_pending=True).exists()
