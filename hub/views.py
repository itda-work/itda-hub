"""프로젝트 수준 뷰 — 상태 확인만."""

from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """compose healthcheck·운영 프로브용. DB 연결까지 확인한다(파일이 없거나 잠기면 500)."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'ok': True})
