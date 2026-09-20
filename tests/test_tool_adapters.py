"""새 도구 어댑터 셋 — 부동산 실거래가·ECOS 경제지표·환율. 네트워크는 부르지 않는다.

상류 응답은 `upstream` 픽스처(MockTransport)로 고정한다. 여기서 재는 것은 **허브가 상류의 모양을
어떤 판정 채널로 옮기는가**다 — 상류가 실제로 그 모양을 내는지는 라이브 검증의 몫이고,
`docs/reports/H-6.md` 에 그 절차를 적었다.

판정은 채널로 읽는다(`ok`·`error_code`·`error_kind`). 문장 어휘로 성공/실패를 추론하지 않는다.
"""

import httpx
import pytest

from mcp_server.tools import ecos, fx, realty

# --- 상류 응답 픽스처 ------------------------------------------------------

APT_TRADE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <aptNm>은마</aptNm><umdNm>대치동</umdNm><jibun>316</jibun><sggCd>11680</sggCd>
        <excluUseAr>84.43</excluUseAr><floor>5</floor><buildYear>1979</buildYear>
        <dealYear>2026</dealYear><dealMonth>8</dealMonth><dealDay>14</dealDay>
        <dealAmount> 285,000</dealAmount>
      </item>
      <item>
        <aptNm>래미안</aptNm><umdNm>도곡동</umdNm><jibun>1</jibun><sggCd>11680</sggCd>
        <excluUseAr>59.98</excluUseAr><floor>12</floor><buildYear>2006</buildYear>
        <dealYear>2026</dealYear><dealMonth>8</dealMonth><dealDay>3</dealDay>
        <dealAmount>190,500</dealAmount><cdealType>O</cdealType>
      </item>
    </items>
    <numOfRows>20</numOfRows><pageNo>1</pageNo><totalCount>137</totalCount>
  </body>
</response>
"""

APT_RENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <aptNm>은마</aptNm><umdNm>대치동</umdNm><sggCd>11680</sggCd>
        <excluUseAr>76.79</excluUseAr><floor>3</floor><buildYear>1979</buildYear>
        <dealYear>2026</dealYear><dealMonth>8</dealMonth><dealDay>9</dealDay>
        <deposit> 50,000</deposit><monthlyRent>0</monthlyRent>
        <contractTerm>26.09~28.09</contractTerm><contractType>갱신</contractType>
      </item>
    </items>
    <numOfRows>20</numOfRows><pageNo>1</pageNo><totalCount>1</totalCount>
  </body>
</response>
"""

NODATA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>03</resultCode><resultMsg>NODATA_ERROR</resultMsg></header>
</response>
"""

GATEWAY_ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OpenAPI_ServiceResponse>
  <cmmMsgHeader>
    <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
    <returnReasonCode>30</returnReasonCode>
  </cmmMsgHeader>
</OpenAPI_ServiceResponse>
"""


def xml_response(text):
    return lambda request: httpx.Response(200, text=text, headers={'Content-Type': 'text/xml'})


def json_response(payload, *, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request.url)
        return httpx.Response(200, json=payload)

    return handler


# --- 부동산 실거래가 -------------------------------------------------------


def test_매매_실거래를_정규화해서_낸다(upstream):
    upstream(xml_response(APT_TRADE_XML))
    result = realty.deals('key', '11680', '202608')

    assert result['ok'] is True
    assert (result['total_count'], result['count'], result['page']) == (137, 2, 1)
    first = result['deals'][0]
    assert first['apt_name'] == '은마'
    assert first['deal_amount_manwon'] == 285000, '쉼표·앞공백이 든 금액이 정수 만원이 되지 않았다'
    assert first['date'] == '2026-8-14'
    assert first['canceled'] is False
    assert result['deals'][1]['canceled'] is True, '해제 거래 표시를 흘렸다'


def test_전월세는_보증금과_월세를_낸다(upstream):
    upstream(xml_response(APT_RENT_XML))
    result = realty.deals('key', '11680', '202608', 'rent')

    row = result['deals'][0]
    assert (row['deposit_manwon'], row['monthly_rent_manwon']) == (50000, 0)
    assert 'deal_amount_manwon' not in row, '전월세에 매매 칸이 섞였다'


def test_데이터_없음은_실패가_아니라_빈_결과다(upstream):
    """「그 달에 거래가 없었다」 는 참인 답이다. 오류로 내면 부르는 쪽이 키를 의심하며 헛돈다."""
    upstream(xml_response(NODATA_XML))
    result = realty.deals('key', '11680', '190001')

    assert result['ok'] is True
    assert (result['count'], result['total_count'], result['deals']) == (0, 0, [])


def test_게이트웨이_오류는_자격증명_문제로_분류하고_활용신청_주소를_준다(upstream):
    """`<header>` 가 없는 갈래다 — 서비스 응답만 보는 파서는 이것을 「빈 결과」로 오독한다."""
    upstream(xml_response(GATEWAY_ERROR_XML))
    result = realty.deals('key', '11680', '202608')

    assert result['ok'] is False
    assert (result['error_code'], result['error_kind']) == ('30', 'credential')
    assert result['apply_url'].startswith('https://www.data.go.kr/')


@pytest.mark.parametrize(
    'kwargs',
    [
        {'lawd_cd': '1168', 'deal_ymd': '202608'},
        {'lawd_cd': '11680', 'deal_ymd': '2026-08'},
        {'lawd_cd': '11680', 'deal_ymd': '202608', 'deal_type': 'lease'},
    ],
    ids=['시군구코드 5자리 아님', '연월 형식 아님', '거래 유형 없음'],
)
def test_잘못된_인자는_상류에_닿기_전에_막힌다(upstream, kwargs):
    """상류는 형식이 틀려도 빈 결과를 돌려주는 때가 있어 「거래가 없다」 와 구분되지 않는다."""
    닿음 = []
    upstream(lambda request: 닿음.append(request.url) or httpx.Response(200, text=NODATA_XML))

    result = realty.deals('key', **kwargs)

    assert (result['ok'], result['error_code']) == (False, 'ARGUMENT')
    assert 닿음 == [], '인자 검증 전에 상류를 불렀다'


def test_인증키는_쿼리스트링으로_가고_상한이_걸린다(upstream):
    본 = []

    def handler(request):
        본.append(dict(request.url.params))
        return httpx.Response(200, text=APT_TRADE_XML)

    upstream(handler)
    realty.deals('secret-key', '11680', '202608', 'trade', count=9999)

    assert 본[0]['serviceKey'] == 'secret-key'
    assert 본[0]['numOfRows'] == str(realty.MAX_ROWS), '한 호출이 끌어올 행에 상한이 없다'


# --- ECOS 경제지표 ---------------------------------------------------------


def test_통계표_검색은_상류_목록을_허브가_거른다(upstream):
    """상류에 검색 파라미터가 없다 — `scanned` 를 함께 내 「없음」과 「훑은 범위 밖」을 가른다."""
    upstream(
        json_response(
            {
                'StatisticTableList': {
                    'list_total_count': 900,
                    'row': [
                        {'STAT_CODE': '901Y009', 'STAT_NAME': '소비자물가지수', 'CYCLE': 'M'},
                        {'STAT_CODE': '200Y001', 'STAT_NAME': '주요지표(연간지표)', 'CYCLE': 'A'},
                    ],
                }
            }
        )
    )
    result = ecos.tables('key', '물가')

    assert result['ok'] is True
    assert result['count'] == 1
    assert result['tables'][0]['stat_code'] == '901Y009'
    assert (result['scanned'], result['total']) == (2, 900)


def test_시계열은_시점_값_단위를_낸다(upstream):
    seen = []
    upstream(
        json_response(
            {
                'StatisticSearch': {
                    'list_total_count': 2,
                    'row': [
                        {
                            'TIME': '202601',
                            'DATA_VALUE': '115.2',
                            'UNIT_NAME': '2020=100',
                            'STAT_NAME': '소비자물가지수',
                            'ITEM_CODE1': '0',
                            'ITEM_NAME1': '총지수',
                        }
                    ],
                }
            },
            seen=seen,
        )
    )
    result = ecos.series('key', '901Y009', 'M', '202601', '202606')

    assert (result['ok'], result['mode']) == (True, 'series')
    assert result['rows'][0] == {
        'time': '202601',
        'value': '115.2',
        'unit': '2020=100',
        'stat_name': '소비자물가지수',
        'item_code': '0',
        'item_name': '총지수',
    }
    assert '/StatisticSearch/key/json/kr/' in str(seen[0]), '인증키는 경로 세그먼트로 간다'


def test_인증키_오류는_자격증명_문제로_분류된다(upstream):
    """HTTP 200 인 채로 본문에 오류가 온다 — 상태 코드만 보는 판정은 이것을 성공으로 읽는다."""
    upstream(
        json_response({'RESULT': {'CODE': 'INFO-100', 'MESSAGE': '인증키가 유효하지 않습니다'}})
    )
    result = ecos.series('key', '901Y009', 'M', '202601', '202606')

    assert (result['ok'], result['error_code'], result['error_kind']) == (
        False,
        'INFO-100',
        'credential',
    )


def test_데이터_없음_INFO_200_은_빈_결과다(upstream):
    upstream(
        json_response({'RESULT': {'CODE': 'INFO-200', 'MESSAGE': '해당하는 데이터가 없습니다'}})
    )
    result = ecos.series('key', '901Y009', 'M', '999901', '999912')

    assert (result['ok'], result['count'], result['rows']) == (True, 0, [])


@pytest.mark.parametrize(
    'args',
    [('901Y009', 'X', '202601', '202606'), ('901Y009', 'M', '', '202606')],
    ids=['주기 코드 아님', '기간 없음'],
)
def test_주기와_기간은_상류에_닿기_전에_검증한다(upstream, args):
    닿음 = []
    upstream(lambda request: 닿음.append(request.url) or httpx.Response(200, json={}))

    result = ecos.series('key', *args)

    assert (result['ok'], result['error_kind']) == (False, 'argument')
    assert 닿음 == []


# --- 환율 ------------------------------------------------------------------


ITEM_LIST = {
    'StatisticItemList': {
        'list_total_count': 2,
        'row': [
            {'ITEM_CODE': '0000001', 'ITEM_NAME': '원/미국달러(매매기준율)', 'CYCLE': 'D'},
            {'ITEM_CODE': '0000002', 'ITEM_NAME': '원/일본엔(100엔)', 'CYCLE': 'D'},
        ],
    }
}

RATE_ROWS = {
    'StatisticSearch': {
        'list_total_count': 1,
        'row': [
            {
                'TIME': '20260901',
                'DATA_VALUE': '1385.4',
                'UNIT_NAME': '원',
                'STAT_NAME': '주요국 통화의 대원화환율',
                'ITEM_CODE1': '0000001',
                'ITEM_NAME1': '원/미국달러(매매기준율)',
            }
        ],
    }
}


def test_통화_이름을_주면_항목코드를_상류에_물어_조회한다(upstream):
    """항목코드를 저장소에 박지 않는다 — 상류가 항목을 개편하면 조용히 다른 통화가 나온다."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        payload = ITEM_LIST if 'StatisticItemList' in str(request.url) else RATE_ROWS
        return httpx.Response(200, json=payload)

    upstream(handler)
    result = fx.rates('key', '20260901', '20260905', '미국달러')

    assert (result['ok'], result['mode'], result['currency']) == (True, 'fx', '미국달러')
    assert result['rows'][0]['value'] == '1385.4'
    assert seen[-1].endswith('/0000001'), '찾은 항목코드가 조회 경로에 실리지 않았다'


def test_없는_통화는_고를_수_있는_것을_함께_돌려준다(upstream):
    """이름만 틀린 호출이 빈 결과로 끝나면 부르는 쪽이 다음 수를 모른다."""
    upstream(json_response(ITEM_LIST))
    result = fx.rates('key', '20260901', '20260905', '몽골투그릭')

    assert (result['ok'], result['error_kind']) == (False, 'argument')
    assert '원/일본엔(100엔)' in result['available']


def test_통화를_비우면_항목_조회_없이_전체를_부른다(upstream):
    seen = []
    upstream(json_response(RATE_ROWS, seen=seen))
    result = fx.rates('key', '20260901', '20260905')

    assert result['ok'] is True
    assert len(seen) == 1 and 'StatisticSearch' in str(seen[0])
