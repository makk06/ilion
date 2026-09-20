import os
import time

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_GET


@require_GET
@sensitive_variables('vworld_api_key')
def client_config(request):
    """Return public runtime settings needed to initialize the client."""
    vworld_api_key = os.environ.get('VWORLD_API_KEY', '').strip()
    if not vworld_api_key:
        response = JsonResponse({
            'success': False,
            'data': None,
            'message': '지도 설정을 일시적으로 불러올 수 없습니다.',
        }, status=503)
    else:
        response = JsonResponse({
            'success': True,
            'data': {'vworld_api_key': vworld_api_key},
            'message': '',
        })
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
def healthz(request):
    if not settings.DEBUG:
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 FROM django_migrations LIMIT 1')
            if settings.DATA_WORKER_ENABLED:
                age = time.time() - (settings.STORAGE_DIR / '.data-worker-heartbeat').stat().st_mtime
                if age > 180:
                    return JsonResponse({'status': 'unavailable'}, status=503)
        except (DatabaseError, OSError):
            return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})
