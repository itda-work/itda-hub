"""KOSIS 통계표 검색. 스킬.잇다 kosis 스킬(Apache-2.0)의 엔드포인트 계약을 따른다. 키는 인자로 받되 로그에 남기지 않는다."""

import httpx

SEARCH_URL = 'https://kosis.kr/openapi/statisticsSearch.do'


def search(api_key: str, keyword: str, count: int = 10) -> dict:
    params = {
        'method': 'getList',
        'apiKey': api_key,
        'format': 'json',
        'jsonVD': 'Y',
        'searchNm': keyword,
    }
    r = httpx.get(SEARCH_URL, params=params, timeout=15.0)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and 'err' in data:
        # 판정은 채널로 — KOSIS 의 오류 코드를 그대로 싣는다. 키 오류(10/11/42)는 허브 설정을 가리킨다.
        return {
            'source': 'kosis.kr',
            'ok': False,
            'error_code': str(data.get('err')),
            'error': data.get('errMsg', ''),
        }
    rows = data if isinstance(data, list) else []
    return {
        'source': 'kosis.kr',
        'ok': True,
        'count': len(rows[:count]),
        'tables': [
            {
                'org_id': r.get('ORG_ID'),
                'org_name': r.get('ORG_NM'),
                'tbl_id': r.get('TBL_ID'),
                'tbl_name': r.get('TBL_NM'),
            }
            for r in rows[:count]
        ],
    }
