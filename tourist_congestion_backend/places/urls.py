from django.urls import path

from places.views import place_detail, place_list


urlpatterns = [
    path('places', place_list, name='place-list'),
    path('places/<int:place_id>', place_detail, name='place-detail'),
]
