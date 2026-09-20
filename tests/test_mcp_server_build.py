"""MCP 서버 조립 — 도구 등록·인증 부착·스코프 가시성. 네트워크 없이, 토큰은 컨텍스트 seam 에 주입한다."""

import asyncio

import pytest


def test_토큰이_없으면_도구가_하나도_보이지_않는다(hub_env, with_token):
    from mcp_server.server import build

    mcp = build()
    assert mcp.auth is not None, '인증 없이 뜨면 안 된다'
    with_token(None)
    assert asyncio.run(mcp.list_tools()) == []


def test_토큰의_스코프만큼만_도구가_보인다(hub_env, with_token):
    """지금 도구가 정확히 이 둘이라는 스냅샷. 도구를 더하면 여기도 함께 고친다.

    도구마다 자기 스코프에만 보이는지는 `tests/test_catalog_adapter_contract.py` 가 spec 수만큼 잰다 —
    이 파일은 인증 연결(토큰 유무·스코프 필터)이 붙어 있는지가 관심이다.
    """
    from mcp_server.server import build

    mcp = build()
    with_token(['tool:weather'])
    tools = asyncio.run(mcp.list_tools())
    assert [t.name for t in tools] == ['weather_now']
    assert 'actor' not in (tools[0].parameters.get('properties') or {}), (
        '자리는 스키마에 노출되지 않아야 한다'
    )
    with_token(['tool:weather', 'tool:kosis'])
    assert sorted(t.name for t in asyncio.run(mcp.list_tools())) == ['kosis_search', 'weather_now']


def test_introspection_주소는_환경변수가_우선한다(hub_env, monkeypatch):
    """compose 안에서는 공개 주소(localhost)가 자기 자신이라 서비스 이름으로 가야 한다."""
    from mcp_server.server import build

    assert build().auth.token_verifier.introspection_url == 'https://hub.example.test/o/introspect/'
    monkeypatch.setenv('HUB_INTROSPECTION_URL', 'http://hub-web:8000/o/introspect/')
    assert build().auth.token_verifier.introspection_url == 'http://hub-web:8000/o/introspect/'


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

    async def get(user_agent='kube-probe/1.0'):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://mcp') as http:
            return await http.get('/healthz', headers={'User-Agent': user_agent})

    response = asyncio.run(get())
    assert response.status_code == 200
    assert response.json() == {'ok': True, 'db': True, 'introspection_secret': True}
    assert 'rs-secret' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    # 요청이 누구든(UA) 같은 판정 — 봇·브라우저라고 다른 응답을 내지 않는다.
    for ua in ('Mozilla/5.0', 'curl/8.0', ''):
        other = asyncio.run(get(ua))
        assert (other.status_code, other.json()) == (200, response.json())

    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', '')
    response = asyncio.run(get())
    assert response.status_code == 503 and response.json()['introspection_secret'] is False


def _access_record(path, status):
    import logging

    return logging.LogRecord(
        'uvicorn.access',
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ('127.0.0.1:5000', 'GET', path, '1.1', status),
        None,
    )


def test_접근_로그는_성공한_healthz_만_거른다():
    """healthcheck(10초) 줄이 접근 로그를 덮지 않게. 실패(503)와 다른 경로는 남긴다."""
    from mcp_server.logs import HealthzAccessFilter, uvicorn_log_config

    keep = HealthzAccessFilter().filter
    assert keep(_access_record('/healthz', 200)) is False
    assert keep(_access_record('/healthz', 503)) is True, '헬스가 나빠진 순간은 보여야 한다'
    assert keep(_access_record('/mcp', 200)) is True
    assert keep(_access_record('/healthzz', 200)) is True

    config = uvicorn_log_config()
    assert config['handlers']['access']['filters'] == ['no_healthz_ok']
    assert 'filters' not in config['handlers']['default'], '오류 로그는 건드리지 않는다'


def test_uvicorn_이_그_설정으로_접근_로그를_거른다(capfd):
    """실제 uvicorn 의 dictConfig 경로로 — 설정이 적용돼 access 핸들러에 필터가 붙는지."""
    import logging

    import uvicorn

    from mcp_server.logs import uvicorn_log_config

    uvicorn.Config(app=lambda *a: None, log_config=uvicorn_log_config())
    access = logging.getLogger('uvicorn.access')
    access.handle(_access_record('/healthz', 200))
    access.handle(_access_record('/mcp', 200))
    err = capfd.readouterr()
    out = err.out + err.err
    assert '"GET /mcp HTTP/1.1" 200' in out
    assert '/healthz' not in out
