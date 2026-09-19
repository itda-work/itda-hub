"""도구함 화면 — 카탈로그에서 담기·빼기, 도구별 설정, 커스텀 커넥터(OAuth) 연결 안내.

연결 토큰은 화면에 내지 않는다(OAuth 커넥터만 노출) — 발급은 운영·스모크용 `issue_token` 커맨드뿐이다.
자격증명이 필요한 도구는 담기가 곧 설정이다 — 설정 화면에서 저장해야 도구함에 들어간다.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Tool

from . import tokens
from .models import ToolboxEntry, ToolSetting, is_configured


@login_required
def home(request):
    tools = Tool.objects.filter(enabled=True)
    mine = {
        e.tool_id: e
        for e in ToolboxEntry.objects.filter(user=request.user).select_related('setting')
    }
    rows = [(t, mine.get(t.id)) for t in tools]
    return render(
        request,
        'toolbox/home.html',
        {'rows': rows, 'mcp_url': settings.HUB_MCP_URL},
    )


@login_required
@require_POST
def add(request, slug):
    tool = get_object_or_404(Tool, slug=slug, enabled=True)
    if tool.needs_setting:
        # 설정 없이 담으면 스코프에는 실리고 호출은 거부되는 도구가 된다. 설정 화면이 담기를 맡는다.
        return redirect('toolbox:setting', slug=tool.slug)
    ToolboxEntry.objects.get_or_create(user=request.user, tool=tool)
    tokens.sync_scope(request.user)
    messages.success(
        request, f'{tool.name} 을(를) 도구함에 담았습니다. 다음 연결부터 스코프에 나타납니다.'
    )
    return redirect('toolbox:home')


@login_required
@require_POST
def remove(request, slug):
    ToolboxEntry.objects.filter(user=request.user, tool__slug=slug).delete()
    tokens.sync_scope(request.user)
    messages.success(
        request,
        '도구함에서 뺐습니다. 커넥터의 스코프는 다음 토큰 갱신에서 줄어듭니다.',
    )
    return redirect('toolbox:home')


@login_required
def setting(request, slug):
    """도구 설정. 아직 담지 않은 도구면 저장이 곧 담기다 — 설정을 마쳐야만 도구함에 들어간다."""
    tool = get_object_or_404(Tool, slug=slug, enabled=True)
    if not tool.needs_setting:
        raise Http404('설정이 없는 도구')
    entry = ToolboxEntry.objects.filter(user=request.user, tool=tool).first()
    has_value = entry is not None and entry.stored_value()
    shared_available = bool(tool.shared_value())
    # 처음 담는 도구는 공용 키가 있으면 그것을 기본으로 켠다 — 키 없이 한 번에 담을 수 있게.
    use_shared = entry.use_shared_credential if entry else shared_available
    error = ''
    if request.method == 'POST':
        use_shared = (
            bool(request.POST.get('use_shared')) and tool.credential == Tool.Credential.SHARED
        )
        value = request.POST.get('value', '').strip()
        if is_configured(tool, has_value=has_value or bool(value), use_shared=use_shared):
            with transaction.atomic():
                entry, created = ToolboxEntry.objects.get_or_create(user=request.user, tool=tool)
                entry.use_shared_credential = use_shared
                entry.save(update_fields=['use_shared_credential'])
                if value:
                    obj, _ = ToolSetting.objects.get_or_create(
                        entry=entry, defaults={'key': tool.setting_key, 'ciphertext': ''}
                    )
                    obj.key = tool.setting_key
                    obj.set_value(value)
                    obj.save()
            if created:
                tokens.sync_scope(request.user)
                messages.success(
                    request,
                    f'{tool.name} 을(를) 설정하고 도구함에 담았습니다. 다음 연결부터 스코프에 나타납니다.',
                )
            else:
                messages.success(
                    request,
                    '설정을 저장했습니다.' + (' 값은 다시 표시되지 않습니다.' if value else ''),
                )
            return redirect('toolbox:home')
        error = (
            f'{tool.setting_key} 를 입력하거나 관리자 공용 키 사용을 켜야 합니다.'
            if shared_available
            else f'{tool.setting_key} 를 입력해야 합니다.'
        )
    return render(
        request,
        'toolbox/setting.html',
        {
            'entry': entry,
            'tool': tool,
            'has_value': has_value,
            'shared_available': shared_available,
            'use_shared': use_shared,
            'error': error,
        },
        status=400 if error else 200,
    )
