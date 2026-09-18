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


def test_환경변수가_비면_명시_에러(monkeypatch):
    monkeypatch.delenv('HUB_INTROSPECTION_CLIENT_ID', raising=False)
    from mcp_server.server import build

    with pytest.raises(RuntimeError, match='HUB_INTROSPECTION_CLIENT_ID'):
        build()
