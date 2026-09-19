"""프로젝트 수준 뷰 — 상태 확인만."""

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from oauth2_provider.models import get_application_model


@never_cache
def healthz(request):
    """compose healthcheck·운영 프로브용. 판정은 필드로 낸다 — 하나라도 거짓이면 503.

    - `db`: DB 왕복(SELECT 1). 파일이 없거나 잠겨 풀리지 않으면 거짓.
    - `introspection_app`: MCP 프로세스가 토큰을 검증할 리소스 서버 Application 이 있다(bootstrap 이 만든다).
      없으면 web 은 떠 있어도 MCP 쪽 인증이 전부 실패하므로 healthy 가 아니다. 시크릿 값은 싣지 않는다.

    공개 경로다(프록시가 나머지를 전부 web 으로 보낸다). 그래서 불리언만 싣고, 요청(UA·헤더)과 무관하게
    200/503 만 내며, 캐시에 남지 않게 `no-store` 를 붙인다(`never_cache`).
    """
    checks = {'db': False, 'introspection_app': False}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            checks['db'] = cursor.fetchone() == (1,)
        client_id = settings.HUB_INTROSPECTION_CLIENT_ID
        checks['introspection_app'] = bool(client_id) and (
            get_application_model().objects.filter(client_id=client_id).exists()
        )
    except DatabaseError:
        pass
    ok = all(checks.values())
    return JsonResponse({'ok': ok, **checks}, status=200 if ok else 503)
