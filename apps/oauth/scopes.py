"""스코프 백엔드 — 카탈로그 전체가 유효한 스코프다.

django-oauth-toolkit 은 인가 요청·토큰 발급·메타데이터에서 모두 이 백엔드를 묻는다. 여기서 도구함으로
좁히면 Claude 가 메타데이터에 광고된 전체 스코프를 요청할 때 `invalid_scope` 로 거절되고, 토큰
엔드포인트(사용자 세션 없음)에서도 검증이 깨진다. 그래서 **유효 여부는 카탈로그가, 이 사용자에게 주는
범위는 인가 뷰(`apps.oauth.views.ToolboxAuthorizationView`)가** 정한다.
"""

from oauth2_provider.scopes import BaseScopes

from apps.catalog.models import scope_choices


class CatalogScopes(BaseScopes):
    def get_all_scopes(self):
        return scope_choices()

    def get_available_scopes(self, application=None, request=None, *args, **kwargs):
        return list(scope_choices().keys())

    def get_default_scopes(self, application=None, request=None, *args, **kwargs):
        return self.get_available_scopes(application=application, request=request)
