"""v1 카탈로그를 심는다. 멱등 — 있으면 갱신, 없으면 생성. 어댑터가 없는 도구는 비공개(enabled=False)."""

from django.core.management.base import BaseCommand

from apps.catalog.models import Tool

CATALOG = [
    {
        'slug': 'kosis',
        'name': 'KOSIS 국가통계',
        'provider': '국가데이터처 KOSIS',
        'credential': Tool.Credential.SHARED,
        'setting_key': 'KOSIS_API_KEY',
        'order': 10,
        'enabled': True,
        'description': '통계표 검색과 데이터 조회. 인증키가 필요하며 관리자 공용 키를 쓸 수 있다.',
    },
    {
        'slug': 'weather',
        'name': '날씨',
        'provider': 'Open-Meteo',
        'credential': Tool.Credential.NONE,
        'order': 40,
        'enabled': True,
        'description': '좌표 기준 현재 날씨와 오늘 예보. 키 불요.',
    },
    {
        'slug': 'fx',
        'name': '환율',
        'provider': '서울외국환중개',
        'credential': Tool.Credential.NONE,
        'order': 20,
        'enabled': False,
        'description': '일별·월평균 매매기준율 조회. 어댑터 준비 중 — 공개 전까지 도구함에 담을 수 없다.',
    },
    {
        'slug': 'fuel',
        'name': '유가',
        'provider': '오피넷',
        'credential': Tool.Credential.NONE,
        'order': 30,
        'enabled': False,
        'description': '지역별 평균 판매가격 조회. 어댑터 준비 중 — 공개 전까지 도구함에 담을 수 없다.',
    },
]


class Command(BaseCommand):
    help = 'v1 도구 카탈로그를 심는다 (멱등)'

    def handle(self, *args, **options):
        for row in CATALOG:
            defaults = {k: v for k, v in row.items() if k != 'slug'}
            tool, created = Tool.objects.update_or_create(slug=row['slug'], defaults=defaults)
            self.stdout.write(
                f'{"생성" if created else "갱신"}: {tool}{"" if tool.enabled else " (비공개)"}'
            )
