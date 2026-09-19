"""인가 뷰 — 동의 화면에서 스코프를 도구함으로 좁힌다.

Claude 는 메타데이터에 광고된 카탈로그 전체 스코프를 요청한다. 유효성 검사(백엔드)는 그것을 전부
통과시키고, **이 사용자에게 실제로 주는 범위**는 여기서 도구함과 교집합을 낸다. 그래서 동의 화면에도
토큰에도 도구함의 스코프만 실린다.

발급 관문은 `create_authorization_response` 하나다 — 동의 폼 POST·`skip_authorization`·`approval_prompt=auto`
세 경로가 모두 여기를 지난다. 교집합이 비면 거부한다: 빈 스코프는 DOT 에서 기본 스코프(= 카탈로그 전체,
`CatalogScopes.get_default_scopes`)로 바뀌므로 그대로 넘기면 도구함에 없는 도구까지 토큰에 실린다.
"""

from django.shortcuts import render
from oauth2_provider.cimd import is_cimd_client_id
from oauth2_provider.exceptions import OAuthToolkitError
from oauth2_provider.settings import oauth2_settings
from oauth2_provider.views import AuthorizationView
from oauthlib.oauth2 import AccessDeniedError
from oauthlib.oauth2.rfc6749.errors import InvalidClientIdError

from apps.toolbox.models import granted_scopes


class ToolboxAuthorizationView(AuthorizationView):
    def _narrow(self, scopes):
        allowed = set(granted_scopes(self.request.user))
        return [s for s in scopes if s in allowed]

    def validate_authorization_request(self, request):
        scopes, credentials = super().validate_authorization_request(request)
        return self._narrow(scopes), credentials

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        context = getattr(response, 'context_data', None)
        if context is None:
            return response  # 리디렉트(오류 콜백·자동 승인)
        if context.get('error'):
            # 검증 실패 — DOT 오류 화면. 「빈 도구함」 으로 바꾸면 원인이 가려진다.
            # CIMD 해석이 실패하면 DOT 는 클라이언트를 모르는 것으로 본다(InvalidClientIdError). 원인은 서버 로그에만 있다.
            client_id = request.GET.get('client_id', '')
            if (
                isinstance(context['error'], InvalidClientIdError)
                and oauth2_settings.CIMD_ENABLED
                and is_cimd_client_id(client_id)
            ):
                context['cimd_client_id'] = client_id
                context['cimd_retry_seconds'] = oauth2_settings.CIMD_FAILURE_BACKOFF_SECONDS
            return response
        if not context.get('scopes'):
            # 검증은 통과했고 요청 스코프와 도구함의 교집합이 비었다.
            return render(request, 'oauth/empty_toolbox.html', status=200)
        return response

    def create_authorization_response(self, request, scopes, credentials, allow):
        narrowed = self._narrow((scopes or '').split())
        if allow and not narrowed:
            # 클라이언트에게 access_denied 로 돌려보낸다(state 포함) — 코드도 Grant 도 만들지 않는다.
            raise OAuthToolkitError(
                error=AccessDeniedError(state=credentials.get('state')),
                redirect_uri=credentials.get('redirect_uri'),
            )
        return super().create_authorization_response(
            request, ' '.join(narrowed), credentials, allow
        )
