"""도구 카탈로그 — 허브가 내놓는 도구의 목록과, 도구마다 하나씩 붙는 OAuth 스코프.

스코프 이름이 곧 도구의 이름이다. 사용자가 도구함에 담은 도구가 동의 화면의 스코프가 되고,
토큰에 실린 스코프대로 MCP 서버가 도구 목록을 거른다. 이 대응이 허브의 뼈대라 여기서
한 번만 정의한다.
"""

from django.db import models


class Tool(models.Model):
    class Credential(models.TextChoices):
        NONE = 'none', '불요'
        USER = 'user', '사용자 키'
        SHARED = 'shared', '사용자 키 또는 관리자 공용 키'

    slug = models.SlugField('식별자', unique=True, help_text='스코프 이름이자 MCP 도구 이름의 접두')
    name = models.CharField('이름', max_length=80)
    description = models.TextField('설명')
    provider = models.CharField('데이터 출처', max_length=120, help_text='예: 국가데이터처 KOSIS')
    credential = models.CharField(
        '자격증명', max_length=10, choices=Credential.choices, default=Credential.NONE
    )
    setting_key = models.CharField(
        '설정 키',
        max_length=60,
        blank=True,
        default='',
        help_text='사용자가 넣는 값의 이름. 예: KOSIS_API_KEY',
    )
    enabled = models.BooleanField('공개', default=True)
    order = models.PositiveSmallIntegerField('정렬', default=100)

    class Meta:
        ordering = ['order', 'slug']
        verbose_name = '도구'
        verbose_name_plural = '도구'

    def __str__(self):
        return f'{self.name} ({self.slug})'

    @property
    def scope(self):
        return f'tool:{self.slug}'


def scope_choices():
    """django-oauth-toolkit 의 SCOPES 로 넘길 {스코프: 설명}. 카탈로그가 바뀌면 함께 바뀐다."""
    return {t.scope: f'{t.name} — {t.description}' for t in Tool.objects.filter(enabled=True)}
