import time

from django.db import connection
from django.http import JsonResponse

import redis
import requests


def health_check(request):
    """Health check endpoint for monitoring and load balancers."""
    checks = {}
    healthy = True

    # Database check
    try:
        start = time.monotonic()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks['database'] = {
            'status': True,
            'latency_ms': round((time.monotonic() - start) * 1000, 1),
        }
    except Exception:
        checks['database'] = {'status': False}
        healthy = False

    # Redis check
    try:
        from django.conf import settings
        redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/0')
        start = time.monotonic()
        r = redis.from_url(redis_url, socket_connect_timeout=2)
        r.ping()
        checks['redis'] = {
            'status': True,
            'latency_ms': round((time.monotonic() - start) * 1000, 1),
        }
    except Exception:
        checks['redis'] = {'status': False}
        healthy = False

    # Ollama check
    try:
        from django.conf import settings
        ollama_url = settings.HAI_DETECTION.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        start = time.monotonic()
        resp = requests.get(f"{ollama_url}/api/tags", timeout=3)
        checks['ollama'] = {
            'status': resp.status_code == 200,
            'latency_ms': round((time.monotonic() - start) * 1000, 1),
        }
        if resp.status_code != 200:
            healthy = False
    except Exception:
        checks['ollama'] = {'status': False}
        healthy = False

    status_code = 200 if healthy else 503
    return JsonResponse({
        'status': 'healthy' if healthy else 'unhealthy',
        'checks': checks,
    }, status=status_code)
