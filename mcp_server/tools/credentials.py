"""자격증명 해석 — 도구함 설정(암호화) → 관리자 공용 키 순. 값은 반환값으로만 흐르고 로그에 남기지 않는다."""

from django_itda.results import ToolDenied

from apps.toolbox.models import ToolboxEntry


def resolve(actor, slug):
    entry = ToolboxEntry.objects.filter(user=actor, tool__slug=slug).select_related('tool').first()
    if entry is None:
        raise ToolDenied.forbidden(f'{slug} 는 도구함에 없다 — 허브에서 담아라')
    setting = getattr(entry, 'setting', None)
    if setting is not None and setting.ciphertext:
        return setting.get_value()
    if entry.use_shared_credential:
        shared = entry.tool.shared_value()
        if shared:
            return shared
        raise ToolDenied.forbidden(f'{slug} 의 관리자 공용 키가 설정돼 있지 않다')
    raise ToolDenied.forbidden(
        f'{slug} 의 자격증명이 없다 — 허브의 도구 설정에서 넣거나 공용 키 사용을 켜라'
    )
