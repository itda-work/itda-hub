"""URL 배선.

- `/o/` 인가 서버(authorize·token·introspect·register). RFC 8414·9728 메타데이터는 루트 `/.well-known/` 에 따로 건다.
- `/mcp` 는 이 프로세스가 아니다. 리버스 프록시가 MCP 프로세스로 보낸다.
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from oauth2_provider.urls import metadata_urlpatterns

from apps.oauth.views import ToolboxAuthorizationView
from hub.views import healthz

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='toolbox:home', permanent=False)),
    path('healthz', healthz, name='healthz'),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    # 동의 화면은 도구함으로 좁힌 뷰가 먼저 잡는다. 나머지 /o/* 는 DOT 그대로.
    path('o/authorize/', ToolboxAuthorizationView.as_view(), name='hub-authorize'),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('', include((metadata_urlpatterns, 'oauth2_provider_metadata'))),
    path('toolbox/', include('apps.toolbox.urls')),
    path('trajectory/', include('apps.trajectory.urls')),
]
