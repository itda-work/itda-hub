"""bootstrap — 환경변수로 앱·관리자 계정을 보장한다. 멱등이고 비밀은 출력에 없다."""

from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from oauth2_provider.models import get_application_model


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_ID', 'hub-mcp')
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', 'first-secret')
    monkeypatch.setenv('HUB_ADMIN_EMAIL', 'Admin@Example.com')
    monkeypatch.setenv('HUB_ADMIN_PASSWORD', 'admin-pass-1')


def _run():
    out, err = StringIO(), StringIO()
    call_command('bootstrap', stdout=out, stderr=err)
    return out.getvalue() + err.getvalue()


def test_두_번_돌려도_하나씩이고_비밀은_출력에_없다(db, env):
    text = _run() + _run()
    Application = get_application_model()
    assert Application.objects.filter(client_id='hub-mcp').count() == 1
    assert Application.objects.filter(client_id='hub-personal').count() == 1
    app = Application.objects.get(client_id='hub-mcp')
    assert app.client_type == Application.CLIENT_CONFIDENTIAL
    assert check_password('first-secret', app.client_secret), 'DOT 가 해시해 저장한다'
    user = get_user_model().objects.get(email='admin@example.com')
    assert user.is_superuser and user.is_staff and user.check_password('admin-pass-1')
    assert EmailAddress.objects.filter(user=user, email='admin@example.com', verified=True).exists()
    for secret in ('first-secret', 'admin-pass-1'):
        assert secret not in text


def test_시크릿이_바뀌면_앱을_갱신하고_관리자_비밀번호는_유지한다(db, env, monkeypatch):
    _run()
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', 'rotated')
    monkeypatch.setenv('HUB_ADMIN_PASSWORD', 'changed-in-env')
    text = _run()
    app = get_application_model().objects.get(client_id='hub-mcp')
    assert check_password('rotated', app.client_secret)
    assert '시크릿 갱신' in text
    user = get_user_model().objects.get(email='admin@example.com')
    assert user.check_password('admin-pass-1'), '이미 있는 계정의 비밀번호는 건드리지 않는다'


def test_자격이_없으면_경고만_하고_나머지는_진행한다(db, monkeypatch):
    for name in (
        'HUB_INTROSPECTION_CLIENT_ID',
        'HUB_INTROSPECTION_CLIENT_SECRET',
        'HUB_ADMIN_EMAIL',
    ):
        monkeypatch.delenv(name, raising=False)
    text = _run()
    assert '경고' in text and 'hub-personal' in text
    assert get_application_model().objects.filter(client_id='hub-personal').exists()
