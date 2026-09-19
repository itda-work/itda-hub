"""가입 정책 — 누가 계정을 **새로** 만들 수 있나. 로그인 수단(무엇으로 들어오나)과는 따로 정한다.

- Google 이 켜져 있으면(`GOOGLE_OAUTH_CLIENT_ID`) 새 계정은 Google 로만 생긴다. 이메일+비밀번호 가입은 닫힌다.
  `HUB_LOCAL_LOGIN=1` 은 이때 "이미 있는 로컬 계정(비상용 관리자)의 로그인" 만 뜻한다.
- Google 이 꺼져 있으면(로컬·자체 호스팅) 이메일+비밀번호 가입이 열린다.

판정은 `settings.HUB_LOCAL_SIGNUP` 한 곳에서 낸다.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return settings.HUB_LOCAL_SIGNUP


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        # 기본 구현은 계정 어댑터(로컬 가입)를 따른다 — 그러면 로컬 가입을 닫을 때 Google 가입까지 닫힌다.
        return True
