"""스코프 = 도구함. 담은 도구만 허용 스코프에 나타난다."""

import pytest

from apps.catalog.models import Tool
from apps.oauth.scopes import CatalogScopes
from apps.toolbox.models import ToolboxEntry, ToolSetting, granted_scopes


@pytest.fixture
def tools(db):
    from django.core.management import call_command

    call_command('seed_catalog', verbosity=0)
    return {t.slug: t for t in Tool.objects.all()}


def test_담은_도구만_스코프가_된다(user, tools):
    assert granted_scopes(user) == []
    ToolboxEntry.objects.create(user=user, tool=tools['weather'])
    assert granted_scopes(user) == ['tool:weather']


def test_스코프_백엔드는_카탈로그_전체를_유효_스코프로_본다(user, tools):
    """도구함으로 좁히는 일은 인가 뷰의 몫이다. 백엔드가 좁히면 전체 스코프 요청이 invalid_scope 로 거절된다."""
    backend = CatalogScopes()
    assert set(backend.get_available_scopes()) == {'tool:kosis', 'tool:weather'}
    assert 'tool:fx' not in backend.get_all_scopes(), '비공개 도구는 스코프가 아니다'


def test_설정_값은_암호화돼_저장되고_복호화로만_읽힌다(user, tools):
    entry = ToolboxEntry.objects.create(user=user, tool=tools['kosis'])
    s = ToolSetting(entry=entry, key='KOSIS_API_KEY')
    s.set_value('secret-123')
    s.save()
    stored = ToolSetting.objects.get(pk=s.pk)
    assert 'secret-123' not in stored.ciphertext
    assert stored.get_value() == 'secret-123'
