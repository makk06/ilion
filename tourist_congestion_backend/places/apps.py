from django.apps import AppConfig


class PlacesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'places'

    def ready(self):
        from .services.mean_archive import install
        install()
