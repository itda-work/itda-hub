"""MCP 서버 조립 — 도구 등록·인증 부착·스코프 가시성. 네트워크 없이, 토큰은 컨텍스트 seam 에 주입한다."""

import asyncio

import pytest
from fastmcp.server.auth.auth import AccessToken


@pytest.fixture
def hub_env(monkeypatch):
    monkeypatch.setenv('HUB_BASE_URL', 'https://hub.example.test')
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_ID', 'rs')
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', 'rs-secret')


def _with_token(monkeypatch, scopes):
    """fastmcp 가 요청마다 읽는 인증 컨텍스트를 대신한다. HTTP 전송·토큰 있음으로 본다."""
    import fastmcp.server.server as server_mod

    token = None if scopes is None else AccessToken(token='t', client_id='claude', scopes=scopes)
    monkeypatch.setattr(server_mod, '_get_auth_context', lambda: (False, token))


def test_토큰이_없으면_도구가_하나도_보이지_않는다(hub_env, monkeypatch):
    from mcp_server.server import build

    mcp = build()
    assert mcp.auth is not None, '인증 없이 뜨면 안 된다'
    _with_token(monkeypatch, None)
    assert asyncio.run(mcp.list_tools()) == []


def test_토큰의_스코프만큼만_도구가_보인다(hub_env, monkeypatch):
    from mcp_server.server import build

    mcp = build()
    _with_token(monkeypatch, ['tool:weather'])
    tools = asyncio.run(mcp.list_tools())
    assert [t.name for t in tools] == ['weather_now']
    assert 'actor' not in (tools[0].parameters.get('properties') or {}), (
        '자리는 스키마에 노출되지 않아야 한다'
    )
    _with_token(monkeypatch, ['tool:weather', 'tool:kosis'])
    assert sorted(t.name for t in asyncio.run(mcp.list_tools())) == ['kosis_search', 'weather_now']


def test_introspection_주소는_환경변수가_우선한다(hub_env, monkeypatch):
    """compose 안에서는 공개 주소(localhost)가 자기 자신이라 서비스 이름으로 가야 한다."""
    from mcp_server.server import build

    assert build().auth.token_verifier.introspection_url == 'https://hub.example.test/o/introspect/'
    monkeypatch.setenv('HUB_INTROSPECTION_URL', 'http://web:8000/o/introspect/')
    assert build().auth.token_verifier.introspection_url == 'http://web:8000/o/introspect/'


def test_환경변수가_비면_명시_에러(monkeypatch):
    monkeypatch.delenv('HUB_INTROSPECTION_CLIENT_ID', raising=False)
    from mcp_server.server import build

    with pytest.raises(RuntimeError, match='HUB_INTROSPECTION_CLIENT_ID'):
        build()


@pytest.mark.django_db(transaction=True)
def test_healthz_는_DB_왕복과_introspection_시크릿을_본다(hub_env, monkeypatch):
    """compose healthcheck 가 부르는 /healthz — 인증 없이 열리고, 시크릿 값은 싣지 않는다."""
    import httpx

    from mcp_server.server import build

    app = build().http_app(path='/mcp')

    async def get():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://mcp') as http:
            return await http.get('/healthz')

    response = asyncio.run(get())
    assert response.status_code == 200
    assert response.json() == {'ok': True, 'db': True, 'introspection_secret': True}
    assert 'rs-secret' not in response.text

    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', '')
    response = asyncio.run(get())
    assert response.status_code == 503 and response.json()['introspection_secret'] is False
