"""Versioned evidence; importing old records never invents earlier availability."""
import hashlib
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_save
from django.utils import timezone
from places.models import CrowdData, WeatherSnapshot, TourEvent, CalendarDay, MeanEvidence


def append(kind, key, received_at, payload):
    payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    encoded = json.dumps([kind, str(key), received_at.isoformat(), payload], sort_keys=True).encode()
    return MeanEvidence.objects.get_or_create(fingerprint=hashlib.sha256(encoded).hexdigest(), defaults={
        'kind': kind, 'key': str(key), 'received_at': received_at, 'payload': payload})[0]


def capture(sender, instance, raw=False, **kwargs):
    if raw:
        return
    row = instance
    received = getattr(row, 'fetched_at', None) or getattr(row, 'created_at', None) or timezone.now()
    if sender == CrowdData:
        append('population', row.crowd_area_id, received, {
            'at': row.observed_at, 'received_at': received, 'min': row.population_min,
            'max': row.population_max, 'replaced': row.is_replaced,
            'demo': any(row.raw_data.get(k) for k in ('is_demo', '_is_demo', 'demo', 'dev_seed')),
            'provider': row.raw_data.get('_provider', 'unknown')})
    elif sender == WeatherSnapshot:
        append('weather', f'{row.grid_x},{row.grid_y}', received, {
            'at': row.valid_at, 'issued_at': row.issued_at, 'received_at': received,
            'product': row.product, **row.values})
    elif sender == CalendarDay:
        append('calendar', row.date.isoformat(), received, {
            'date': row.date.isoformat(), 'is_holiday': row.is_holiday, 'received_at': received})
    elif sender == TourEvent:
        from .event_context import archive_event
        archive_event(row, received)


def install():
    for model in (CrowdData, WeatherSnapshot, TourEvent, CalendarDay):
        post_save.connect(capture, sender=model, dispatch_uid='mean_archive_' + model.__name__)


def backfill():
    counts = {}
    for model in (CrowdData, WeatherSnapshot, TourEvent, CalendarDay):
        count = 0
        for row in model.objects.iterator():
            capture(model, row)
            count += 1
        counts[model.__name__] = count
    return counts
