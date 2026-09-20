"""비밀이 상류 실패 경로로 새지 않는지 — 궤적(`ToolCall.reason`)과 프로세스 로그 양쪽.

허브의 계약은 「도구 인자에 자격증명을 싣지 않으므로 궤적에 비밀이 남지 않는다」인데, 그 계약은
정상 경로에서만 참이었다(#4). 상류가 HTTP 오류를 내면 httpx 예외 문자열에 요청 URL 이 통째로
실리고, django-itda 가 그것을 `ToolCall.reason` 에 저장한다. 성공할 때도 httpx 의 INFO 로그가
URL 을 찍는다.

키는 쿼리스트링에서 **URL 인코딩**되므로 원문 검사만으로는 통과하는데 새는 테스트가 된다.
아래 `assert_no_key` 가 두 형태를 모두 본다.
"""

import contextlib
import logging
import logging.config

import httpx
import pytest

# 가짜 키에 URL 인코딩되는 문자를 일부러 넣는다 — `+` `/` `=` 는 각각 %2B %2F %3D 가 된다.
FAKE_KEY = 'ZZfake+key/for=leak+probe=ZZ'


def encoded(value: str) -> str:
    """이 값이 쿼리스트링에 실릴 때의 모양."""
    return str(httpx.QueryParams({'k': value})).split('=', 1)[1]


def assert_no_key(haystack: str, where: str):
    assert FAKE_KEY not in haystack, f'{where} 에 키가 원문으로 있다: {haystack[:400]}'
    assert encoded(FAKE_KEY) not in haystack, (
        f'{where} 에 키가 URL 인코딩 형태로 있다: {haystack[:400]}'
    )


def _kosis_call():
    from mcp_server.tools import kosis

    return kosis.search(FAKE_KEY, '인구', 3)


# --- 궤적 축 -------------------------------------------------------------


@pytest.mark.parametrize(
    'name,handler',
    [
        ('상류 500', lambda req: httpx.Response(500, json={'message': 'boom'})),
        ('상류 404', lambda req: httpx.Response(404, text='not found')),
        ('상류 429', lambda req: httpx.Response(429, text='too many')),
        ('타임아웃', lambda req: (_ for _ in ()).throw(httpx.ReadTimeout('read timed out'))),
        ('연결 실패', lambda req: (_ for _ in ()).throw(httpx.ConnectError('no route'))),
    ],
)
def test_상류_실패의_예외_문자열에_키가_없다(upstream, name, handler):
    """어댑터가 올리는 예외는 그대로 `ToolCall.reason` 이 된다(django_itda/tools.py).

    그러므로 예외 문자열에 키가 없어야 궤적에도 없다.
    """
    upstream(handler)
    try:
        _kosis_call()
    except Exception as exc:  # noqa: BLE001 — 어떤 예외든 그 문자열을 검사하는 것이 이 테스트다
        assert_no_key(f'{type(exc).__name__}: {exc}', f'{name} 의 예외 문자열')
        assert_no_key(repr(exc), f'{name} 의 예외 repr')


def test_궤적에_저장된_사유에_키가_없다(db, user, upstream):
    """끝까지 — Toolset.call 을 지나 실제 ToolCall 행의 `reason` 을 본다."""
    from django.core.management import call_command
    from django_itda.models import ToolCall

    from apps.catalog.models import Tool
    from apps.toolbox.models import ToolboxEntry, ToolSetting
    from mcp_server.tools import toolset

    call_command('seed_catalog', verbosity=0)
    entry = ToolboxEntry.objects.create(user=user, tool=Tool.objects.get(slug='kosis'))
    setting = ToolSetting(entry=entry, key='KOSIS_API_KEY')
    setting.set_value(FAKE_KEY)
    setting.save()

    upstream(lambda req: httpx.Response(503, text='service unavailable'))
    # 실패해도 좋다 — 궤적에 무엇이 남았는지가 이 테스트의 관심이다.
    with contextlib.suppress(Exception):
        toolset.call('kosis_search', user, keyword='인구', count=3)

    row = ToolCall.objects.filter(tool='kosis_search').order_by('-id').first()
    assert row is not None, '호출이 궤적에 한 행도 남지 않았다'
    assert_no_key(row.reason, 'ToolCall.reason')
    assert_no_key(str(row.arguments), 'ToolCall.arguments')


# --- 로그 축 -------------------------------------------------------------


def test_성공한_호출의_로그에도_키가_없다(upstream, caplog):
    """예외 경로만 막으면 절반이다 — httpx 는 **성공 응답도** INFO 로 URL 을 찍는다."""
    upstream(lambda req: httpx.Response(200, json=[]))
    with caplog.at_level(logging.DEBUG):
        _kosis_call()
    assert_no_key(caplog.text, '성공 호출의 로그')


def test_실패한_호출의_로그에도_키가_없다(upstream, caplog):
    upstream(lambda req: httpx.Response(500, text='boom'))
    with caplog.at_level(logging.DEBUG), contextlib.suppress(Exception):
        _kosis_call()
    assert_no_key(caplog.text, '실패 호출의 로그')


def test_httpx_로거는_INFO_를_내지_않는다(settings):
    """근본 처방 — 설정이 httpx 로거를 WARNING 이상으로 묶는다.

    루트 로거가 INFO 라서(`hub/settings.py`) 그대로 두면 httpx 의 요청 줄이 매 호출 stdout 에 남는다.
    """
    logging.config.dictConfig(settings.LOGGING)
    for name in ('httpx', 'httpcore'):
        logger = logging.getLogger(name)
        assert logger.getEffectiveLevel() >= logging.WARNING, (
            f'{name} 로거가 INFO 이하다 — 요청 URL 이 로그에 남는다'
        )
