"""스파이크의 핵심 불변식 — Claude 가 전체 스코프를 요청해도 토큰에는 도구함 스코프만 실린다.

authorization code + PKCE(S256) 왕복을 Django 테스트 클라이언트로 돈다. 공개 클라이언트(token_endpoint_auth 'none').
"""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from oauth2_provider.models import get_application_model

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
def catalog(db):
    call_command('seed_catalog', verbosity=0)
    return {t.slug: t for t in Tool.objects.all()}


def _pkce():
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def test_동의_화면과_토큰은_도구함_스코프로_좁혀진다(client, user, app, catalog):
    ToolboxEntry.objects.create(user=user, tool=catalog['weather'])
    client.force_login(user)
    verifier, challenge = _pkce()
    params = {
        'client_id': app.client_id,
        'response_type': 'code',
        'redirect_uri': REDIRECT,
        'scope': 'tool:kosis tool:weather',  # Claude 는 광고된 전체를 요청한다
        'state': 'xyz',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    page = client.get('/o/authorize/', params)
    assert page.status_code == 200
    assert page.context['scopes'] == ['tool:weather'], '동의 화면에는 도구함의 스코프만'

    form = {**params, 'scope': 'tool:kosis tool:weather', 'allow': 'Authorize'}  # 넓히기 시도
    redirect = client.post('/o/authorize/', form)
    assert redirect.status_code == 302
    code = parse_qs(urlparse(redirect['Location']).query)['code'][0]

    token = client.post(
        '/o/token/',
        {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT,
            'client_id': app.client_id,
            'code_verifier': verifier,
        },
    )
    assert token.status_code == 200, token.content
    body = token.json()
    assert body['scope'] == 'tool:weather', '토큰 스코프 = 도구함'
    assert body['token_type'].lower() == 'bearer'


def test_도구함이_비면_동의_대신_안내(client, user, app, catalog):
    client.force_login(user)
    _, challenge = _pkce()
    page = client.get(
        '/o/authorize/',
        {
            'client_id': app.client_id,
            'response_type': 'code',
            'redirect_uri': REDIRECT,
            'scope': 'tool:kosis',
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
        },
    )
    assert page.status_code == 200
    assert '도구함이 비어 있습니다' in page.content.decode()
