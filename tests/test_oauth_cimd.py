"""claude.ai 커스텀 커넥터의 CIMD 신원 — grant 해석 완화와, 인가 화면이 오류를 오류로 보여 주는지.

2026-09-20 운영: claude.ai 문서에 `urn:ietf:params:oauth:grant-type:jwt-bearer` 가 더해져 DOT 3.4.1 이 CIMD 해석을
거부했고, 허브는 그 오류를 「도구함이 비어 있습니다」 로 바꿔 보여 줬다(docs/reports/H-5.md).
"""

import base64
import copy
import hashlib
import logging
import secrets

import pytest
from django.core.cache import cache
from django.core.management import call_command
from oauth2_provider import cimd
from oauth2_provider.models import get_application_model

from apps.catalog.models import Tool
from apps.oauth.cimd import CLAUDE_AI_SAMPLE, install
from apps.toolbox.models import ToolboxEntry

CLIENT_ID = CLAUDE_AI_SAMPLE['client_id']
REDIRECT = CLAUDE_AI_SAMPLE['redirect_uris'][0]


def _doc(**overrides):
    doc = copy.deepcopy(CLAUDE_AI_SAMPLE)
    doc.update(overrides)
    return doc


@pytest.fixture(autouse=True)
def _clear_backoff():
    cache.clear()  # CIMD 실패 백오프가 테스트 사이에 새지 않게
    yield
    cache.clear()


@pytest.fixture
def serve(monkeypatch):
    """SafeMetadataFetcher 를 네트워크 없이 — 주어진 문서를 돌려준다."""

    def _serve(doc):
        monkeypatch.setattr(cimd.SafeMetadataFetcher, 'fetch', lambda self, url: (doc, 3600))

    return _serve


@pytest.fixture
def signed_in(client, user, db):
    call_command('seed_catalog', verbosity=0)
    for slug in ('kosis', 'weather'):
        ToolboxEntry.objects.create(user=user, tool=Tool.objects.get(slug=slug))
    client.force_login(user)
    return client


def _authorize(client, scope='tool:kosis tool:weather'):
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    )
    return client.get(
        '/o/authorize/',
        {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': REDIRECT,
            'scope': scope,
            'state': 'st',
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
        },
    )


# --- grant 해석 ---


def test_기동_시_완화_패치가_적용돼_있다():
    assert getattr(cimd._resolve_grant_type, 'hub_relaxed', False)
    assert install() is True, '두 번 불러도 겹쳐 감싸지 않고 통과'
    assert not getattr(cimd._resolve_grant_type.__wrapped__, 'hub_relaxed', False)


def test_claude_ai_문서의_grant_3종은_authorization_code_로_해석된다():
    assert cimd._build_application_kwargs(CLAUDE_AI_SAMPLE)['authorization_grant_type'] == (
        'authorization-code'
    )


@pytest.mark.parametrize(
    'grant_types',
    [
        ['refresh_token', 'urn:ietf:params:oauth:grant-type:jwt-bearer'],  # 지원 0
        ['client_credentials'],  # 지원 0
        ['authorization_code', 'implicit', 'refresh_token'],  # 지원 2
    ],
)
def test_지원_grant_가_정확히_하나가_아니면_여전히_거부한다(grant_types):
    with pytest.raises(cimd.CIMDError, match='exactly one supported grant type') as exc:
        cimd._build_application_kwargs(_doc(grant_types=grant_types))
    assert repr(grant_types) in str(exc.value), '실패 로그에 문서의 grant 목록이 남는다'


def test_claude_ai_문서로_Application_이_만들어진다(serve, db):
    serve(_doc())
    app = cimd.resolve_cimd_application(CLIENT_ID, request=None)
    assert app is not None
    assert app.authorization_grant_type == get_application_model().GRANT_AUTHORIZATION_CODE
    assert app.client_type == get_application_model().CLIENT_PUBLIC


def test_CIMD_실패_로그에_문서_URL과_grant_목록이_남는다(serve, db, caplog):
    grants = ['refresh_token', 'urn:ietf:params:oauth:grant-type:jwt-bearer']
    serve(_doc(grant_types=grants))
    with caplog.at_level(logging.INFO, logger='oauth2_provider.cimd'):
        assert cimd.resolve_cimd_application(CLIENT_ID, request=None) is None
    text = caplog.text
    assert CLIENT_ID in text and repr(grants) in text


# --- 인가 화면: 오류 / 빈 교집합 / 정상 ---


def test_claude_ai_문서로_인가하면_동의_폼이_나온다(signed_in, serve):
    serve(_doc())
    page = _authorize(signed_in)
    assert page.status_code == 200
    assert page.context['scopes'] == ['tool:kosis', 'tool:weather']
    assert b'id="authorizationForm"' in page.content


def test_CIMD_해석이_실패하면_빈_도구함이_아니라_오류_화면(signed_in, serve):
    serve(_doc(grant_types=['client_credentials']))
    page = _authorize(signed_in)
    body = page.content.decode()
    assert page.status_code == 400
    assert '도구함이 비어 있습니다' not in body
    assert '클라이언트 등록(CIMD) 실패' in body
    assert CLIENT_ID in body
    assert 'authorizationForm' not in body


def test_일반_인가_오류도_빈_도구함으로_바뀌지_않는다(signed_in, serve):
    serve(_doc())
    # 등록되지 않은 콜백 — 클라이언트로 돌려보낼 수 없어 허브가 직접 오류 화면을 낸다.
    page = signed_in.get(
        '/o/authorize/',
        {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': 'https://evil.example/cb',
        },
    )
    body = page.content.decode()
    assert page.status_code >= 400
    assert '도구함이 비어 있습니다' not in body
    assert '연결할 수 없습니다' in body
    assert '클라이언트 등록(CIMD) 실패' not in body


def test_검증은_통과하고_교집합이_비면_빈_도구함(client, user, serve, db):
    call_command('seed_catalog', verbosity=0)
    client.force_login(user)  # 도구함 비어 있음
    serve(_doc())
    page = _authorize(client)
    assert page.status_code == 200
    assert '도구함이 비어 있습니다' in page.content.decode()
