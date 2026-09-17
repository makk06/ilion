"""Typed append-only observations and shared, compact forecast inputs for v2."""
from django.db import models


class HourlyStudy(models.Model):
    provider = models.CharField(max_length=16)
    started_at = models.DateTimeField()
    config = models.JSONField(default=dict)
    state = models.JSONField(default=dict)


class HourlyTarget(models.Model):
    study = models.ForeignKey(HourlyStudy, on_delete=models.PROTECT, related_name='targets')
    external_id = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    metric = models.CharField(max_length=24)
    scope = models.CharField(max_length=30)
    mapping = models.JSONField(default=dict)
    priority = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=False)
    selected = models.BooleanField(default=False)
    promoted = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['study', 'external_id'], name='hourly_target_identity')]


class HourlyObservation(models.Model):
    target = models.ForeignKey(HourlyTarget, on_delete=models.PROTECT)
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)
    value = models.FloatField()
    fingerprint = models.CharField(max_length=64, unique=True)
    raw_path = models.CharField(max_length=255)
    raw_hash = models.CharField(max_length=64)
    details = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=['target', 'observed_at', 'received_at'], name='hourly_obs_lookup')]
        constraints = [models.CheckConstraint(condition=models.Q(value__gte=0), name='hourly_nonnegative')]


class HourlyRun(models.Model):
    target = models.ForeignKey(HourlyTarget, on_delete=models.PROTECT)
    issued_at = models.DateTimeField()
    computed_at = models.DateTimeField(auto_now_add=True)
    inputs = models.JSONField(default=dict)
    parameters = models.JSONField(default=dict)
    phase = models.CharField(max_length=16, default='shadow')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['target', 'issued_at'], name='hourly_run_identity')]
        indexes = [models.Index(fields=['target', '-issued_at'], name='hourly_latest_run')]


class HourlyForecast(models.Model):
    run = models.ForeignKey(HourlyRun, on_delete=models.CASCADE, related_name='forecasts')
    valid_at = models.DateTimeField()
    payload = models.JSONField(default=dict)
    actual = models.FloatField(null=True)
    actual_observed_at = models.DateTimeField(null=True)
    actual_received_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=16, default='pending')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run', 'valid_at'], name='hourly_forecast_identity')]
        indexes = [models.Index(fields=['status', 'valid_at'], name='hourly_pending_truth')]


class HourlyDaily(models.Model):
    target = models.ForeignKey(HourlyTarget, on_delete=models.PROTECT)
    date = models.DateField()
    payload = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['target', 'date'], name='hourly_daily_identity')]
