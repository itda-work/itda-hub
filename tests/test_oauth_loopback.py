"""네이티브 앱의 loopback 콜백 — 운영처럼 전역 스킴이 https 뿐이어도 loopback 호스트의 http 만은 받는다(#7).

Codex 앱의 CIMD 문서(2026-10-14 실측, https://chatgpt.com/oauth/codex/client.json)는 redirect_uris 가
`http://127.0.0.1/callback`·`http://localhost/callback` 이고 실제 콜백은 임시 포트로 온다. Claude Code 도 같은 모양이다.
"""

import base64
import copy
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from oauth2_provider import cimd
from oauth2_provider.models import get_application_model

from apps.catalog.models import Tool
from apps.oauth.redirects import install
from apps.toolbox.models import ToolboxEntry

CODEX_SAMPLE = {
    'client_id': 'https://chatgpt.com/oauth/codex/client.json',
    'client_uri': 'https://chatgpt.com/codex',
    'application_type': 'native',
    'redirect_uris': ['http://127.0.0.1/callback', 'http://localhost/callback'],
    'token_endpoint_auth_method': 'none',
    'token_endpoint_auth_methods_supported': ['none'],
    'grant_types': ['authorization_code', 'refresh_token'],
    'response_types': ['code'],
    'client_name': 'Codex',
}
CODEX_ID = CODEX_SAMPLE['client_id']


@pytest.fixture(autouse=True)
def https_only(settings):
    """운영 조건 — 전역 redirect 스킴은 https 뿐(로컬 테스트 설정은 http 도 연다)."""
    settings.OAUTH2_PROVIDER = {
        **settings.OAUTH2_PROVIDER,
        'ALLOWED_REDIRECT_URI_SCHEMES': ['https'],
    }
    cache.clear()  # CIMD 실패 백오프가 테스트 사이에 새지 않게
    yield
    cache.clear()


@pytest.fixture
def serve(monkeypatch):
    def _serve(doc):
        monkeypatch.setattr(cimd.SafeMetadataFetcher, 'fetch', lambda self, url: (doc, 3600))

    return _serve


@pytest.fixture
def signed_in(client, user, db):
    call_command('seed_catalog', verbosity=0)
    ToolboxEntry.objects.create(user=user, tool=Tool.objects.get(slug='weather'))
    client.force_login(user)
    return client


def _pkce():
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def _params(redirect_uri, challenge, client_id=CODEX_ID):
    return {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': 'tool:weather',
        'state': 'st',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }


def _app(redirect_uris):
    Application = get_application_model()
    return Application(
        name='t',
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=redirect_uris,
    )


# --- 판정 ---


def test_기동_시_패치가_적용돼_있다():
    assert getattr(get_application_model().get_allowed_schemes, 'hub_loopback', False)
    assert install() is True, '두 번 불러도 겹쳐 감싸지 않고 통과'
    assert not getattr(
        get_application_model().get_allowed_schemes.__wrapped__, 'hub_loopback', False
    )


@pytest.mark.parametrize(
    ('uris', 'http_allowed'),
    [
        ('http://127.0.0.1/callback http://localhost/callback', True),
        ('http://[::1]:8765/cb', True),
        ('https://claude.ai/api/mcp/auth_callback http://127.0.0.1/cb', True),
        ('https://claude.ai/api/mcp/auth_callback', False),
        ('http://example.com/cb', False),
        ('http://127.0.0.1.example.com/cb', False),  # 호스트 이름이 loopback 처럼 시작할 뿐
        (
            'http://127.0.0.1/cb http://example.com/cb',
            False,
        ),  # 하나라도 loopback 이 아니면 전부 거부
        (
            'http://127.0.0.2/cb',
            False,
        ),  # RFC 8252 의 loopback 은 127.0.0.1·::1 — 대역 전체가 아니다
    ],
)
def test_http_는_redirect_가_모두_loopback_일_때만(db, uris, http_allowed):
    assert ('http' in _app(uris).get_allowed_schemes()) is http_allowed


def test_localhost_는_ALLOW_LOCALHOST_LOOPBACK_일_때만(db, settings):
    assert 'http' in _app('http://localhost/callback').get_allowed_schemes()
    settings.OAUTH2_PROVIDER = {**settings.OAUTH2_PROVIDER, 'ALLOW_LOCALHOST_LOOPBACK': False}
    assert 'http' not in _app('http://localhost/callback').get_allowed_schemes()


def test_비_loopback_http_콜백은_등록되지_않는다(db):
    with pytest.raises(ValidationError, match='invalid_scheme'):
        _app('http://example.com/cb').full_clean(exclude=['client_secret'])
    _app('http://127.0.0.1/callback').full_clean(exclude=['client_secret'])  # 통과


# --- Codex CIMD ---


def test_Codex_문서로_공개_Application_이_만들어진다(serve, db):
    serve(copy.deepcopy(CODEX_SAMPLE))
    app = cimd.resolve_cimd_application(CODEX_ID, request=None)
    assert app is not None
    assert app.client_type == get_application_model().CLIENT_PUBLIC
    assert app.name == 'Codex'


def test_비_loopback_http_를_실은_CIMD_문서는_거부된다(serve, db):
    doc = copy.deepcopy(CODEX_SAMPLE)
    doc['redirect_uris'] = ['http://127.0.0.1/callback', 'http://attacker.example/callback']
    serve(doc)
    assert cimd.resolve_cimd_application(CODEX_ID, request=None) is None


@pytest.mark.parametrize(
    'redirect_uri',
    ['http://127.0.0.1:53712/callback', 'http://localhost:61234/callback'],
)
def test_Codex_가_임시_포트로_왕복한다(signed_in, serve, redirect_uri):
    serve(copy.deepcopy(CODEX_SAMPLE))
    verifier, challenge = _pkce()

    page = signed_in.get('/o/authorize/', _params(redirect_uri, challenge))
    assert page.status_code == 200
    assert b'id="authorizationForm"' in page.content
    assert b'data-loopback-warning' in page.content, '동의 화면이 loopback 경고를 띄운다'

    response = signed_in.post(
        '/o/authorize/', {**_params(redirect_uri, challenge), 'allow': 'Authorize'}
    )
    assert response.status_code == 302
    location = urlparse(response['Location'])
    assert f'{location.scheme}://{location.netloc}{location.path}' == redirect_uri
    query = parse_qs(location.query)
    assert query['state'] == ['st']

    token = signed_in.post(
        '/o/token/',
        {
            'client_id': CODEX_ID,
            'grant_type': 'authorization_code',
            'code': query['code'][0],
            'redirect_uri': redirect_uri,
            'code_verifier': verifier,
        },
    )
    assert token.status_code == 200, token.content
    assert token.json()['scope'] == 'tool:weather'


def test_등록되지_않은_loopback_경로로는_돌려보내지_않는다(signed_in, serve):
    serve(copy.deepcopy(CODEX_SAMPLE))
    _, challenge = _pkce()
    page = signed_in.get('/o/authorize/', _params('http://127.0.0.1:53712/other', challenge))
    assert page.status_code >= 400
    assert 'Location' not in page


def test_https_콜백의_동의_화면에는_loopback_경고가_없다(signed_in, serve):
    from apps.oauth.cimd import CLAUDE_AI_SAMPLE

    serve(copy.deepcopy(CLAUDE_AI_SAMPLE))
    _, challenge = _pkce()
    page = signed_in.get(
        '/o/authorize/',
        _params(
            CLAUDE_AI_SAMPLE['redirect_uris'][0], challenge, client_id=CLAUDE_AI_SAMPLE['client_id']
        ),
    )
    assert page.status_code == 200
    assert b'id="authorizationForm"' in page.content
    assert b'data-loopback-warning' not in page.content
