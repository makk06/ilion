import os
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from places.integrations.exceptions import ExternalAPIAuthError, ExternalAPIConfigurationError, ExternalAPIError, ExternalAPIQuotaError
from places.job_models import DataJob, ProviderCallBudget
from places.models import PlaceSource, WeatherForecast
from places.services.seoul_sync import SeoulCrowdSyncService
from places.services.tour_detail_sync import TourPlaceDetailSyncService
from places.services.tour_sync import TourPlaceSyncService
from places.services.weather import ISSUE_HOURS, KST, KMAForecastClient, latest_available_issue, save_forecast


class BudgetExceeded(RuntimeError):
    pass


LANE_SHARE = {'regular': .7, 'supplemental': .2, 'reserve': .1}
PROVIDER_ENV = {'tour_api': 'TOUR_API_DAILY_LIMIT', 'seoul': 'SEOUL_DAILY_LIMIT', 'kma': 'KMA_DAILY_LIMIT'}


def enqueue(kind, target_key, *, payload=None, lane='regular', window=None):
    if lane not in LANE_SHARE:
        raise ValueError('Invalid call budget lane')
    key = f'{kind}:{target_key}:{window or timezone.now().strftime("%Y%m%d")}'
    job, _ = DataJob.objects.get_or_create(
        dedupe_key=key,
        defaults={'kind': kind, 'target_key': target_key, 'payload': payload or {},
                  'lane': lane, 'run_after': timezone.now()},
    )
    return job


@transaction.atomic
def debit(provider, lane):
    daily_limit = int(os.environ.get(PROVIDER_ENV[provider], '0'))
    # Seoul's general Open API documents a per-request row cap, not a daily
    # call cap for citydata_ppltn. -1 keeps accounting without blocking calls.
    unlimited = provider == 'seoul' and daily_limit == -1
    lane_limit = int(daily_limit * LANE_SHARE[lane])
    today = timezone.localdate()
    counter, _ = ProviderCallBudget.objects.get_or_create(
        provider=provider, date=today, lane=lane,
    )
    if not unlimited and counter.used >= lane_limit:
        raise BudgetExceeded(f'{provider} {lane} daily call budget exhausted or unconfigured')
    ProviderCallBudget.objects.filter(pk=counter.pk).update(used=F('used') + 1)


@transaction.atomic
def claim_job():
    now = timezone.now()
    # A killed process is retried after its lease expires, keeping the page cursor.
    DataJob.objects.filter(status=DataJob.Status.RUNNING, leased_at__lt=now - timedelta(minutes=5)).update(
        status=DataJob.Status.PENDING, run_after=now, leased_at=None)
    job = DataJob.objects.filter(status=DataJob.Status.PENDING, run_after__lte=now).order_by('run_after', 'id').first()
    if job:
        job.status = DataJob.Status.RUNNING
        job.leased_at = now
        job.attempts += 1
        job.save(update_fields=['status', 'leased_at', 'attempts', 'updated_at'])
    return job


def _execute(job):
    if job.kind == 'tour_places':
        from places.integrations.tour_api import TourAPIClient
        client = TourAPIClient()
        debit('tour_api', job.lane)
        page_size = int(job.payload.get('page_size', 1000))
        page = client.fetch_places_page(
            page_number=job.cursor, page_size=page_size,
            modified_since=job.payload.get('modified_since'),
            region_code=job.payload.get('region_code'),
        )
        service = TourPlaceSyncService(None)
        allowed = {'관광지', '문화시설', '축제/공연/행사', '레포츠', '쇼핑', '음식점'}
        processed = 0
        for record in page.records:
            if record.category in allowed:
                service._sync_record(record)
                processed += 1
        job.processed += processed
        more = page.has_next and bool(page.records) and job.cursor < int(job.payload.get('max_pages') or 100000)
        return more
    if job.kind == 'tour_detail':
        from places.integrations.tour_api import TourAPIClient
        source = PlaceSource.objects.filter(pk=job.payload['source_id'], match_status='matched').select_related('place').first()
        if source:
            if not (source.raw_data.get('contenttypeid') or source.raw_data.get('contentTypeId')):
                return False
            include_intro = job.payload.get('include_intro', True)
            if not isinstance(include_intro, bool):
                raise ValueError('include_intro must be a boolean')
            client = TourAPIClient()
            # The common response already contains the description. Intro is
            # optional and billed as a separate request.
            debit('tour_api', job.lane)
            if include_intro:
                debit('tour_api', job.lane)
            result = TourPlaceDetailSyncService(client).sync([source], include_intro=include_intro)
            job.processed += result.processed
        return False
    if job.kind == 'seoul_crowd':
        from places.integrations.seoul_realtime import SeoulRealtimeClient
        client = SeoulRealtimeClient()
        debit('seoul', job.lane)
        result = SeoulCrowdSyncService(client).sync([job.target_key])
        job.processed += result.areas_processed
        return False
    if job.kind == 'weather':
        grid = tuple(job.payload['grid'])
        issue = timezone.datetime.fromisoformat(job.payload['issued_at'])
        now = timezone.now()
        if issue.utcoffset() is None or issue > now:
            raise ValueError('Weather issuance must be aware and already released')
        local_issue = issue.astimezone(KST)
        if local_issue.hour not in ISSUE_HOURS or any((local_issue.minute, local_issue.second, local_issue.microsecond)):
            raise ValueError('Weather issuance is not a scheduled base time')
        target_raw = job.payload.get('target_at')
        target_hour = None
        if target_raw:
            target = timezone.datetime.fromisoformat(target_raw)
            if target.utcoffset() is None:
                raise ValueError('Weather target must include an offset')
            target_hour = target.replace(minute=0, second=0, microsecond=0)
            current_issue = latest_available_issue(now, target_at=target)
            if issue > current_issue:
                raise ValueError('Weather issuance cannot cover the requested target')
            issue = current_issue
            if now - issue > timedelta(hours=settings.WEATHER_MAX_ISSUE_AGE_HOURS):
                return False
        else:
            current_issue = latest_available_issue(now)
            if issue > current_issue:
                raise ValueError('Weather issuance is not yet available')
            if issue < current_issue:
                issue = current_issue
        cached = WeatherForecast.objects.filter(
            source='kma_vilage', grid_x=grid[0], grid_y=grid[1], issued_at=issue,
        ).exclude(raw_data__dev_seed=True)
        if target_hour is not None:
            cached = cached.filter(target_at=target_hour)
        if cached.exists():
            return False
        client = KMAForecastClient()
        rows = client.fetch(grid, issue, lambda: debit('kma', job.lane))
        if target_hour is not None and not any(row[0] == target_hour for row in rows):
            raise ExternalAPIError('KMA forecast does not cover the requested target hour')
        job.processed += save_forecast(grid, issue, rows)
        return False
    raise ValueError('Unsupported job kind')


def run_one():
    job = claim_job()
    if job is None:
        return None
    try:
        more = _execute(job)
    except (BudgetExceeded, ExternalAPIQuotaError) as exc:
        job.status = DataJob.Status.PENDING
        job.error_code = type(exc).__name__
        tomorrow = timezone.localdate() + timedelta(days=1)
        job.run_after = timezone.make_aware(datetime.combine(tomorrow, time.min), timezone.get_current_timezone())
        job.attempts -= 1
    except (ExternalAPIConfigurationError, ExternalAPIAuthError) as exc:
        job.status = DataJob.Status.FAILED
        job.error_code = type(exc).__name__
        job.finished_at = timezone.now()
    except (ExternalAPIError, OSError, ValueError) as exc:
        job.error_code = type(exc).__name__
        if job.attempts <= 2:
            job.status = DataJob.Status.PENDING
            job.run_after = timezone.now() + timedelta(seconds=2 ** job.attempts)
        else:
            job.status = DataJob.Status.FAILED
            job.finished_at = timezone.now()
    else:
        job.error_code = ''
        if more:
            job.cursor += 1
            job.attempts = 0
            job.status = DataJob.Status.PENDING
            job.run_after = timezone.now()
        else:
            job.status = DataJob.Status.SUCCEEDED
            job.finished_at = timezone.now()
    job.leased_at = None
    job.save()
    return job
