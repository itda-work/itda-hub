"""설정이 필요한 도구는 설정을 마쳐야 담긴다 — '담긴 도구는 곧 호출할 수 있는 도구' 불변식."""

from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.core.management import CommandError, call_command

from apps.catalog.models import Tool
from apps.toolbox import tokens
from apps.toolbox.models import ToolboxEntry, ToolSetting, granted_scopes


@pytest.fixture
def catalog(db):
    call_command('seed_catalog', verbosity=0)
    return {t.slug: t for t in Tool.objects.all()}


@pytest.fixture
def no_shared(monkeypatch):
    monkeypatch.delenv('SHARED_KOSIS_API_KEY', raising=False)


def test_설정이_필요한_도구는_담기_요청이_설정_화면으로_간다(client, user, catalog):
    client.force_login(user)
    response = client.post('/toolbox/add/kosis/')
    assert response.status_code == 302 and response['Location'] == '/toolbox/setting/kosis/'
    assert granted_scopes(user) == [], '설정 전에는 담기지 않는다'


def test_설정_불요_도구는_바로_담긴다(client, user, catalog):
    client.force_login(user)
    client.post('/toolbox/add/weather/')
    assert granted_scopes(user) == ['tool:weather']


def test_아직_안_담은_도구의_설정_화면은_저장하고_담기다(client, user, catalog, no_shared):
    client.force_login(user)
    html = client.get('/toolbox/setting/kosis/').content.decode()
    assert '저장하고 담기' in html
    assert 'name="use_shared"' not in html, '공용 키가 없으면 공용 키 선택지를 내지 않는다'


def test_빈_설정으로는_담기지_않는다(client, user, catalog, no_shared):
    client.force_login(user)
    response = client.post('/toolbox/setting/kosis/', {'value': '', 'use_shared': 'on'})
    assert response.status_code == 400
    assert 'KOSIS_API_KEY 를 입력해야 합니다.' in response.content.decode()
    assert not ToolboxEntry.objects.filter(user=user).exists()


def test_사용자_키를_저장하면_담기고_토큰_스코프가_따라간다(client, user, catalog, no_shared):
    tokens.issue(user)
    client.force_login(user)
    response = client.post('/toolbox/setting/kosis/', {'value': 'my-key'})
    assert response.status_code == 302
    entry = ToolboxEntry.objects.get(user=user, tool=catalog['kosis'])
    assert entry.setting.get_value() == 'my-key'
    assert tokens.active(user).scope == 'tool:kosis'


def test_공용_키가_있으면_기본으로_켜져_한_번에_담긴다(client, user, catalog, monkeypatch):
    monkeypatch.setenv('SHARED_KOSIS_API_KEY', 'shared')
    client.force_login(user)
    html = client.get('/toolbox/setting/kosis/').content.decode()
    assert 'name="use_shared" checked' in html
    client.post('/toolbox/setting/kosis/', {'use_shared': 'on'})
    entry = ToolboxEntry.objects.get(user=user, tool=catalog['kosis'])
    assert entry.use_shared_credential is True and not entry.stored_value()


def test_공용_키를_켜도_실제_공용_키가_없으면_담기지_않는다(client, user, catalog, no_shared):
    client.force_login(user)
    assert client.post('/toolbox/setting/kosis/', {'use_shared': 'on'}).status_code == 400
    assert granted_scopes(user) == []


def test_담긴_도구를_미설정_상태로_되돌릴_수_없다(client, user, catalog, monkeypatch):
    monkeypatch.setenv('SHARED_KOSIS_API_KEY', 'shared')
    entry = ToolboxEntry.objects.create(
        user=user, tool=catalog['kosis'], use_shared_credential=True
    )
    client.force_login(user)
    assert client.post('/toolbox/setting/kosis/', {}).status_code == 400
    entry.refresh_from_db()
    assert entry.use_shared_credential is True


def test_저장된_키가_있으면_빈_값으로_다시_저장해도_유지된다(client, user, catalog, no_shared):
    entry = ToolboxEntry.objects.create(user=user, tool=catalog['kosis'])
    s = ToolSetting(entry=entry, key='KOSIS_API_KEY')
    s.set_value('kept')
    s.save()
    client.force_login(user)
    assert client.post('/toolbox/setting/kosis/', {'value': ''}).status_code == 302
    assert ToolSetting.objects.get(entry=entry).get_value() == 'kept'


def test_설정_불요_도구에는_설정_화면이_없다(client, user, catalog):
    client.force_login(user)
    assert client.get('/toolbox/setting/weather/').status_code == 404


def test_도구함_카드_토글(client, user, catalog, no_shared):
    client.force_login(user)
    html = client.get('/toolbox/').content.decode()
    assert 'href="/toolbox/setting/kosis/" class="tool-toggle' in html
    assert 'aria-label="KOSIS 국가통계 설정하고 담기"' in html
    assert 'action="/toolbox/add/kosis/"' not in html, '설정 필요 도구는 바로 담는 폼을 내지 않는다'
    assert 'action="/toolbox/add/weather/"' in html


def test_issue_token_은_설정_없이_담지_않는다(user, catalog, no_shared):
    with pytest.raises(CommandError, match='설정이 필요하다'):
        call_command('issue_token', email=user.email, tools='kosis')
    assert not ToolboxEntry.objects.filter(user=user).exists()


def test_마이그레이션은_설정_없이_담겼던_항목만_걷어낸다(
    user, catalog, django_user_model, monkeypatch
):
    migration = import_module('apps.toolbox.migrations.0002_drop_unconfigured_entries')
    bob = django_user_model.objects.create_user(username='bob', email='b@example.com')
    carol = django_user_model.objects.create_user(username='carol', email='c@example.com')
    dave = django_user_model.objects.create_user(username='dave', email='d@example.com')
    bare = ToolboxEntry.objects.create(user=user, tool=catalog['kosis'])
    keyed = ToolboxEntry.objects.create(user=bob, tool=catalog['kosis'])
    s = ToolSetting(entry=keyed, key='KOSIS_API_KEY')
    s.set_value('k')
    s.save()
    shared = ToolboxEntry.objects.create(
        user=carol, tool=catalog['kosis'], use_shared_credential=True
    )
    free = ToolboxEntry.objects.create(user=dave, tool=catalog['weather'])

    monkeypatch.setenv('SHARED_KOSIS_API_KEY', 'shared')
    migration.drop_unconfigured(django_apps, None)
    remaining = set(ToolboxEntry.objects.values_list('pk', flat=True))
    assert remaining == {keyed.pk, shared.pk, free.pk}
    assert bare.pk not in remaining

    monkeypatch.delenv('SHARED_KOSIS_API_KEY')
    migration.drop_unconfigured(django_apps, None)
    assert shared.pk not in set(ToolboxEntry.objects.values_list('pk', flat=True)), (
        '공용 키를 켰어도 공용 키가 없으면 호출할 수 없는 항목이다'
    )
