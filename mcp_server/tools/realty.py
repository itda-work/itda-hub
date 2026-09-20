"""국토교통부 아파트 실거래가 — data.go.kr(RTMS) 조회.

스킬.잇다 `itda-realty:realty-deals` 스킬(Apache-2.0)의 엔드포인트·필드 계약을 따르되 허브 규약으로
다시 썼다. 스킬 쪽은 전 페이지를 끌어와 CSV 로 떨구는 배치이고, 여기서는 **한 번의 도구 호출이
한 화면**이다 — 페이지를 돌지 않고 `total_count` 를 함께 내 부르는 쪽이 다음 페이지를 고르게 한다.
모델의 컨텍스트로 통째로 들어가는 결과라, 전량 수집은 허브의 계약이 아니다.

인증키는 쿼리스트링(`serviceKey`)으로 가므로 `safe.check` 가 통째로 버린다 — KOSIS 와 같은 경로다.
상류는 **HTTP 200 인 채로 본문에 오류를 싣는다.** 두 모양이 있다.

- 서비스 응답: `<response><header><resultCode>…` — 데이터 없음(03)·트래픽 초과(22) 등.
- 게이트웨이 응답: `<OpenAPI_ServiceResponse><cmmMsgHeader>…` — 미등록 키(30)·미승인(20) 등.
  이쪽은 `<header>` 가 없어서 서비스 응답만 보는 파서는 「빈 결과」로 오독한다.
"""

import xml.etree.ElementTree as ET

import httpx

from . import safe

BASE_URL = 'https://apis.data.go.kr/1613000'
SOURCE = 'data.go.kr'

# 읽기 전용 아파트 실거래 두 갈래. 오피스텔·연립다세대 등은 같은 표에 줄을 더하면 늘어난다.
ENDPOINTS = {
    'trade': (
        f'{BASE_URL}/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade',
        'https://www.data.go.kr/data/15126469/openapi.do',
    ),
    'rent': (
        f'{BASE_URL}/RTMSDataSvcAptRent/getRTMSDataSvcAptRent',
        'https://www.data.go.kr/data/15126474/openapi.do',
    ),
}

SUCCESS_CODES = {'0', '00', '000', '0000'}

# 데이터 없음(NODATA_ERROR)은 실패가 아니다 — 「그 달에 거래가 없었다」 는 참인 답이다.
# 오류로 내면 부르는 쪽이 키·코드를 의심하며 헛돈다.
EMPTY_CODE = '03'

# 공공데이터포털 공통 오류 코드 → 부르는 쪽이 문장 파싱 없이 고칠 자리를 알게 하는 분류.
ERROR_KIND = {
    '01': 'transient',
    '02': 'transient',
    '04': 'transient',
    '05': 'transient',
    '22': 'transient',
    '10': 'argument',
    '11': 'argument',
    '12': 'credential',
    '20': 'credential',
    '30': 'credential',
    '31': 'credential',
    '32': 'credential',
}

MAX_ROWS = 100


def _text(el, tag: str) -> str:
    return (el.findtext(tag) or '').strip()


def _amount(value: str) -> int | None:
    """거래금액·보증금 문자열(만원, 쉼표 포함) → 정수 만원. 빈 값·`-` 는 None."""
    cleaned = value.replace(',', '').strip()
    if not cleaned or cleaned == '-':
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _error(code: str, message: str, api_key: str, apply_url: str) -> dict:
    payload = {
        'source': SOURCE,
        'ok': False,
        'error_code': code,
        'error_kind': ERROR_KIND.get(code, 'unknown'),
        # 상류가 우리가 보낸 쿼리스트링을 오류 문장에 인용하는 경우가 있다.
        'error': safe.redact(message, api_key),
    }
    if payload['error_kind'] == 'credential':
        payload['apply_url'] = apply_url
    return payload


def _item(el, deal_type: str) -> dict:
    """상류의 camelCase 필드를 허브의 snake_case 로. 매매·전월세가 다른 금액 칸을 쓴다."""
    row = {
        'apt_name': _text(el, 'aptNm'),
        'dong': _text(el, 'umdNm'),
        'jibun': _text(el, 'jibun'),
        'sgg_code': _text(el, 'sggCd'),
        'area_m2': _text(el, 'excluUseAr'),
        'floor': _text(el, 'floor'),
        'build_year': _text(el, 'buildYear'),
        'date': '-'.join(
            p for p in (_text(el, 'dealYear'), _text(el, 'dealMonth'), _text(el, 'dealDay')) if p
        ),
    }
    if deal_type == 'trade':
        row['deal_amount_manwon'] = _amount(_text(el, 'dealAmount'))
        row['canceled'] = bool(_text(el, 'cdealType'))
    else:
        row['deposit_manwon'] = _amount(_text(el, 'deposit'))
        row['monthly_rent_manwon'] = _amount(_text(el, 'monthlyRent'))
        row['contract_term'] = _text(el, 'contractTerm')
        row['contract_type'] = _text(el, 'contractType')
    return row


def deals(
    api_key: str,
    lawd_cd: str,
    deal_ymd: str,
    deal_type: str = 'trade',
    count: int = 20,
    page: int = 1,
) -> dict:
    """시군구 코드·계약연월의 아파트 실거래. `deal_type` 은 `trade`(매매) 또는 `rent`(전월세).

    인자 검증을 상류에 미루지 않는다 — 상류는 형식이 틀려도 빈 결과를 돌려주는 때가 있어,
    「그 달에 거래가 없었다」 와 「코드를 잘못 적었다」 가 구분되지 않는다.
    """
    if deal_type not in ENDPOINTS:
        return {
            'source': SOURCE,
            'ok': False,
            'error_code': 'ARGUMENT',
            'error_kind': 'argument',
            'error': f'deal_type 은 {sorted(ENDPOINTS)} 중 하나다 — 받은 값: {deal_type!r}',
        }
    if not (len(lawd_cd) == 5 and lawd_cd.isdigit()):
        return {
            'source': SOURCE,
            'ok': False,
            'error_code': 'ARGUMENT',
            'error_kind': 'argument',
            'error': f'lawd_cd 는 법정동코드 앞 5 자리(시군구)다 — 받은 값: {lawd_cd!r}',
        }
    if not (len(deal_ymd) == 6 and deal_ymd.isdigit()):
        return {
            'source': SOURCE,
            'ok': False,
            'error_code': 'ARGUMENT',
            'error_kind': 'argument',
            'error': f'deal_ymd 는 계약연월 YYYYMM 이다 — 받은 값: {deal_ymd!r}',
        }

    url, apply_url = ENDPOINTS[deal_type]
    rows_wanted = max(1, min(count, MAX_ROWS))
    params = {
        'serviceKey': api_key,
        'LAWD_CD': lawd_cd,
        'DEAL_YMD': deal_ymd,
        'pageNo': max(1, page),
        'numOfRows': rows_wanted,
    }
    r = httpx.get(url, params=params, timeout=20.0)
    # 인증키가 쿼리스트링에 있다 — 예외 문자열에 URL 을 싣지 않는다(#4).
    safe.check(r, SOURCE)

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as exc:
        # 예외를 그대로 올리지 않는다 — 파서 메시지에 본문 조각이 실리고 그것이 궤적에 남는다.
        return _error('PARSE', f'XML 파싱 실패: {type(exc).__name__}', api_key, apply_url)

    # 게이트웨이 오류는 `<header>` 가 없다. 이 갈래를 먼저 본다.
    gateway = root.find('cmmMsgHeader')
    if gateway is not None:
        return _error(
            _text(gateway, 'returnReasonCode'),
            _text(gateway, 'returnAuthMsg') or _text(gateway, 'errMsg'),
            api_key,
            apply_url,
        )

    header = root.find('header')
    empty = False
    if header is not None:
        code = _text(header, 'resultCode')
        if code == EMPTY_CODE:
            empty = True
        elif code and code not in SUCCESS_CODES:
            return _error(code, _text(header, 'resultMsg'), api_key, apply_url)

    body = None if empty else root.find('body')
    items = body.find('items') if body is not None else None
    rows = [_item(el, deal_type) for el in items.findall('item')] if items is not None else []
    return {
        'source': SOURCE,
        'ok': True,
        'deal_type': deal_type,
        'lawd_cd': lawd_cd,
        'deal_ymd': deal_ymd,
        'page': int(_text(body, 'pageNo') or page) if body is not None else page,
        'total_count': int(_text(body, 'totalCount') or 0) if body is not None else 0,
        'count': len(rows),
        'deals': rows,
    }
