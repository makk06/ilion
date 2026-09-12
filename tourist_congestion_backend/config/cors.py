import re

from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers


class CorsMiddleware:
    """Explicit production origins; loopback Flutter development ports in DEBUG."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin', '')
        allowed = origin in settings.CORS_ALLOWED_ORIGINS or (
            settings.DEBUG and re.fullmatch(r'https?://(localhost|127\.0\.0\.1)(:\d{1,5})?', origin)
        )
        if request.method == 'OPTIONS' and origin and allowed:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        patch_vary_headers(response, ['Origin'])
        if origin and allowed:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        return response
