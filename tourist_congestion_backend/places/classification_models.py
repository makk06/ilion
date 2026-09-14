from django.db import models
from django.utils import timezone


class PlaceClassificationEvidence(models.Model):
    """Evidence for a description-based label; no full source text is copied."""

    place = models.OneToOneField('places.Place', on_delete=models.CASCADE,
                                 related_name='classification_record')
    label = models.CharField(max_length=7)
    method = models.CharField(max_length=24)
    version = models.CharField(max_length=24)
    input_hash = models.CharField(max_length=64)
    quote = models.CharField(max_length=255)
    span_start = models.PositiveIntegerField()
    span_end = models.PositiveIntegerField()
    evidence_quotes = models.JSONField(default=list)
    primary_activity = models.CharField(max_length=120, blank=True)
    scope = models.CharField(max_length=24, blank=True)
    ancillary_note = models.CharField(max_length=255, blank=True)
    rationale = models.CharField(max_length=255, blank=True)
    weather_exposure = models.CharField(max_length=7, blank=True)
    weather_activity = models.CharField(max_length=120, blank=True)
    weather_reason = models.CharField(max_length=255, blank=True)
    previous_label = models.CharField(max_length=7, blank=True)
    previous_source = models.CharField(max_length=30, blank=True)
    model = models.CharField(max_length=40, blank=True)
    classified_at = models.DateTimeField(default=timezone.now)


class PlaceClassificationAttempt(models.Model):
    """One opt-in Luna attempt per place/input/version, including failed attempts."""

    place = models.ForeignKey('places.Place', on_delete=models.CASCADE,
                              related_name='classification_attempts')
    input_hash = models.CharField(max_length=64)
    model = models.CharField(max_length=40)
    status = models.CharField(max_length=24, default='reserved')
    error_code = models.CharField(max_length=40, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    proposal = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=('place', 'input_hash', 'model'), name='unique_place_classification_attempt',
        )]


class PlaceWeatherExposure(models.Model):
    """Versioned offline weather profile, distinct from indoor/outdoor labels."""

    place = models.OneToOneField('places.Place', on_delete=models.CASCADE,
                                 related_name='weather_exposure_record')
    level = models.CharField(max_length=7, default='unknown')
    activity = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=40)
    reason = models.CharField(max_length=255)
    conflict = models.BooleanField(default=False)
    conflict_reason = models.CharField(max_length=255, blank=True)
    type_code = models.CharField(max_length=10, blank=True)
    type_name = models.CharField(max_length=100, blank=True)
    factor = models.FloatField(default=0)
    version = models.CharField(max_length=24)
    input_hash = models.CharField(max_length=64)
    classified_at = models.DateTimeField(default=timezone.now)
