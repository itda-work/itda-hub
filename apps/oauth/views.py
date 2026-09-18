"""인가 뷰 — 동의 화면에서 스코프를 도구함으로 좁힌다.

Claude 는 메타데이터에 광고된 카탈로그 전체 스코프를 요청한다. 유효성 검사(백엔드)는 그것을 전부
통과시키고, **이 사용자에게 실제로 주는 범위**는 여기서 도구함과 교집합을 낸다. 그래서 동의 화면에도
토큰에도 도구함의 스코프만 실린다. 폼 POST 로 스코프를 넓히는 시도도 같은 교집합에 걸린다.
"""

from django.shortcuts import render
from oauth2_provider.views import AuthorizationView

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
        if getattr(response, 'context_data', None) is not None and not response.context_data.get(
            'scopes'
        ):
            return render(request, 'oauth/empty_toolbox.html', status=200)
        return response

    def form_valid(self, form):
        requested = (form.cleaned_data.get('scope') or '').split()
        form.cleaned_data['scope'] = ' '.join(self._narrow(requested))
        return super().form_valid(form)
