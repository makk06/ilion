"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from config.views import client_config, healthz, privacy_policy, terms_of_service
from config.map_tiles import vworld_tile
from config.test_dashboard import backend_test_dashboard
from places.demo_views import place_demo
from recommendations.views import RecommendationView

urlpatterns = [
    path('api/config', client_config, name='client-config'),
    path('api/maps/vworld/<int:z>/<int:x>/<int:y>.png', vworld_tile),
    path('healthz', healthz, name='healthz'),
    path('privacy', privacy_policy, name='privacy-policy'),
    path('terms', terms_of_service, name='terms-of-service'),
    path('test/backend/', backend_test_dashboard, name='backend-test-dashboard'),
    path('demo/', place_demo, name='place-demo'),
    path('api/', include('places.urls')),
    path('api/recommendations', RecommendationView.as_view(), name='recommendations'),
    path('admin/', admin.site.urls),
    path('api/', include('users.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
