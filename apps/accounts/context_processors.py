"""템플릿에 가입 정책을 싣는다 — 로그인 화면이 닫힌 가입으로 가는 링크를 내지 않게."""

from django.conf import settings


def signup(request):
    return {'HUB_LOCAL_SIGNUP': settings.HUB_LOCAL_SIGNUP}
