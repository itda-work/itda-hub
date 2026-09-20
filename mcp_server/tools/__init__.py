"""도구 선언 — django-itda `Toolset` 위에 허브의 도구를 올린다.

각 도구는 `actor` 를 첫 인자로 받고, 자격증명은 인자로 받지 않는다. 자격증명은 `credentials.resolve`
가 도구함 설정 또는 관리자 공용 키에서 꺼내 어댑터에 넘긴다. 그래서 인자 목록(궤적에 남는다)에
비밀이 실리지 않는다.
"""

import inspect

from django_itda.tools import Toolset

from . import ecos, fx, kosis, realty, weather

toolset = Toolset(name='itda-hub')


class HubSpec:
    """fastmcp 등록에 필요한 것만 든 얇은 명세. django-itda 의 ToolSpec 에 스코프와 시그니처를 얹는다."""

    def __init__(self, name, fn, scope):
        self.name = name
        self.scope = scope
        self.description = (fn.__doc__ or '').strip()
        sig = inspect.signature(fn)
        self.signature = sig.replace(
            parameters=[p for p in sig.parameters.values() if p.name != 'actor']
        )
        self.annotations = {
            k: v for k, v in getattr(fn, '__annotations__', {}).items() if k != 'actor'
        }


_SPECS: list[HubSpec] = []


def hub_tool(slug, *, query=True):
    """카탈로그 slug 하나에 도구 하나. 스코프는 `tool:<slug>` 다."""

    def register(fn):
        toolset.tool(fn, name=fn.__name__, query=query)
        _SPECS.append(HubSpec(fn.__name__, fn, f'tool:{slug}'))
        return fn

    return register


@hub_tool('weather')
def weather_now(actor, latitude: float, longitude: float) -> dict:
    """좌표의 현재 날씨(기온·바람·날씨 코드)와 오늘 예보. 출처 Open-Meteo, 키 불요."""
    return weather.now(latitude, longitude)


@hub_tool('kosis')
def kosis_search(actor, keyword: str, count: int = 10) -> dict:
    """KOSIS 통계표 검색. 기관·표 ID·표 이름을 돌려준다. 인증키는 도구함 설정 또는 관리자 공용 키."""
    from .credentials import resolve

    return kosis.search(resolve(actor, 'kosis'), keyword, count)


@hub_tool('realty-deals')
def realty_deals(
    actor,
    lawd_cd: str,
    deal_ymd: str,
    deal_type: str = 'trade',
    count: int = 20,
    page: int = 1,
) -> dict:
    """국토교통부 아파트 실거래가. `lawd_cd` 는 법정동코드 앞 5 자리(시군구, 예: 서울 강남구 11680),
    `deal_ymd` 는 계약연월 YYYYMM, `deal_type` 은 `trade`(매매)·`rent`(전월세). 한 페이지만 돌려주고
    `total_count` 를 함께 낸다 — 더 필요하면 `page` 를 올린다. 인증키는 도구함 설정 또는 공용 키."""
    from .credentials import resolve

    return realty.deals(resolve(actor, 'realty-deals'), lawd_cd, deal_ymd, deal_type, count, page)


@hub_tool('ecos')
def ecos_stats(
    actor,
    stat_code: str = '',
    keyword: str = '',
    period: str = 'M',
    start: str = '',
    end: str = '',
    item_code: str = '',
    count: int = 50,
) -> dict:
    """한국은행 ECOS 경제지표. `stat_code` 를 주면 그 통계표의 시계열을(`period` 는 A·S·Q·M·SM·D,
    `start`·`end` 는 주기에 맞는 형식 — A:2024, Q:2024Q1, M:202401, D:20240101), 안 주면 `keyword`
    로 통계표를 검색한다. 항목코드를 모르면 통계표 검색부터 한다. 인증키는 도구함 설정 또는 공용 키."""
    from .credentials import resolve

    api_key = resolve(actor, 'ecos')
    if stat_code:
        return ecos.series(api_key, stat_code, period, start, end, item_code, count)
    return ecos.tables(api_key, keyword, count)


@hub_tool('fx')
def fx_rate(actor, start: str, end: str, currency: str = '', count: int = 100) -> dict:
    """일별 환율(한국은행 ECOS 대원화환율). `start`·`end` 는 YYYYMMDD, `currency` 는 통화 이름의
    일부(예: 미국달러, 일본엔). 비우면 그 기간의 모든 통화가 온다. 인증키는 ECOS 키와 같다."""
    from .credentials import resolve

    return fx.rates(resolve(actor, 'fx'), start, end, currency, count)


def specs():
    return list(_SPECS)
