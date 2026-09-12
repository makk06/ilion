from django.urls import path

from places.views import nearby_places, place_detail, place_list, place_regions


urlpatterns = [
    path('places', place_list, name='place-list'),
    path('places/regions', place_regions, name='place-regions'),
    path('places/nearby', nearby_places, name='place-nearby'),
    path('places/<int:place_id>', place_detail, name='place-detail'),
]
