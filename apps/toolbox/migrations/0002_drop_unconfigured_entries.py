"""설정 없이 담겼던 항목을 걷어 낸다 — '담긴 도구는 곧 호출할 수 있는 도구' 불변식(`is_configured`)의 소급 적용.

자격증명이 필요한데 사용자 키도 없고, 공용 키를 켜지 않았거나 켰어도 공용 키가 없는 항목이 대상이다.
이런 항목은 스코프에만 실리고 호출은 늘 거부됐다. 되돌리기는 하지 않는다(다시 담으면 된다).
"""

import os

from django.db import migrations


def drop_unconfigured(apps, schema_editor):
    ToolboxEntry = apps.get_model('toolbox', 'ToolboxEntry')
    ToolSetting = apps.get_model('toolbox', 'ToolSetting')
    with_value = set(ToolSetting.objects.exclude(ciphertext='').values_list('entry_id', flat=True))
    for entry in ToolboxEntry.objects.exclude(tool__credential='none').select_related('tool'):
        if entry.id in with_value:
            continue
        tool = entry.tool
        shared = (
            entry.use_shared_credential
            and tool.credential == 'shared'
            and tool.setting_key
            and os.environ.get(f'SHARED_{tool.setting_key}', '')
        )
        if not shared:
            entry.delete()


class Migration(migrations.Migration):
    dependencies = [('toolbox', '0001_initial')]

    operations = [migrations.RunPython(drop_unconfigured, migrations.RunPython.noop)]
