"""loopback 콜백 — http redirect 는 loopback 호스트일 때만 받는다(RFC 8252 §7.3, RFC 9700 §2.1).

운영은 `ALLOWED_REDIRECT_URI_SCHEMES=['https']` 다(E003 게이트, `check --deploy` 0건). DOT 3.4.1 은 스킴만 보므로
http 를 빼면 네이티브 앱의 loopback 콜백(Codex 앱 `http://127.0.0.1/callback`, Claude Code `http://localhost:<포트>/callback`)
까지 막히고, 넣으면 아무 호스트의 http 가 열린다. 표준의 경계는 그 사이 — 「https, 또는 loopback 호스트의 http」.

`Application.get_allowed_schemes()` 를 감싼다: **앱의 http redirect 가 모두 loopback 호스트일 때만** `http` 를 더한다.
등록 검증(`AbstractApplication.clean` — CIMD·DCR·admin 이 모두 `full_clean` 으로 지난다)과 인가 응답 리디렉트
(`BaseAuthorizationView.redirect`)가 둘 다 이 메서드를 부르므로 한 점에서 경계가 선다. loopback 의 포트 무관 매칭은
DOT `redirect_to_uri_allowed` 가 이미 한다(`localhost` 는 `ALLOW_LOCALHOST_LOOPBACK` 일 때). 전역 설정은 그대로라
E003 은 조용하다.

DOT 에 같은 판정을 upstream 제안한다(docs/reports/H-7.md 「A」). 들어오면 이 모듈을 걷는다. DOT 를 올려 호출 구조가
바뀌면 기동 시 자체 검사(`install`)가 경고 로그를 남긴다 — H-5 의 `apps/oauth/cimd.py` 와 같은 방식(#7).
"""

import logging
from urllib.parse import urlparse

log = logging.getLogger(__name__)


def loopback_hosts():
    from oauth2_provider.settings import oauth2_settings

    hosts = {'127.0.0.1', '::1'}
    if oauth2_settings.ALLOW_LOCALHOST_LOOPBACK:
        hosts.add('localhost')
    return hosts


def is_loopback_http(uri):
    try:
        parsed = urlparse(uri)
        return parsed.scheme == 'http' and parsed.hostname in loopback_hosts()
    except ValueError:  # 깨진 IPv6 대괄호 등 — loopback 이 아니다
        return False


def _make_get_allowed_schemes(original):
    def get_allowed_schemes(self):
        schemes = list(original(self))
        if 'http' in schemes:
            return schemes
        http = [u for u in (self.redirect_uris or '').split() if u.lower().startswith('http:')]
        if http and all(is_loopback_http(u) for u in http):
            schemes.append('http')
        return schemes

    get_allowed_schemes.__wrapped__ = original
    get_allowed_schemes.hub_loopback = True
    return get_allowed_schemes


def install():
    """`Application.get_allowed_schemes` 를 loopback 판정판으로 바꾸고 표본으로 확인한다. 반환값은 적용 여부.

    실패해도 기동은 막지 않는다 — 그때는 loopback 콜백만 등록되지 않는다(https 콜백은 무관). 경고 로그만 남긴다.
    """
    try:
        from oauth2_provider.models import AbstractApplication, get_application_model
        from oauth2_provider.views.base import BaseAuthorizationView

        for owner, func in (
            ('AbstractApplication.clean', AbstractApplication.clean),
            ('BaseAuthorizationView.redirect', BaseAuthorizationView.redirect),
        ):
            if 'get_allowed_schemes' not in func.__code__.co_names:
                raise RuntimeError(f'{owner} 가 더는 get_allowed_schemes 를 부르지 않는다')

        Application = get_application_model()
        current = Application.get_allowed_schemes
        if not getattr(current, 'hub_loopback', False):
            Application.get_allowed_schemes = _make_get_allowed_schemes(current)

        # 자체 검사 — 전역 스킴이 https 뿐이라고 가정한 원본으로 판정을 잰다(로컬 설정은 http 를 이미 연다).
        check = _make_get_allowed_schemes(lambda self: ['https'])
        cases = {
            'http://127.0.0.1/callback https://example.com/cb': True,
            'http://[::1]:8765/cb': True,
            'http://example.com/cb': False,
            'http://127.0.0.1/cb http://example.com/cb': False,
            'https://example.com/cb': False,
        }
        for uris, expect_http in cases.items():
            got = 'http' in check(Application(redirect_uris=uris))
            if got != expect_http:
                raise RuntimeError(f'{uris!r} 의 http 허용이 {got} 로 나왔다')
    except Exception as exc:  # noqa: BLE001 — 내부 구조가 어떻게 바뀌든 기동은 막지 않는다
        log.warning(
            'loopback 콜백 패치를 적용하지 못했다 — Codex 앱·Claude Code 의 OAuth 연결이 실패할 수 있다: %r',
            exc,
        )
        return False
    return True
