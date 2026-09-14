from django.db import models


class DataJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    kind = models.CharField(max_length=30)
    target_key = models.CharField(max_length=120)
    dedupe_key = models.CharField(max_length=180, unique=True)
    lane = models.CharField(max_length=12, default='regular')
    status = models.CharField(max_length=12, choices=Status, default=Status.PENDING)
    payload = models.JSONField(default=dict)
    cursor = models.PositiveIntegerField(default=1)
    processed = models.PositiveIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    run_after = models.DateTimeField()
    leased_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=('status', 'run_after'))]


class ProviderCallBudget(models.Model):
    provider = models.CharField(max_length=30)
    date = models.DateField()
    lane = models.CharField(max_length=12)
    used = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=('provider', 'date', 'lane'), name='unique_provider_daily_lane',
        )]
