"""인가 서버의 RFC 9700 자세 — 커스텀 커넥터가 쓰는 길(code + PKCE S256 + refresh 회전)은 열려 있고,
나머지(plain · implicit · password · 쿼리스트링 토큰 · refresh 재사용)는 닫혀 있다.

claude.ai·Cowork 커스텀 커넥터의 신원(CIMD 문서, 2026-09-20 실측)은 grant_types = authorization_code ·
refresh_token · jwt-bearer(허브는 무시 — tests/test_oauth_cimd.py), response_types = code, token_endpoint_auth_method = none, 콜백 https — 여기서 닫는 것과 겹치지 않는다.
"""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from oauth2_provider.models import get_access_token_model, get_application_model
from oauth2_provider.oauth2_backends import get_oauthlib_core

from apps.catalog.models import Tool
from apps.toolbox.models import ToolboxEntry

REDIRECT = 'https://claude.ai/api/mcp/auth_callback'


@pytest.fixture
def app(db):
    Application = get_application_model()
    return Application.objects.create(
        name='claude-test',
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=REDIRECT,
        client_secret='',
    )


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


def _authorize(client, app, challenge, method='S256', response_type='code'):
    form = {
        'client_id': app.client_id,
        'response_type': response_type,
        'redirect_uri': REDIRECT,
        'scope': 'tool:weather',
        'state': 'st',
        'code_challenge': challenge,
        'code_challenge_method': method,
        'allow': 'Authorize',
    }
    response = client.post('/o/authorize/', form)
    location = response.get('Location', '')
    return response, urlparse(location), parse_qs(urlparse(location).query)


def _token(client, app, **data):
    return client.post('/o/token/', {'client_id': app.client_id, **data})


def _code_flow(client, app):
    verifier, challenge = _pkce()
    _, _, query = _authorize(client, app, challenge)
    body = _token(
        client,
        app,
        grant_type='authorization_code',
        code=query['code'][0],
        redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    assert body.status_code == 200, body.content
    return body.json()


def test_메타데이터는_닫힌_길을_광고하지_않는다(client, db):
    doc = client.get('/.well-known/oauth-authorization-server').json()
    assert 'implicit' not in doc['grant_types_supported']
    assert 'password' not in doc['grant_types_supported']
    assert {'authorization_code', 'refresh_token'} <= set(doc['grant_types_supported'])
    assert doc['code_challenge_methods_supported'] == ['S256']
    assert doc['authorization_response_iss_parameter_supported'] is True
    assert 'token' not in doc['response_types_supported']


def test_PKCE_S256_왕복은_통과하고_인가_응답에_iss_가_실린다(signed_in, app):
    """RFC 9207 — 클라이언트가 mix-up 을 가려낼 수 있게 iss(= 발급자 = HUB_BASE_URL)를 싣는다."""
    verifier, challenge = _pkce()
    response, location, query = _authorize(signed_in, app, challenge)
    assert response.status_code == 302
    assert f'{location.scheme}://{location.netloc}{location.path}' == REDIRECT
    assert query['iss'] == ['http://testserver']
    assert query['state'] == ['st'] and 'code' in query

    body = _token(
        signed_in,
        app,
        grant_type='authorization_code',
        code=query['code'][0],
        redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    assert body.status_code == 200, body.content
    assert body.json()['scope'] == 'tool:weather'


def test_PKCE_plain_은_거부된다(signed_in, app):
    verifier = secrets.token_urlsafe(48)
    response, _, query = _authorize(signed_in, app, verifier, method='plain')
    assert response.status_code == 302
    assert 'code' not in query, 'plain 으로는 인가 코드가 나오지 않는다'
    assert query['error'] == ['invalid_request']


def test_PKCE_없는_요청은_거부된다(signed_in, app):
    response = signed_in.post(
        '/o/authorize/',
        {
            'client_id': app.client_id,
            'response_type': 'code',
            'redirect_uri': REDIRECT,
            'scope': 'tool:weather',
            'allow': 'Authorize',
        },
    )
    query = parse_qs(urlparse(response.get('Location', '')).query)
    assert 'code' not in query and query.get('error') == ['invalid_request']


def test_implicit_은_거부된다(signed_in, db):
    Application = get_application_model()
    implicit = Application.objects.create(
        name='implicit',
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_IMPLICIT,
        redirect_uris=REDIRECT,
    )
    _, challenge = _pkce()
    response, location, _ = _authorize(signed_in, implicit, challenge, response_type='token')
    fragment = parse_qs(location.fragment)
    assert 'access_token' not in fragment
    assert get_access_token_model().objects.count() == 0
    assert response.status_code in (302, 400)


def test_password_grant_는_거부된다(client, user, db):
    Application = get_application_model()
    secret = 'pw-secret'
    pw = Application.objects.create(
        name='pw',
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_PASSWORD,
        client_secret=secret,
        redirect_uris='',
    )
    response = client.post(
        '/o/token/',
        {
            'grant_type': 'password',
            'username': 'alice',
            'password': 'x',
            'client_id': pw.client_id,
            'client_secret': secret,
        },
    )
    assert response.status_code == 400, response.content
    assert 'access_token' not in response.json()


def test_토큰은_쿼리스트링으로_받지_않는다(signed_in, app):
    """RFC 9700 §4.3.2 — 같은 토큰이 헤더로는 통하고 ?access_token= 으로는 막힌다."""
    access = _code_flow(signed_in, app)['access_token']
    core = get_oauthlib_core()
    factory = RequestFactory()
    by_header = factory.get('/x', HTTP_AUTHORIZATION=f'Bearer {access}')
    by_query = factory.get('/x', {'access_token': access})
    assert core.verify_request(by_header, scopes=['tool:weather'])[0] is True
    assert core.verify_request(by_query, scopes=['tool:weather'])[0] is False


def test_refresh_회전_뒤_옛_refresh_재사용은_계열을_폐기한다(signed_in, app):
    first = _code_flow(signed_in, app)
    rotated = _token(
        signed_in, app, grant_type='refresh_token', refresh_token=first['refresh_token']
    )
    assert rotated.status_code == 200, rotated.content
    second = rotated.json()
    assert second['refresh_token'] != first['refresh_token']

    replay = _token(
        signed_in, app, grant_type='refresh_token', refresh_token=first['refresh_token']
    )
    assert replay.status_code == 400
    # 재사용이 탐지되면 회전으로 받은 새 refresh 도 죽는다(탈취된 쪽이 어느 쪽이든 끊긴다).
    after = _token(
        signed_in, app, grant_type='refresh_token', refresh_token=second['refresh_token']
    )
    assert after.status_code == 400


def test_로컬은_http_콜백을_받는다(db):
    """로컬(http://localhost)만 — 운영(https) 금지는 tests/test_production_settings.py 가 잰다."""
    from django.conf import settings

    assert settings.OAUTH2_PROVIDER['ALLOWED_REDIRECT_URI_SCHEMES'] == ['http', 'https']
    Application = get_application_model()
    local = Application(
        name='local',
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris='http://127.0.0.1:33418/callback',
    )
    local.full_clean(exclude=['client_secret', 'user'])
