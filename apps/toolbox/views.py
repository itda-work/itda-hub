"""도구함 화면 — 카탈로그에서 담기·빼기, 도구별 설정, 연결 토큰."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Tool

from . import tokens
from .models import ToolboxEntry, ToolSetting, granted_scopes

TOKEN_SESSION_KEY = 'hub_token_once'


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
        {'rows': rows, 'token': tokens.active(request.user), 'mcp_url': settings.HUB_MCP_URL},
    )


@login_required
@require_POST
def add(request, slug):
    tool = get_object_or_404(Tool, slug=slug, enabled=True)
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
        '도구함에서 뺐습니다. 연결 토큰은 즉시, OAuth 토큰은 다음 갱신에서 스코프가 줄어듭니다.',
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


@login_required
@require_POST
def token_issue(request):
    """발급 → 세션에 잠깐 두고 → GET 화면에서 한 번 꺼내 보여 준다(PRG). 새로고침으로 재발급되지 않는다."""
    request.session[TOKEN_SESSION_KEY] = tokens.issue(request.user)
    return redirect('toolbox:token')


@login_required
def token_show(request):
    raw = request.session.pop(TOKEN_SESSION_KEY, None)
    if not raw:
        messages.info(request, '보여 줄 새 토큰이 없습니다. 필요하면 재발급하세요.')
        return redirect('toolbox:home')
    return render(
        request,
        'toolbox/token.html',
        {
            'token': raw,
            'mcp_url': settings.HUB_MCP_URL,
            'days': tokens.TOKEN_DAYS,
            'scopes': granted_scopes(request.user),
        },
    )


@login_required
@require_POST
def token_revoke(request):
    tokens.revoke(request.user)
    messages.success(
        request,
        '연결 토큰을 폐기했습니다. 그 토큰으로 붙어 있던 클라이언트는 다음 호출부터 거부됩니다.',
    )
    return redirect('toolbox:home')
