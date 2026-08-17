from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class ExternalSource(models.TextChoices):
    TOUR_API = 'tour_api', 'Korea Tourism Organization TourAPI'
    SEOUL_REALTIME = 'seoul_realtime', 'Seoul Real-time Population'


class Place(models.Model):
    class IndoorOutdoor(models.TextChoices):
        UNKNOWN = 'unknown', 'Unknown'
        INDOOR = 'indoor', 'Indoor'
        OUTDOOR = 'outdoor', 'Outdoor'

    class OpenStatus(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'

    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    subcategory = models.CharField(max_length=100, null=True, blank=True)
    region_code = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    indoor_outdoor = models.CharField(
        max_length=7,
        choices=IndoorOutdoor,
        default=IndoorOutdoor.UNKNOWN,
    )
    open_status = models.CharField(
        max_length=6,
        choices=OpenStatus,
        null=True,
        blank=True,
    )
    avg_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class PlaceSource(models.Model):
    class MatchStatus(models.TextChoices):
        NEW = 'new', 'New'
        MATCHED = 'matched', 'Matched'
        MANUAL_REVIEW = 'manual_review', 'Manual review'
        INACTIVE = 'inactive', 'Inactive'

    place = models.ForeignKey(
        Place,
        on_delete=models.SET_NULL,
        related_name='sources',
        null=True,
        blank=True,
    )
    source = models.CharField(max_length=30, choices=ExternalSource)
    external_id = models.CharField(max_length=255)
    source_name = models.CharField(max_length=255, blank=True)
    source_category = models.CharField(max_length=100, blank=True)
    source_address = models.CharField(max_length=500, blank=True)
    source_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        null=True,
        blank=True,
    )
    source_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        null=True,
        blank=True,
    )
    match_status = models.CharField(
        max_length=20,
        choices=MatchStatus,
        default=MatchStatus.NEW,
    )
    raw_data = models.JSONField(default=dict)
    last_synced_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('source', 'external_id'),
                name='unique_place_source_external_id',
            ),
            models.CheckConstraint(
                condition=(
                    Q(match_status='matched', place__isnull=False)
                    | ~Q(match_status='matched')
                ),
                name='matched_place_source_has_place',
            ),
        ]
        indexes = [
            models.Index(fields=('source', 'match_status')),
        ]

    def __str__(self):
        return f'{self.source}:{self.external_id}'


class CrowdArea(models.Model):
    source = models.CharField(max_length=30, choices=ExternalSource)
    external_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    region_code = models.CharField(max_length=20, blank=True)
    raw_data = models.JSONField(default=dict)
    last_synced_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('source', 'external_id'),
                name='unique_crowd_area_external_id',
            ),
        ]

    def __str__(self):
        return self.name


class PlaceCrowdArea(models.Model):
    class MatchMethod(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        COORDINATE = 'coordinate', 'Coordinate'
        SOURCE = 'source', 'External source'

    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name='crowd_area_mappings',
    )
    crowd_area = models.ForeignKey(
        CrowdArea,
        on_delete=models.CASCADE,
        related_name='place_mappings',
    )
    match_method = models.CharField(
        max_length=20,
        choices=MatchMethod,
        default=MatchMethod.MANUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('place', 'crowd_area'),
                name='unique_place_crowd_area',
            ),
        ]

    def __str__(self):
        return f'{self.place} -> {self.crowd_area}'


class CrowdData(models.Model):
    class CrowdLevel(models.TextChoices):
        RELAXED = 'relaxed', 'Relaxed'
        NORMAL = 'normal', 'Normal'
        BUSY = 'busy', 'Busy'
        CROWDED = 'crowded', 'Crowded'
        UNKNOWN = 'unknown', 'Unknown'

    crowd_area = models.ForeignKey(
        CrowdArea,
        on_delete=models.CASCADE,
        related_name='observations',
    )
    observed_at = models.DateTimeField()
    crowd_level = models.CharField(
        max_length=20,
        choices=CrowdLevel,
        default=CrowdLevel.UNKNOWN,
    )
    crowd_message = models.TextField(blank=True)
    crowd_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=True,
        blank=True,
    )
    population_min = models.PositiveIntegerField(null=True, blank=True)
    population_max = models.PositiveIntegerField(null=True, blank=True)
    is_replaced = models.BooleanField(default=False)
    raw_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('crowd_area', 'observed_at'),
                name='unique_crowd_observation',
            ),
            models.CheckConstraint(
                condition=(
                    Q(population_min__isnull=True)
                    | Q(population_max__isnull=True)
                    | Q(population_min__lte=models.F('population_max'))
                ),
                name='crowd_population_range_is_valid',
            ),
        ]
        indexes = [
            models.Index(fields=('crowd_area', '-observed_at')),
        ]

    def __str__(self):
        return f'{self.crowd_area} at {self.observed_at}'
