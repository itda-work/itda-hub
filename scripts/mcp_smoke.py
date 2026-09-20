"""MCP 왕복 스모크 — 연결 토큰으로 진짜 MCP 클라이언트(fastmcp)가 도구를 하나씩 부른다.

    HUB_TOKEN=<연결 토큰> [HUB_MCP_URL=http://localhost:8080/mcp] python scripts/mcp_smoke.py

판정은 반환 구조로 한다: ① 토큰 없이는 거부 ② 토큰의 스코프만큼 도구가 보인다 ③ 날씨는 current 가 온다
④ 키가 필요한 도구는 ok 이거나(키 있음) 자격증명 거부(ToolError)다 — 둘 다 정상, 예외로 죽는 것만 실패.

**키가 필요한 도구의 라이브 검증이 여기다.** 단위 테스트는 픽스처로 고정한 모양만 재므로 상류가
실제로 그 모양을 내는지는 이 스모크가 말한다. 보고서는 `docs/reports/H-6.md`.

종료 코드 0 = 통과. 토큰은 환경변수로만 받는다(argv 는 ps 에 보인다).
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.exceptions import ToolError
from mcp.shared.exceptions import MCPError


def _payload(result):
    data = getattr(result, 'data', None)
    if data is not None:
        return data
    return getattr(result, 'structured_content', None) or [
        getattr(c, 'text', None) for c in result.content
    ]


async def main() -> int:
    url = os.environ.get('HUB_MCP_URL', 'http://localhost:8080/mcp')
    token = os.environ.get('HUB_TOKEN', '')
    if not token:
        print(
            'HUB_TOKEN 이 비어 있다 — `just token <이메일>` 또는 `manage.py issue_token --email <이메일>` 로 발급하라',
            file=sys.stderr,
        )
        return 2
    report = {
        'url': url,
        'unauthenticated_rejected': None,
        'tools': [],
        'weather': None,
        'calls': {},
    }

    try:
        async with Client(url) as anon:
            await anon.list_tools()
        report['unauthenticated_rejected'] = False
    except Exception as exc:  # noqa: BLE001 — 거부의 예외 종류는 전송 계층이 정한다. 서버 다운은 아래 인증 호출이 잡는다
        report['unauthenticated_rejected'] = True
        report['unauthenticated_error'] = type(exc).__name__

    try:
        async with Client(url, auth=BearerAuth(token)) as client:
            tools = await client.list_tools()
            report['tools'] = sorted(t.name for t in tools)
            await _call_tools(client, report)
    except MCPError as exc:
        # 폐기·만료 토큰이면 여기로 온다 — 서버 다운은 위 익명 호출도 같은 이유로 실패했을 것이다.
        report['authenticated_error'] = f'{type(exc).__name__}: {exc}'
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    ok = report['unauthenticated_rejected'] is True and bool(report['tools'])
    if report['weather'] is not None:
        ok = ok and isinstance(report['weather'], dict) and 'current' in report['weather']
    return 0 if ok else 1


def _probes():
    """도구마다 한 번 부를 인자. 날짜는 오늘에서 뒤로 잡는다 — 상류가 아직 안 낸 달을 찍으면
    「키 문제」와 「데이터 없음」이 섞인다. 실거래가는 공개가 늦어 두 달 전을 본다."""
    today = datetime.now(ZoneInfo('Asia/Seoul')).date()  # 상류가 모두 KST 기준이다
    두달전 = (today.replace(day=1) - timedelta(days=62)).strftime('%Y%m')
    올해 = today.strftime('%Y')
    return {
        'kosis_search': {'keyword': '인구', 'count': 3},
        'realty_deals': {'lawd_cd': '11680', 'deal_ymd': 두달전, 'count': 3},
        'ecos_stats': {'keyword': '소비자물가', 'count': 3},
        'fx_rate': {
            'start': f'{올해}0102',
            'end': f'{올해}0131',
            'currency': '미국달러',
            'count': 5,
        },
    }


async def _call_tools(client, report):
    if 'weather_now' in report['tools']:
        r = await client.call_tool('weather_now', {'latitude': 37.5665, 'longitude': 126.978})
        report['weather'] = _payload(r)
    for name, args in _probes().items():
        if name not in report['tools']:
            continue
        try:
            report['calls'][name] = _payload(await client.call_tool(name, args))
        except ToolError as exc:
            # 키가 없으면 여기로 온다 — 거부도 정상 경로다(그 사실이 궤적에 남는 것이 계약이다).
            report['calls'][name] = {'denied': str(exc)}


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
