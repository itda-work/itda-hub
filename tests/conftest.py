"""공용 픽스처. 환경변수 기본값은 tests/settings.py 가 settings import 전에 박는다."""

import httpx
import pytest


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username='alice', email='alice@example.com', password='x'
    )


@pytest.fixture
def catalog(db):
    """v1 카탈로그를 심는다 — 공개 kosis·weather, 비공개 fx·fuel."""
    from django.core.management import call_command

    from apps.catalog.models import Tool

    call_command('seed_catalog', verbosity=0)
    return {t.slug: t for t in Tool.objects.all()}


@pytest.fixture
def hub_env(monkeypatch):
    """MCP 서버를 조립할 수 있는 최소 환경. 네트워크는 쓰지 않는다."""
    monkeypatch.setenv('HUB_BASE_URL', 'https://hub.example.test')
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_ID', 'rs')
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', 'rs-secret')


@pytest.fixture
def with_token(monkeypatch):
    """fastmcp 가 요청마다 읽는 인증 컨텍스트를 대신한다. HTTP 전송·토큰 있음으로 본다.

    자리가 둘이다 — 가시성·인가 검사는 `fastmcp.server.server._get_auth_context` 를 보고, 도구 본문의
    자리 해석(`mcp_server.server._actor`)은 `get_access_token()` 을 본다. 둘 다 같은 토큰을 내야
    목록과 호출이 같은 조건에서 돈다.

    이 픽스처가 주는 것은 **인증이 끝난 상태**다 — introspection·bearer 검증·HTTP 전송은 지나지 않는다.
    인가(스코프) 판정은 그대로 돈다: `(False, token)` 의 `False` 는 「검사를 건너뛰지 않는다」 는 뜻이라
    `require_scopes` 가 실제로 걸린다.

    `None` 은 토큰 없음(미인증), `[]` 는 **인증됐지만 빈 도구함**이다 — 둘은 다른 조건이다.
    """
    import fastmcp.server.server as server_mod
    from fastmcp.server.auth.auth import AccessToken

    import mcp_server.server as hub_server

    def install(scopes, *, username='alice'):
        token = (
            None
            if scopes is None
            else AccessToken(
                token='t', client_id='claude', scopes=list(scopes), claims={'username': username}
            )
        )
        monkeypatch.setattr(server_mod, '_get_auth_context', lambda: (False, token))
        monkeypatch.setattr(hub_server, 'get_access_token', lambda: token)
        return token

    return install


@pytest.fixture
def upstream(monkeypatch):
    """상류를 MockTransport 로 세운다 — 네트워크를 부르지 않는다.

    어댑터가 `httpx.get` 을 쓰든 공통 레이어를 쓰든 같은 자리를 지나도록 모듈의 `get` 을 갈아끼운다.
    """

    def install(handler):
        transport = httpx.MockTransport(handler)

        def fake_get(url, **kwargs):
            with httpx.Client(transport=transport) as client:
                return client.get(url, **kwargs)

        monkeypatch.setattr(httpx, 'get', fake_get)

    return install
