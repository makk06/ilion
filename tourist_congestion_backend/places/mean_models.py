from django.db import models


class MeanEvidence(models.Model):
    """Append-only source snapshots, isolated from legacy pruning."""
    kind = models.CharField(max_length=24)
    key = models.CharField(max_length=255)
    received_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    payload = models.JSONField()

    class Meta:
        indexes = [models.Index(fields=['kind', 'key', 'received_at'])]


class MeanStudy(models.Model):
    name = models.CharField(max_length=80, unique=True, default='area-mean-v1')
    started_at = models.DateTimeField()
    config = models.JSONField(default=dict)
    state = models.JSONField(default=dict)


class MeanPrediction(models.Model):
    study = models.ForeignKey(MeanStudy, on_delete=models.CASCADE)
    area_id = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    valid_at = models.DateTimeField()
    payload = models.JSONField()
    actual = models.FloatField(null=True)
    actual_received_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=24, default='pending')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['study', 'area_id', 'issued_at', 'valid_at'], name='unique_mean_prediction')]
        indexes = [models.Index(fields=['study', 'issued_at'])]
