"""도구 선언 — django-itda `Toolset` 위에 허브의 도구를 올린다.

각 도구는 `actor` 를 첫 인자로 받고, 자격증명은 인자로 받지 않는다. 자격증명은 `credentials.resolve`
가 도구함 설정 또는 관리자 공용 키에서 꺼내 어댑터에 넘긴다. 그래서 인자 목록(궤적에 남는다)에
비밀이 실리지 않는다.
"""

import inspect

from django_itda.tools import Toolset

from . import kosis, weather

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


def specs():
    return list(_SPECS)
