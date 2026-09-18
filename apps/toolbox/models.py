"""도구함 — 사용자가 담은 도구와 도구별 설정.

`ToolboxEntry` 가 있는 도구만 그 사용자의 동의 화면에 스코프로 나타나고, 그래서 토큰에 실리고,
그래서 MCP 도구 목록에 나타난다. `ToolSetting` 은 값을 암호화해 둔다.
"""

from django.conf import settings
from django.db import models

from apps.catalog.models import Tool

from . import crypto


class ToolboxEntry(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='toolbox'
    )
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name='entries')
    use_shared_credential = models.BooleanField('관리자 공용 키 사용', default=False)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'tool')]
        verbose_name = '도구함 항목'
        verbose_name_plural = '도구함 항목'

    def __str__(self):
        return f'{self.user} · {self.tool.slug}'


class ToolSetting(models.Model):
    entry = models.OneToOneField(ToolboxEntry, on_delete=models.CASCADE, related_name='setting')
    key = models.CharField('설정 키', max_length=60)
    ciphertext = models.TextField('암호문')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '도구 설정'
        verbose_name_plural = '도구 설정'

    def __str__(self):
        return f'{self.entry} · {self.key}'

    def set_value(self, value: str):
        self.ciphertext = crypto.encrypt(value)

    def get_value(self) -> str:
        return crypto.decrypt(self.ciphertext)


def granted_scopes(user) -> list[str]:
    """이 사용자의 도구함이 허용하는 스코프. 동의 화면과 토큰 발급이 이 목록을 상한으로 쓴다."""
    # 카탈로그 순서로 고정한다 — 담은 순서에 따라 스코프 문자열이 흔들리지 않는다(토큰 스코프·화면 표시가 같은 열).
    entries = ToolboxEntry.objects.filter(user=user, tool__enabled=True).select_related('tool')
    return [e.tool.scope for e in entries.order_by('tool__order', 'tool__slug')]
