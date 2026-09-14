from django.db import models


class WeatherForecast(models.Model):
    """One KMA forecast target with independent issuance, target, and fetch times."""

    source = models.CharField(max_length=30, default='kma_vilage')
    grid_x = models.PositiveSmallIntegerField()
    grid_y = models.PositiveSmallIntegerField()
    issued_at = models.DateTimeField()
    target_at = models.DateTimeField()
    precipitation_type = models.PositiveSmallIntegerField(null=True, blank=True)
    temperature_c = models.FloatField(null=True, blank=True)
    wind_mps = models.FloatField(null=True, blank=True)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=('source', 'grid_x', 'grid_y', 'issued_at', 'target_at'),
            name='unique_weather_forecast_target',
        )]
        indexes = [models.Index(fields=('grid_x', 'grid_y', 'target_at', '-issued_at'))]
