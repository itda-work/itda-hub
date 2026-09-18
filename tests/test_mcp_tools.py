"""도구 선언 — 스코프 대응과 자격증명 해석. 네트워크는 부르지 않는다."""

import pytest
from django_itda.results import ToolDenied

from apps.catalog.models import Tool
from apps.toolbox.models import ToolboxEntry, ToolSetting
from mcp_server.tools import specs
from mcp_server.tools.credentials import resolve


def test_도구마다_카탈로그_스코프가_붙는다():
    by_name = {s.name: s.scope for s in specs()}
    assert by_name == {'weather_now': 'tool:weather', 'kosis_search': 'tool:kosis'}
    for s in specs():
        assert 'actor' not in s.signature.parameters, '자리는 모델이 고르지 못해야 한다'


@pytest.fixture
def kosis(db):
    from django.core.management import call_command

    call_command('seed_catalog', verbosity=0)
    return Tool.objects.get(slug='kosis')


def test_도구함에_없으면_거부(user, kosis):
    with pytest.raises(ToolDenied):
        resolve(user, 'kosis')


def test_사용자_키가_우선하고_없으면_공용_키(user, kosis, monkeypatch):
    entry = ToolboxEntry.objects.create(user=user, tool=kosis)
    with pytest.raises(ToolDenied):
        resolve(user, 'kosis')
    entry.use_shared_credential = True
    entry.save()
    monkeypatch.setenv('SHARED_KOSIS_API_KEY', 'shared-key')
    assert resolve(user, 'kosis') == 'shared-key'
    s = ToolSetting(entry=entry, key='KOSIS_API_KEY')
    s.set_value('my-key')
    s.save()
    assert resolve(user, 'kosis') == 'my-key'
