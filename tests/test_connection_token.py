"""연결 토큰 — OAuth 왕복 없이 붙는 개인 토큰. 검증 경로는 OAuth 토큰과 같은 introspection 이다."""

import base64

import pytest
from django.core.management import call_command
from oauth2_provider.models import get_access_token_model

from apps.catalog.models import Tool
from apps.toolbox import tokens
from apps.toolbox.models import ToolboxEntry

RS = ('rs', 'rs-secret')


@pytest.fixture
def catalog(db):
    call_command('seed_catalog', verbosity=0)
    return {t.slug: t for t in Tool.objects.all()}


@pytest.fixture
def rs(db, monkeypatch):
    """introspection 리소스 서버 자격 — bootstrap 이 만드는 것과 같은 경로로 만든다."""
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_ID', RS[0])
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', RS[1])
    call_command('bootstrap', verbosity=0)
    return RS


def _introspect(client, creds, raw):
    basic = base64.b64encode(f'{creds[0]}:{creds[1]}'.encode()).decode()
    return client.post('/o/introspect/', {'token': raw}, HTTP_AUTHORIZATION=f'Basic {basic}')


def test_발급_토큰은_introspection_에서_도구함_스코프와_사용자를_돌려준다(
    client, user, catalog, rs
):
    ToolboxEntry.objects.create(user=user, tool=catalog['weather'])
    raw = tokens.issue(user)
    data = _introspect(client, rs, raw).json()
    assert data['active'] is True
    assert data['scope'] == 'tool:weather'
    assert data['username'] == 'alice', 'MCP 서버의 _actor 가 읽는 필드'
    assert data['client_id'] == tokens.PERSONAL_CLIENT_ID
    assert not get_access_token_model().objects.filter(token=raw).exists(), (
        'RFC 9700: 원문은 저장되지 않고 체크섬만 남는다'
    )


def test_도구함이_바뀌면_토큰_스코프가_따라간다(client, user, catalog, rs):
    raw = tokens.issue(user)
    assert _introspect(client, rs, raw).json()['scope'] == ''
    client.force_login(user)
    client.post('/toolbox/add/weather/')
    assert _introspect(client, rs, raw).json()['scope'] == 'tool:weather'
    client.post('/toolbox/remove/weather/')
    assert _introspect(client, rs, raw).json()['scope'] == ''


def test_재발급은_이전_토큰을_폐기한다(client, user, catalog, rs):
    first = tokens.issue(user)
    second = tokens.issue(user)
    assert _introspect(client, rs, first).json() == {'active': False}
    assert _introspect(client, rs, second).json()['active'] is True
    tokens.revoke(user)
    assert _introspect(client, rs, second).json() == {'active': False}
    assert tokens.active(user) is None


def test_틀린_리소스_서버_자격은_introspection_을_못_한다(client, user, catalog, rs):
    raw = tokens.issue(user)
    response = _introspect(client, ('rs', 'wrong'), raw)
    assert response.status_code in (401, 403), response.status_code


def test_화면_발급은_한_번만_보여준다(client, user, catalog):
    client.force_login(user)
    redirect = client.post('/toolbox/token/issue/')
    assert redirect.status_code == 302 and redirect['Location'].endswith('/toolbox/token/')
    page = client.get('/toolbox/token/')
    assert page.status_code == 200
    raw = page.context['token']
    assert raw in page.content.decode() and 'claude mcp add' in page.content.decode()
    again = client.get('/toolbox/token/')
    assert again.status_code == 302, '두 번째 열람은 도구함으로 돌려보낸다'
    home = client.get('/toolbox/')
    assert raw not in home.content.decode(), '도구함 화면에 원문이 남지 않는다'
    assert '재발급' in home.content.decode()


def test_issue_token_커맨드는_도구함을_채우고_원문만_stdout_에_찍는다(
    user, catalog, capsys, monkeypatch
):
    monkeypatch.setenv('SHARED_KOSIS_API_KEY', 'shared')
    call_command('issue_token', email='ALICE@example.com', tools='weather,kosis', shared=True)
    out, err = capsys.readouterr()
    raw = out.strip()
    assert raw and '\n' not in raw, 'stdout 은 토큰 한 줄뿐'
    assert 'tool:kosis tool:weather' in err and raw not in err
    entry = ToolboxEntry.objects.get(user=user, tool__slug='kosis')
    assert entry.use_shared_credential is True
    assert tokens.active(user).scope == 'tool:kosis tool:weather'
