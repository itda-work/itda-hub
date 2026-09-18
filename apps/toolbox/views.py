"""도구함 화면 — 카탈로그에서 담기·빼기, 도구별 설정."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Tool

from .models import ToolboxEntry, ToolSetting


@login_required
def home(request):
    tools = Tool.objects.filter(enabled=True)
    mine = {
        e.tool_id: e
        for e in ToolboxEntry.objects.filter(user=request.user).select_related('setting')
    }
    rows = [(t, mine.get(t.id)) for t in tools]
    return render(request, 'toolbox/home.html', {'rows': rows})


@login_required
@require_POST
def add(request, slug):
    tool = get_object_or_404(Tool, slug=slug, enabled=True)
    ToolboxEntry.objects.get_or_create(user=request.user, tool=tool)
    messages.success(
        request, f'{tool.name} 을(를) 도구함에 담았습니다. 다음 연결부터 스코프에 나타납니다.'
    )
    return redirect('toolbox:home')


@login_required
@require_POST
def remove(request, slug):
    ToolboxEntry.objects.filter(user=request.user, tool__slug=slug).delete()
    messages.success(
        request, '도구함에서 뺐습니다. 이미 발급된 토큰의 스코프는 다음 갱신에서 줄어듭니다.'
    )
    return redirect('toolbox:home')


@login_required
def setting(request, slug):
    entry = get_object_or_404(ToolboxEntry, user=request.user, tool__slug=slug)
    tool = entry.tool
    if request.method == 'POST':
        entry.use_shared_credential = (
            bool(request.POST.get('use_shared')) and tool.credential == Tool.Credential.SHARED
        )
        entry.save(update_fields=['use_shared_credential'])
        value = request.POST.get('value', '').strip()
        if value:
            obj, _ = ToolSetting.objects.get_or_create(
                entry=entry, defaults={'key': tool.setting_key, 'ciphertext': ''}
            )
            obj.key = tool.setting_key
            obj.set_value(value)
            obj.save()
            messages.success(request, '설정을 저장했습니다. 값은 다시 표시되지 않습니다.')
        return redirect('toolbox:home')
    has_value = hasattr(entry, 'setting') and bool(entry.setting.ciphertext)
    return render(
        request, 'toolbox/setting.html', {'entry': entry, 'tool': tool, 'has_value': has_value}
    )
