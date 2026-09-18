"""부팅 시 환경변수로 보장하는 것들 — 멱등. compose 의 entrypoint 가 migrate·seed_catalog 다음에 부른다.

1. introspection 리소스 서버 Application (HUB_INTROSPECTION_CLIENT_ID/SECRET) — MCP 프로세스가 토큰을 검증하는 자격.
2. 연결 토큰용 내장 Application (apps.toolbox.tokens.personal_application).
3. 관리자 계정 (HUB_ADMIN_EMAIL/PASSWORD 둘 다 있을 때만). 이미 있으면 비밀번호를 건드리지 않는다.

비밀 값은 어떤 출력에도 싣지 않는다.
"""

import os

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.management.base import BaseCommand
from oauth2_provider.models import get_application_model

from apps.toolbox import tokens


class Command(BaseCommand):
    help = '환경변수로 introspection 앱·연결 토큰 앱·관리자 계정을 보장한다(멱등)'

    def handle(self, *args, **options):
        self._introspection_app()
        tokens.personal_application()
        self.stdout.write(f'연결 토큰 앱 보장: client_id={tokens.PERSONAL_CLIENT_ID}')
        self._admin()

    def _introspection_app(self):
        client_id = os.environ.get('HUB_INTROSPECTION_CLIENT_ID', '').strip()
        secret = os.environ.get('HUB_INTROSPECTION_CLIENT_SECRET', '')
        if not client_id or not secret:
            self.stderr.write(
                '경고: HUB_INTROSPECTION_CLIENT_ID/SECRET 이 비어 있다 — MCP 프로세스가 토큰을 검증할 수 없다'
            )
            return
        Application = get_application_model()
        app, created = Application.objects.get_or_create(
            client_id=client_id,
            defaults={
                'name': '잇다 허브 MCP 리소스 서버',
                'client_type': Application.CLIENT_CONFIDENTIAL,
                'authorization_grant_type': Application.GRANT_CLIENT_CREDENTIALS,
                'redirect_uris': '',
                'client_secret': secret,
            },
        )
        state = '생성'
        if not created and not check_password(secret, app.client_secret):
            # 시크릿이 바뀌었다(.env 회전). 저장 시 DOT 가 해시한다.
            app.client_secret = secret
            app.save(update_fields=['client_secret'])
            state = '시크릿 갱신'
        elif not created:
            state = '유지'
        self.stdout.write(f'introspection 앱 {state}: client_id={client_id}')

    def _admin(self):
        email = os.environ.get('HUB_ADMIN_EMAIL', '').strip().lower()
        password = os.environ.get('HUB_ADMIN_PASSWORD', '')
        if not email or not password:
            self.stdout.write('관리자 계정: HUB_ADMIN_EMAIL/PASSWORD 없음 — 건너뜀')
            return
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_superuser(username=email, email=email, password=password)
            state = '생성'
        else:
            state = '유지(비밀번호 불변)'
        if not (user.is_staff and user.is_superuser):
            user.is_staff = user.is_superuser = True
            user.save(update_fields=['is_staff', 'is_superuser'])
        EmailAddress.objects.get_or_create(
            user=user, email=email, defaults={'verified': True, 'primary': True}
        )
        self.stdout.write(f'관리자 계정 {state}: {email}')
