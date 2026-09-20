"""연결 토큰 발급 CLI — 사용자 화면에는 없는 유일한 발급 경로다. 운영·스모크·자동화용.

토큰 원문은 stdout 에 **그것만** 찍는다(`TOKEN=$(manage.py issue_token --email …)` 로 받도록). 나머지는 stderr.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Tool
from apps.toolbox import tokens
from apps.toolbox.models import ToolboxEntry, is_configured


class Command(BaseCommand):
    help = '사용자의 연결 토큰을 발급한다(이전 토큰 폐기). --tools 로 도구함을 함께 채운다.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='허브 사용자 이메일')
        parser.add_argument('--tools', default='', help='함께 담을 도구 slug (쉼표 구분)')
        parser.add_argument(
            '--shared', action='store_true', help='담는 도구에 관리자 공용 키 사용을 켠다'
        )

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email__iexact=options['email']).first()
        if user is None:
            raise CommandError(f'사용자가 없다: {options["email"]}')
        for slug in [s.strip() for s in options['tools'].split(',') if s.strip()]:
            tool = Tool.objects.filter(slug=slug, enabled=True).first()
            if tool is None:
                raise CommandError(f'공개된 도구가 아니다: {slug}')
            use_shared = options['shared'] and tool.credential == Tool.Credential.SHARED
            entry = ToolboxEntry.objects.filter(user=user, tool=tool).first()
            if entry is None and not is_configured(tool, has_value=False, use_shared=use_shared):
                raise CommandError(
                    f'{slug} 는 설정이 필요하다 — --shared(관리자 공용 키가 있을 때) 또는 허브 화면에서 키를 넣어 담아라'
                )
            if entry is None:
                entry = ToolboxEntry.objects.create(user=user, tool=tool)
            if use_shared:
                entry.use_shared_credential = True
                entry.save(update_fields=['use_shared_credential'])
            self.stderr.write(
                f'도구함: {tool.slug}{" (공용 키)" if entry.use_shared_credential else ""}'
            )
        raw = tokens.issue(user)
        self.stderr.write(
            f'연결 토큰 발급: {user.email} · {tokens.TOKEN_DAYS}일 · 스코프 {tokens.active(user).scope or "(없음)"}'
        )
        self.stdout.write(raw)
