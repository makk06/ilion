from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class EventTargetLink(models.Model):
    event = models.ForeignKey('places.TourEvent', on_delete=models.PROTECT)
    target = models.ForeignKey('places.HourlyTarget', on_delete=models.PROTECT)
    verified = models.BooleanField(default=False)
    evidence = models.TextField(blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(editable=False, default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'target'], name='unique_event_target')]

    def clean(self):
        if self.verified and not self.evidence.strip():
            raise ValidationError('검증 근거가 필요합니다.')
        if bool(self.starts_at) != bool(self.ends_at) or (self.starts_at and self.starts_at >= self.ends_at):
            raise ValidationError('시작·종료 시각을 함께 올바르게 입력하세요.')

    def save(self, *args, **kwargs):
        self.full_clean()
        self.checked_at = timezone.now()
        super().save(*args, **kwargs)
        from .services.mean_archive import append
        append('event_link', str(self.pk), self.checked_at, {
            'event_id': self.event.external_id, 'target_id': self.target_id,
            'provider': self.target.study.provider, 'external_id': self.target.external_id,
            'metric': self.target.metric, 'verified': self.verified, 'evidence': self.evidence,
            'starts_at': self.starts_at, 'ends_at': self.ends_at})


class EventExperimentRun(models.Model):
    target = models.ForeignKey('places.HourlyTarget', on_delete=models.PROTECT)
    issued_at = models.DateTimeField()
    computed_at = models.DateTimeField(auto_now_add=True)
    version = models.CharField(max_length=50)
    mode = models.CharField(max_length=16, default='retrospective')
    inputs = models.JSONField(default=dict)
    payload = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['target', 'issued_at', 'version'], name='unique_event_experiment')]
