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
        'slug': 'realty-deals',
        'name': '부동산 실거래가',
        'provider': '국토교통부 실거래가(data.go.kr)',
        'credential': Tool.Credential.SHARED,
        'setting_key': 'DATA_GO_KR_API_KEY',
        'order': 12,
        'enabled': True,
        'description': (
            '시군구·계약연월로 아파트 매매·전월세 실거래를 조회한다. '
            '공공데이터포털 인증키가 필요하며 관리자 공용 키를 쓸 수 있다.'
        ),
    },
    {
        'slug': 'ecos',
        'name': '한국은행 경제지표',
        'provider': '한국은행 ECOS',
        'credential': Tool.Credential.SHARED,
        'setting_key': 'ECOS_API_KEY',
        'order': 14,
        'enabled': True,
        'description': '통계표 검색과 시계열 조회. 인증키가 필요하며 관리자 공용 키를 쓸 수 있다.',
    },
    {
        'slug': 'fx',
        'name': '환율',
        # 어댑터는 ECOS 의 일별 대원화환율 통계표를 쓴다 — 같은 인증키(`ECOS_API_KEY`)다.
        'provider': '한국은행 ECOS',
        'credential': Tool.Credential.SHARED,
        'setting_key': 'ECOS_API_KEY',
        'order': 20,
        'enabled': True,
        'description': '일별 대원화환율 조회. 한국은행 ECOS 인증키를 쓴다(경제지표 도구와 같은 키).',
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
