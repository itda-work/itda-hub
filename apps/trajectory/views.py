"""궤적 — 내 도구 호출 이력. django-itda 의 ToolCall 을 그대로 읽는다. 값(인자)은 보여 주되 비밀은 없다:
도구 인자에 자격증명이 실리지 않도록 어댑터가 설계돼 있다."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django_itda.models import ToolCall


@login_required
def mine(request):
    calls = ToolCall.objects.filter(actor=request.user).order_by('-started_at')[:100]
    return render(request, 'trajectory/mine.html', {'calls': calls})
