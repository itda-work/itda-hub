"""환율 — 한국은행 ECOS 의 일별 대원화환율 통계표 위에 세운 얇은 프리셋.

카탈로그의 `fx` 는 0.4 까지 「어댑터 준비 중」이었고 출처가 서울외국환중개로 적혀 있었다. 그쪽은
공개 API 가 아니라 화면 스크래핑이라 허브의 읽기 전용 계약에 맞지 않는다. 같은 값(매매기준율)을
**공식 API 로 내는 곳이 한국은행 ECOS** 라, `ecos` 어댑터를 그대로 쓴다.

그래서 `fx` 는 `ecos` 와 같은 인증키(`ECOS_API_KEY`)를 쓴다. 도구 행은 따로 둔다 — 스코프가
도구함이고(`tool:fx` 와 `tool:ecos` 는 따로 담긴다), 환율만 필요한 사용자에게 통계표 검색까지
열어 줄 이유가 없다. 대신 사용자는 개인 키를 두 도구에 각각 넣어야 한다(관리자 공용 키를 쓰면
한 번이다). 그 판단의 근거는 `docs/reports/H-6.md`.

**항목코드를 저장소에 박지 않는다.** 통화 이름 → 항목코드는 상류(`StatisticItemList`)에 묻는다.
코드표를 박아 두면 상류가 항목을 개편했을 때 조용히 다른 통화를 돌려준다.
"""

from . import ecos

# 「주요국 통화의 대원화환율」(일별). 스킬.잇다 ecos 스킬의 라이브 검증(2026-06-09)에서 온 코드다.
STAT_CODE = '731Y003'
PERIOD = 'D'


def rates(api_key: str, start: str, end: str, currency: str = '', count: int = 100) -> dict:
    """`start`~`end`(YYYYMMDD) 의 일별 환율. `currency` 는 항목 이름의 일부(예: 미국달러, 일본엔).

    통화를 지정하면 상류의 항목 목록에서 코드를 찾아 그 항목만 조회한다. 못 찾으면 **무엇을 고를 수
    있는지 함께** 돌려준다 — 이름만 틀린 호출이 빈 결과로 끝나면 부르는 쪽이 다음 수를 모른다.
    """
    item_code = ''
    if currency:
        found = ecos.items(api_key, STAT_CODE)
        if not found['ok']:
            return found
        matched = [i for i in found['items'] if currency in (i.get('item_name') or '')]
        if not matched:
            return {
                'source': ecos.SOURCE,
                'ok': False,
                'error_code': 'ARGUMENT',
                'error_kind': 'argument',
                'error': f'{currency!r} 에 맞는 통화 항목이 없다',
                'available': [i.get('item_name') for i in found['items']],
            }
        item_code = matched[0]['item_code']

    result = ecos.series(api_key, STAT_CODE, PERIOD, start, end, item_code, count)
    if result['ok']:
        result['mode'] = 'fx'
        result['currency'] = currency
    return result
