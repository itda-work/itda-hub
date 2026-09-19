"""잇다 허브 MCP 서버 — 별도 프로세스, Streamable HTTP.

세 가지만 한다.

1. **토큰 검증** — 허브(django-oauth-toolkit)의 introspection 으로. 토큰의 `scope` 가 곧 도구함이다.
2. **가시성** — 도구마다 `auth=require_scopes('tool:<slug>')`. 스코프 없는 도구는 목록에도 없고 호출도 거부된다.
3. **자리** — introspection 응답의 `username` 을 Django 사용자로 풀어 `actor` 로 삼는다. 도구 호출은
   django-itda `Toolset.call` 을 지나므로 궤적(`ToolCall`)이 남는다.

Django 안에서 호스팅하지 않는다. 이 파일은 그 결정의 물증이다.
"""

import os

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django_itda.results import ToolBusy, ToolDenied
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import RemoteAuthProvider, require_scopes
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.tools import specs, toolset

INSTRUCTIONS = (
    '잇다 허브. 사용자가 도구함에 담은 도구만 보인다. 도구가 목록에 없으면 허브(hub.itda.work)의 '
    '도구함에서 담아야 한다고 안내하라. 자격증명 값은 절대 묻지 말고 허브 설정 화면으로 안내하라.'
)


def _env(name):
    value = os.environ.get(name, '')
    if not value:
        raise RuntimeError(f'{name} 이 비어 있다 — .env.example 을 보라')
    return value


def build() -> FastMCP:
    base_url = _env('HUB_BASE_URL').rstrip('/')
    # compose 안에서는 공개 주소(localhost)가 자기 자신이라 서비스 이름(hub-web)으로 가야 한다 — HUB_INTROSPECTION_URL.
    introspection_url = (
        os.environ.get('HUB_INTROSPECTION_URL', '').strip() or f'{base_url}/o/introspect/'
    )
    verifier = IntrospectionTokenVerifier(
        introspection_url=introspection_url,
        client_id=_env('HUB_INTROSPECTION_CLIENT_ID'),
        client_secret=_env('HUB_INTROSPECTION_CLIENT_SECRET'),
        base_url=base_url,
    )
    auth = RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[base_url],
        base_url=base_url,
        resource_name='잇다 허브',
    )
    mcp = FastMCP('itda-hub', instructions=INSTRUCTIONS, auth=auth)
    for spec in specs():
        mcp.tool(_bind(spec), name=spec.name, auth=require_scopes(spec.scope))
    mcp.custom_route('/healthz', methods=['GET'], include_in_schema=False)(healthz)
    return mcp


def _db_roundtrip() -> bool:
    from django.db import DatabaseError, connection

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            return cursor.fetchone() == (1,)
    except DatabaseError:
        return False


async def healthz(request: Request) -> JSONResponse:
    """compose healthcheck 용(프록시는 /mcp 만 이 프로세스로 보내므로 공개되지 않는다). 인증 없음.

    판정은 필드로 — `db`: 같은 SQLite 파일 왕복, `introspection_secret`: 토큰 검증 자격이 환경에 있다
    (값은 싣지 않는다). 하나라도 거짓이면 503.
    """
    checks = {
        'db': await sync_to_async(_db_roundtrip)(),
        'introspection_secret': bool(os.environ.get('HUB_INTROSPECTION_CLIENT_SECRET', '')),
    }
    ok = all(checks.values())
    return JSONResponse({'ok': ok, **checks}, status_code=200 if ok else 503)


async def _actor():
    """토큰 → Django 사용자. introspection 응답에는 `sub` 가 없고 `username` 이 있다(DOT 3.4 실측)."""
    token = get_access_token()
    if token is None:
        raise ToolError('토큰이 없다')
    username = (token.claims or {}).get('username') or token.subject
    if not username:
        raise ToolError('토큰에 사용자 식별이 없다 — 허브 introspection 응답을 확인하라')
    User = get_user_model()
    user = await sync_to_async(User.objects.filter(username=username).first)()
    if user is None:
        raise ToolError(f'토큰의 사용자 {username} 를 허브에서 찾지 못했다')
    return user


def _bind(spec):
    async def run(**kwargs):
        actor = await _actor()
        try:
            return await sync_to_async(toolset.call)(spec.name, actor, **kwargs)
        except (ToolDenied, ToolBusy) as exc:
            raise ToolError(str(exc)) from None

    run.__name__ = spec.name
    run.__doc__ = spec.description
    run.__signature__ = spec.signature
    run.__annotations__ = spec.annotations
    return run
