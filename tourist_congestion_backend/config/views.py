from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.conf import settings
from django.db import connection, DatabaseError
import time


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
