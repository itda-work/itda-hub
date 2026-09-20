"""화면 렌더(H-4) — 주요 화면이 200 으로 뜨고 핵심 요소(폼 필드·라벨·버튼·토큰 카드)가 있는지.

기능·URL·폼 필드 이름은 바뀌지 않았다는 것을 화면 쪽에서 지킨다. 동의 화면은 **렌더된 폼 그대로**
다시 보내 허용·거부가 작동하는지까지 본다(숨은 필드·`allow` 계약).
"""

import base64
import hashlib
import re
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.utils import timezone
from django_itda.models import ToolCall
from oauth2_provider.models import get_application_model

from apps.catalog.models import Tool
from apps.toolbox.models import ToolboxEntry

REDIRECT = 'https://claude.ai/api/mcp/auth_callback'


@pytest.fixture
def catalog(db):
    call_command('seed_catalog', verbosity=0)
    return {t.slug: t for t in Tool.objects.all()}


def _html(response):
    assert response.status_code == 200, response.status_code
    return response.content.decode()


def _shell(html):
    """공통 셸 — 한국어 문서, 빌드된 CSS, 테마 가드, 주 메뉴, 푸터."""
    assert '<html lang="ko">' in html
    assert '/static/css/hub.css' in html and '/static/js/theme-boot.js' in html
    assert 'id="theme-toggle"' in html
    assert 'aria-label="주 메뉴"' in html
    assert 'Powered by' in html and 'https://itda.work' in html
    # 시험 서비스 고지는 모든 화면에 있어야 한다 — 도구를 담고 연결하는 순간마다 알아야 할 전제다.
    assert '시험 서비스' in html and '중단될 수 있습니다' in html


def test_로그인_화면_로컬_전용(client, db):
    html = _html(client.get('/accounts/login/'))
    _shell(html)
    assert 'name="login"' in html and 'name="password"' in html
    assert 'for="id_login"' in html and 'for="id_password"' in html, '입력 칸마다 라벨이 이어진다'
    assert '<details' not in html, 'Google 이 없으면 비밀번호 폼이 1차라 접지 않는다'
    assert '/accounts/signup/' in html, '가입이 열려 있으면(HUB_LOCAL_SIGNUP) 안내한다'


def test_가입_비밀번호재설정_화면(client, db):
    signup = _html(client.get('/accounts/signup/'))
    assert 'name="email"' in signup and 'name="password1"' in signup and 'for="id_email"' in signup
    reset = _html(client.get('/accounts/password/reset/'))
    _shell(reset)
    assert 'name="email"' in reset and 'class="hub-form' in reset


def test_로그아웃_확인_화면(client, user):
    client.force_login(user)
    html = _html(client.get('/accounts/logout/'))
    assert 'action="/accounts/logout/"' in html and 'type="submit"' in html
    assert client.post('/accounts/logout/').status_code == 302


def test_도구함_화면_카드와_연결_카드(client, user, catalog):
    ToolboxEntry.objects.create(user=user, tool=catalog['kosis'])
    client.force_login(user)
    html = _html(client.get('/toolbox/'))
    _shell(html)
    assert 'aria-current="page">도구함' in html
    assert user.email in html
    for tool in Tool.objects.filter(enabled=True):
        assert tool.name in html and tool.scope in html
    assert 'action="/toolbox/remove/kosis/"' in html and 'href="/toolbox/setting/kosis/"' in html
    assert 'aria-label="KOSIS 국가통계 담김 — 빼기"' in html and 'tool-toggle-on' in html
    assert 'action="/toolbox/add/weather/"' in html and 'aria-label="날씨 담기"' in html
    assert 'id="mcp-url"' in html and 'data-copy-target="mcp-url"' in html
    assert '연결 토큰' not in html and '/toolbox/token/' not in html, (
        '연결 토큰은 화면에 내지 않는다'
    )
    assert '관리자</a>' not in html, '관리자 링크는 스태프에게만'


def test_스태프는_관리자_링크를_본다(client, user, catalog):
    user.is_staff = True
    user.save()
    client.force_login(user)
    assert 'href="/admin/"' in _html(client.get('/toolbox/'))


def test_도구_설정_화면_라벨(client, user, catalog, monkeypatch):
    monkeypatch.setenv('SHARED_KOSIS_API_KEY', 'shared')
    ToolboxEntry.objects.create(user=user, tool=catalog['kosis'], use_shared_credential=True)
    client.force_login(user)
    html = _html(client.get('/toolbox/setting/kosis/'))
    assert 'for="id_value"' in html and 'id="id_value"' in html and 'name="value"' in html
    if catalog['kosis'].credential == Tool.Credential.SHARED:
        assert 'for="id_use_shared"' in html and 'name="use_shared"' in html


def test_연결_토큰_화면은_없다(client, user, catalog):
    client.force_login(user)
    for url in ('/toolbox/token/', '/toolbox/token/issue/', '/toolbox/token/revoke/'):
        assert client.post(url).status_code == 404, url


def test_궤적_빈_상태와_표(client, user, catalog):
    client.force_login(user)
    empty = _html(client.get('/trajectory/'))
    _shell(empty)
    assert '아직 호출이 없습니다' in empty and '<table' not in empty

    now = timezone.now()
    for i, (kind, outcome) in enumerate([('ALLOW', 'COMMITTED'), ('DENY', 'NOTHING')]):
        ToolCall.objects.create(
            call_id=f'c{i}',
            tool='weather_now',
            actor=user,
            via='mcp',
            kind=kind,
            outcome=outcome,
            reason='테스트',
            started_at=now - timedelta(seconds=i),
            duration_ms=42,
        )
    html = _html(client.get('/trajectory/'))
    assert '<table' in html and 'scope="col"' in html
    assert 'badge-green">ALLOW' in html and 'badge-red">DENY' in html
    assert 'weather_now' in html and '42ms' in html


@pytest.fixture
def app(db):
    Application = get_application_model()
    return Application.objects.create(
        name='Claude',
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=REDIRECT,
        client_secret='',
    )


def _consent(client, app):
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    )
    return _html(
        client.get(
            '/o/authorize/',
            {
                'client_id': app.client_id,
                'response_type': 'code',
                'redirect_uri': REDIRECT,
                'scope': 'tool:kosis tool:weather',
                'state': 'xyz',
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
            },
        )
    )


def _form_fields(html):
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html))


def test_동의_화면_앱_이름_도구함_스코프_허용_거부(client, user, app, catalog):
    ToolboxEntry.objects.create(user=user, tool=catalog['weather'])
    client.force_login(user)
    html = _consent(client, app)
    _shell(html)
    assert 'Claude' in html and user.email in html
    assert catalog['weather'].name in html and catalog['kosis'].name not in html, '스코프 = 도구함'
    assert '>허용</button>' in html and 'name="allow"' in html and '>거부</button>' in html

    fields = _form_fields(html)
    allowed = client.post('/o/authorize/', {**fields, 'allow': 'Authorize'})
    assert 'code' in parse_qs(urlparse(allowed['Location']).query), '렌더된 폼 그대로 허용된다'

    denied = client.post('/o/authorize/', _form_fields(_consent(client, app)))
    assert parse_qs(urlparse(denied['Location']).query)['error'] == ['access_denied']
