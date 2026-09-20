"""연결 토큰 — OAuth 왕복 없이 MCP 클라이언트(Claude Code 등)를 붙이는 개인 토큰.

django-oauth-toolkit 의 AccessToken 을 그대로 쓴다(별도 모델 없음). 그래서 MCP 프로세스의 introspection
검증 경로가 OAuth 토큰과 완전히 같다 — 검증 코드가 두 벌이 되지 않는다. 다른 것은 발급 경로뿐이다:
동의 화면 대신 `manage.py issue_token` 커맨드가 만들고(0.4.0 부터 화면 버튼은 없다 — 사용자에게는
OAuth 커넥터만 노출한다), 스코프는 발급 시점의 도구함이며
도구함이 바뀌면 따라간다(OAuth 토큰은 다음 갱신 때 좁혀진다).

원문은 발급 순간의 반환값으로만 나간다. 저장은 체크섬뿐이다(RFC 9700 — settings 의
COMPLIANT_BCP_RFC9700_TOKEN_STORAGE). 잃어버리면 재발급이 유일한 길이다.
"""

import secrets
from datetime import timedelta

from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model, set_token_value

from .models import granted_scopes

PERSONAL_CLIENT_ID = 'hub-personal'
TOKEN_DAYS = 30


def personal_application():
    """연결 토큰이 매달리는 내장 Application. 토큰 엔드포인트로는 쓰이지 않는다(시크릿은 무작위·미공개)."""
    Application = get_application_model()
    app, _ = Application.objects.get_or_create(
        client_id=PERSONAL_CLIENT_ID,
        defaults={
            'name': '잇다 허브 연결 토큰',
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_CLIENT_CREDENTIALS,
            'redirect_uris': '',
            'client_secret': secrets.token_urlsafe(32),
        },
    )
    return app


def _mine(user):
    return get_access_token_model().objects.filter(
        user=user, application__client_id=PERSONAL_CLIENT_ID
    )


def active(user):
    """살아 있는 연결 토큰(없으면 None). 사용자당 하나만 둔다."""
    return _mine(user).filter(expires__gt=timezone.now()).order_by('-created').first()


def issue(user) -> str:
    """새 토큰을 만들고 원문을 돌려준다. 이전 토큰은 폐기한다."""
    _mine(user).delete()
    raw = secrets.token_urlsafe(32)
    token = get_access_token_model()(
        user=user,
        application=personal_application(),
        expires=timezone.now() + timedelta(days=TOKEN_DAYS),
        scope=' '.join(granted_scopes(user)),
    )
    set_token_value(token, raw)
    token.save()
    return raw


def revoke(user) -> int:
    deleted, _ = _mine(user).delete()
    return deleted


def sync_scope(user) -> None:
    """도구함이 바뀌면 살아 있는 연결 토큰의 스코프를 도구함에 맞춘다. introspection 은 캐시가 없어 즉시 반영된다."""
    _mine(user).update(scope=' '.join(granted_scopes(user)))
