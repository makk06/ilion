"""Server-only VWorld credentials; clients receive image bytes, never upstream URLs."""
import os
import requests
from django.http import HttpResponse
from django.views.decorators.http import require_GET
from django.views.decorators.debug import sensitive_variables


@require_GET
@sensitive_variables()
def vworld_tile(request, z, x, y):
    if not 0 <= z <= 19 or not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
        return HttpResponse(status=404)
    key = os.environ.get('VWORLD_API_KEY', '')
    if not key:
        return HttpResponse('Map unavailable', status=503)
    # Fixed host/layer and integer coordinates prevent arbitrary proxy requests.
    url = f'https://api.vworld.kr/req/wmts/1.0.0/{key}/Base/{z}/{y}/{x}.png'
    try:
        with requests.get(url, timeout=(4, 12), stream=True,
                          allow_redirects=False) as upstream:
            if upstream.status_code != 200:
                return HttpResponse('Map unavailable', status=502)
            chunks = []
            size = 0
            for chunk in upstream.iter_content(65536):
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    return HttpResponse('Map unavailable', status=502)
                chunks.append(chunk)
            payload = b''.join(chunks)
        # Never forward provider error text, headers, or redirects containing keys.
        if not payload.startswith(b'\x89PNG\r\n\x1a\n') or key.encode() in payload:
            return HttpResponse('Map unavailable', status=502)
        response = HttpResponse(payload, content_type='image/png')
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except Exception:
        # Exception messages from HTTP clients may contain the credential URL.
        return HttpResponse('Map unavailable', status=502)
