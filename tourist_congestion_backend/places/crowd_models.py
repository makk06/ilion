"""Persisted evidence and derived estimates; imported by places.models."""
from django.db import models
from django.db.models import Q


class PlaceCrowdProfile(models.Model):
    place = models.OneToOneField('places.Place', on_delete=models.CASCADE, related_name='crowd_profile')
    profile = models.CharField(max_length=20, default='unknown')
    evidence = models.JSONField(default=dict)
    version = models.CharField(max_length=40, default='profiles-v1')
    grid_x = models.PositiveSmallIntegerField(null=True)
    grid_y = models.PositiveSmallIntegerField(null=True)
    opening_schedule = models.JSONField(default=dict, blank=True)
    last_requested_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)


class TransitObservation(models.Model):
    crowd_area = models.ForeignKey('places.CrowdArea', on_delete=models.CASCADE)
    mode = models.CharField(max_length=10)
    window_minutes = models.PositiveSmallIntegerField(default=30)
    observed_at = models.DateTimeField()
    fetched_at = models.DateTimeField()
    timestamp_quality = models.CharField(max_length=20, default='collection_only')
    arrivals_min = models.PositiveIntegerField()
    arrivals_max = models.PositiveIntegerField()
    departures_min = models.PositiveIntegerField(null=True)
    departures_max = models.PositiveIntegerField(null=True)
    fingerprint = models.CharField(max_length=64)
    raw_data = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('crowd_area', 'mode', 'window_minutes', 'observed_at'), name='unique_transit_window'),
            models.CheckConstraint(condition=Q(arrivals_min__lte=models.F('arrivals_max')), name='valid_transit_range'),
        ]
        indexes = [models.Index(fields=('crowd_area', 'mode', '-observed_at'))]


class WeatherSnapshot(models.Model):
    grid_x = models.PositiveSmallIntegerField()
    grid_y = models.PositiveSmallIntegerField()
    product = models.CharField(max_length=30)
    issued_at = models.DateTimeField()
    valid_at = models.DateTimeField()
    fetched_at = models.DateTimeField()
    values = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('grid_x', 'grid_y', 'product', 'issued_at', 'valid_at'), name='unique_weather_issue')]
        indexes = [models.Index(fields=('grid_x', 'grid_y', 'valid_at', '-issued_at'))]


class TourEvent(models.Model):
    external_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    start_date = models.DateField()
    end_date = models.DateField()
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    time_quality = models.CharField(max_length=20, default='date_only')
    size_weight = models.FloatField(default=0.5)
    size_evidence = models.TextField(blank=True)
    size_valid_until = models.DateField(null=True, blank=True)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField()
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(start_date__lte=models.F('end_date')), name='valid_event_dates')]
        indexes = [models.Index(fields=('active', 'end_date', 'start_date'))]


class CalendarDay(models.Model):
    date = models.DateField(unique=True)
    is_holiday = models.BooleanField(default=False)
    name = models.CharField(max_length=255, blank=True)
    holiday_run = models.PositiveSmallIntegerField(default=0)
    fetched_at = models.DateTimeField()


class HistoricalSample(models.Model):
    crowd_area = models.ForeignKey('places.CrowdArea', on_delete=models.CASCADE)
    metric = models.CharField(max_length=30)
    bucket_at = models.DateTimeField()
    value = models.FloatField()
    sample_count = models.PositiveSmallIntegerField()
    quality = models.FloatField(default=1)
    context = models.JSONField(default=dict)
    available_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=('crowd_area', 'metric', 'bucket_at'), name='unique_historical_bucket')]
        indexes = [models.Index(fields=('crowd_area', 'metric', 'bucket_at'))]


class HistoricalBaseline(models.Model):
    crowd_area = models.ForeignKey('places.CrowdArea', on_delete=models.CASCADE)
    metric = models.CharField(max_length=30)
    weekday = models.SmallIntegerField()  # -1 denotes the all-hours distribution
    hour = models.SmallIntegerField()
    version = models.CharField(max_length=40)
    median = models.FloatField()
    mad = models.FloatField(default=0)
    distribution = models.JSONField(default=list)
    sample_days = models.PositiveSmallIntegerField()
    coverage = models.FloatField()
    context = models.JSONField(default=dict)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('crowd_area', 'metric', 'weekday', 'hour', 'version'), name='unique_baseline_version')]
        indexes = [models.Index(fields=('crowd_area', 'version', 'metric')),
                   models.Index(fields=('crowd_area','metric','-period_end'))]


class CrowdEstimate(models.Model):
    place = models.OneToOneField('places.Place', on_delete=models.CASCADE, related_name='crowd_snapshot')
    payload = models.JSONField(default=dict)
    state = models.JSONField(default=dict)
    estimated_at = models.DateTimeField()
    refresh_after = models.DateTimeField()
    model_version = models.CharField(max_length=40)


class CollectorState(models.Model):
    provider = models.CharField(max_length=30)
    key = models.CharField(max_length=255)
    cursor = models.JSONField(default=dict)
    next_run_at = models.DateTimeField(null=True)
    last_success_at = models.DateTimeField(null=True)
    failures = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=100, blank=True)
    lease_until = models.DateTimeField(null=True)
    lease_owner = models.CharField(max_length=36, blank=True)
    budget_date = models.DateField(null=True)
    calls = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('provider', 'key'), name='unique_collector_key')]


class ForecastEvaluation(models.Model):
    """Frozen inputs/forecasts for forward-only, independently observed evaluation."""
    place = models.ForeignKey('places.Place', on_delete=models.CASCADE)
    crowd_area = models.ForeignKey('places.CrowdArea', on_delete=models.CASCADE)
    issued_at = models.DateTimeField()
    valid_at = models.DateTimeField()
    hours_ahead = models.PositiveSmallIntegerField()
    predicted_score = models.FloatField()
    baseline_score = models.FloatField()
    persistence_score = models.FloatField()
    distribution = models.JSONField(default=list)
    actual_score = models.FloatField(null=True)
    model_version = models.CharField(max_length=40)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('place', 'issued_at', 'hours_ahead'), name='unique_forecast_evaluation')]
