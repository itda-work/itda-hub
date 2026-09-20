"""한국은행 ECOS OpenAPI — 통계표 검색과 시계열 조회.

스킬.잇다 `itda-gov-collect:ecos` 스킬(Apache-2.0)의 엔드포인트 계약을 따르되, 허브 규약으로 다시
썼다 — 판정은 채널로 내고, 인증키는 도구 인자가 아니라 `credentials.resolve` 가 넘긴다.

**ECOS 는 인증키를 URL 경로에 싣는다**(`/api/<서비스>/<인증키>/json/kr/<시작>/<끝>/...`). 그래서
상류 실패 경로에서 `safe.check(r, SOURCE, api_key)` 로 **키를 명시해 넘긴다** — 쿼리스트링처럼
통째로 버릴 수 없는 자리라 `safe.py` 가 값으로 지운다.

HTTP 200 인 채로 본문에 오류를 싣는 API 다(`{"RESULT": {"CODE": ..., "MESSAGE": ...}}`). 그래서
판정은 상태 코드가 아니라 본문에서 나온다.
"""

from urllib.parse import quote

import httpx

from . import safe

BASE_URL = 'https://ecos.bok.or.kr/api'
SOURCE = 'ecos.bok.or.kr'

# 주기 코드 → 검색 일자 형식. 상류가 ERROR-101 로 되돌려 주기 전에 허브가 먼저 막는다.
PERIODS = {
    'A': 'YYYY',
    'S': 'YYYYS1',
    'Q': 'YYYYQ1',
    'M': 'YYYYMM',
    'SM': 'YYYYMMS1',
    'D': 'YYYYMMDD',
}

# 키·설정 문제인지 데이터·일시 장애인지를 부르는 쪽이 문장 파싱 없이 알게 한다.
ERROR_KIND = {
    'INFO-100': 'credential',
    'ERROR-100': 'argument',
    'ERROR-101': 'argument',
    'ERROR-200': 'argument',
    'ERROR-300': 'argument',
    'ERROR-301': 'argument',
    'ERROR-400': 'transient',
    'ERROR-500': 'transient',
    'ERROR-600': 'transient',
    'ERROR-601': 'transient',
    'ERROR-602': 'transient',
}

# 한 번의 도구 호출이 끌어올 수 있는 상류 행의 상한. 상류는 10000 까지 받지만, 결과가 모델의
# 컨텍스트로 통째로 들어가므로 허브가 먼저 자른다.
MAX_ROWS = 500

# 통계표 검색은 상류에 키워드 파라미터가 없다 — 목록을 받아 허브가 거른다. 그 훑는 범위.
TABLE_SCAN = 1000


def _url(*segments) -> str:
    """경로 기반 URL. 한글 검색어·인증키를 포함해 모든 세그먼트를 percent-encoding 한다."""
    return BASE_URL + '/' + '/'.join(quote(str(s), safe='') for s in segments)


def _call(api_key: str, *segments) -> dict:
    """ECOS 한 번 호출. 상류 오류는 구조화 결과로, HTTP 실패는 `UpstreamError` 로 낸다.

    성공이면 `{'ok': True, 'rows': [...], 'total': N}`, 상류가 오류를 내면
    `{'ok': False, 'error_code': ..., 'error_kind': ..., 'error': ...}` 다.
    """
    r = httpx.get(_url(*segments), timeout=20.0)
    # 인증키가 **경로**에 있다 — 안전한 URL 에서도 지워야 한다(safe.py).
    safe.check(r, SOURCE, api_key)
    data = r.json()
    result = data.get('RESULT') if isinstance(data, dict) else None
    if result:
        code = str(result.get('CODE', ''))
        if code == 'INFO-200':  # 데이터 없음 — 오류가 아니라 빈 결과다
            return {'ok': True, 'rows': [], 'total': 0}
        return {
            'ok': False,
            'error_code': code,
            'error_kind': ERROR_KIND.get(code, 'unknown'),
            # 상류가 우리가 보낸 경로를 오류 문장에 인용하는 경우가 있다 — 반사된 비밀을 지운다.
            'error': safe.redact(str(result.get('MESSAGE', '')), api_key),
        }
    body = data.get(segments[0], {}) if isinstance(data, dict) else {}
    return {
        'ok': True,
        'rows': body.get('row', []) or [],
        'total': int(body.get('list_total_count') or 0),
    }


def _failed(payload: dict) -> dict:
    return {'source': SOURCE, **payload}


def tables(api_key: str, keyword: str = '', count: int = 20) -> dict:
    """통계표 검색. 상류에 검색 파라미터가 없어 목록 앞쪽 `TABLE_SCAN` 건을 받아 허브가 거른다.

    `scanned` 와 `total` 을 함께 낸다 — 못 찾았을 때 「없다」 인지 「훑은 범위 밖」 인지를 부르는
    쪽이 구분할 수 있어야 한다.
    """
    got = _call(api_key, 'StatisticTableList', api_key, 'json', 'kr', 1, TABLE_SCAN)
    if not got['ok']:
        return _failed(got)
    rows = got['rows']
    if keyword:
        rows = [r for r in rows if keyword in (r.get('STAT_NAME') or '')]
    return {
        'source': SOURCE,
        'ok': True,
        'mode': 'tables',
        'keyword': keyword,
        'scanned': len(got['rows']),
        'total': got['total'],
        'count': len(rows[:count]),
        'tables': [
            {
                'stat_code': r.get('STAT_CODE'),
                'stat_name': r.get('STAT_NAME'),
                'cycle': r.get('CYCLE'),
                'searchable': r.get('SRCH_YN'),
                'org_name': r.get('ORG_NAME'),
            }
            for r in rows[:count]
        ],
    }


def items(api_key: str, stat_code: str, count: int = 500) -> dict:
    """통계표의 세부항목 목록(StatisticItemList). 항목코드를 하드코딩하지 않기 위한 입구다.

    `fx` 어댑터가 통화 이름 → 항목코드를 **상류에 물어** 푼다. 코드표를 저장소에 박아 두면 상류가
    항목을 개편하는 순간 조용히 틀린 값을 낸다.
    """
    got = _call(api_key, 'StatisticItemList', api_key, 'json', 'kr', 1, count, stat_code)
    if not got['ok']:
        return _failed(got)
    return {
        'source': SOURCE,
        'ok': True,
        'mode': 'items',
        'stat_code': stat_code,
        'total': got['total'],
        'count': len(got['rows']),
        'items': [
            {
                'item_code': r.get('ITEM_CODE'),
                'item_name': r.get('ITEM_NAME'),
                'cycle': r.get('CYCLE'),
                'unit': r.get('UNIT_NAME'),
                'start_time': r.get('START_TIME'),
                'end_time': r.get('END_TIME'),
            }
            for r in got['rows']
        ],
    }


def series(
    api_key: str,
    stat_code: str,
    period: str,
    start: str,
    end: str,
    item_code: str = '',
    count: int = 100,
) -> dict:
    """시계열 조회(StatisticSearch). `item_code` 를 비우면 그 통계표의 모든 항목이 온다."""
    if period not in PERIODS:
        return {
            'source': SOURCE,
            'ok': False,
            'error_code': 'ARGUMENT',
            'error_kind': 'argument',
            'error': f'주기는 {sorted(PERIODS)} 중 하나다 — 받은 값: {period!r}',
        }
    if not (start and end):
        return {
            'source': SOURCE,
            'ok': False,
            'error_code': 'ARGUMENT',
            'error_kind': 'argument',
            'error': f'{period} 주기의 start·end 가 필요하다 — 형식 {PERIODS[period]}',
        }
    rows_wanted = max(1, min(count, MAX_ROWS))
    segments = [
        'StatisticSearch',
        api_key,
        'json',
        'kr',
        1,
        rows_wanted,
        stat_code,
        period,
        start,
        end,
    ]
    if item_code:
        segments.append(item_code)
    got = _call(api_key, *segments)
    if not got['ok']:
        return _failed(got)
    return {
        'source': SOURCE,
        'ok': True,
        'mode': 'series',
        'stat_code': stat_code,
        'period': period,
        'total': got['total'],
        'count': len(got['rows']),
        'rows': [
            {
                'time': r.get('TIME'),
                'value': r.get('DATA_VALUE'),
                'unit': r.get('UNIT_NAME'),
                'stat_name': r.get('STAT_NAME'),
                'item_code': r.get('ITEM_CODE1'),
                'item_name': r.get('ITEM_NAME1'),
            }
            for r in got['rows']
        ],
    }
