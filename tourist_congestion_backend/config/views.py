import os
import time

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_GET

from config import legal


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


@require_GET
def privacy_policy(request):
    """Public policy page linked from the store listing and the app."""
    if not legal.ACCESS_LOG_RETENTION:
        # 보관 기간을 모르는 채로 게시하면 처리방침 자체가 사실과 달라진다.
        return HttpResponse('개인정보 처리방침을 준비하고 있습니다.', status=503,
                            content_type='text/plain; charset=utf-8')
    return render(request, 'config/privacy_policy.html', legal.context())


@require_GET
def terms_of_service(request):
    return render(request, 'config/terms_of_service.html', legal.context())
