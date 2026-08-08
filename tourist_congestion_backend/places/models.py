from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Place(models.Model):
    class IndoorOutdoor(models.TextChoices):
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
    indoor_outdoor = models.CharField(max_length=7, choices=IndoorOutdoor)
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
