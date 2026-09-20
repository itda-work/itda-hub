"""상류 호출의 비밀 누출 방지 — 예외 문자열을 허브가 통제한다.

httpx 의 `raise_for_status()` 가 만드는 `HTTPStatusError` 문자열에는 **요청 URL 이 통째로** 실린다.
django-itda 는 도구 본문이 올린 일반 예외를 `f'{type(failure).__name__}: {failure}'` 로 궤적
(`ToolCall.reason`)에 저장하므로(`django_itda/tools.py`), 쿼리스트링으로 인증키를 받는 상류
(KOSIS 등)는 그 경로로 키가 DB·화면·admin 검색에 평문으로 남았다 — #4.

여기서 하는 것은 하나다: **상류 실패를 허브가 문구를 정한 예외로 바꾼다.** 판정을 어떻게 낼지
(예외로 둘지 구조화 결과로 바꿀지)는 정하지 않는다 — 그것은 #3 의 몫이고, 그때 이 모듈이
그쪽으로 흡수될 수 있다. 지금은 **무엇을 말하지 않을지**만 정한다.

쿼리스트링은 통째로 버린다. 「어느 파라미터가 비밀인가」를 목록으로 관리하면 새 도구가
목록을 갱신하지 않는 순간 다시 샌다 — 기본을 안전한 쪽에 둔다.

**경로에 비밀을 싣는 상류가 있다.** 한국은행 ECOS 는 인증키를 쿼리 파라미터가 아니라 URL
**경로 세그먼트**로 받는다(`/api/StatisticSearch/<인증키>/json/kr/...`). 경로는 버릴 수 없다 —
버리면 어느 엔드포인트가 실패했는지가 사라져 안전한 URL 이 아무 말도 하지 않게 된다. 그래서
`check()` 는 **그 호출에 우리가 실어 보낸 비밀**을 선택 인자로 받아 안전한 URL 에서 지운다.
파라미터 이름 목록이 아니라 값 자체라, 새 도구가 목록을 갱신하지 않아 새는 경로가 없다.
"""

from urllib.parse import quote

import httpx


class UpstreamError(Exception):
    """상류가 오류 응답을 냈다. 문자열에 쿼리스트링도, 넘겨받은 비밀도 싣지 않는다.

    상태 코드는 구조화 필드로도 들고 있다 — 호출하는 쪽이 문장을 파싱하지 않게.
    """

    def __init__(self, source: str, status: int, url: httpx.URL, secret: str = ''):
        self.source = source
        self.status = status
        # 스킴·호스트·경로만. 쿼리·프래그먼트·userinfo 는 버리고, 경로에 실린 비밀은 지운다.
        self.safe_url = redact(f'{url.scheme}://{url.host}{url.path}', secret)
        super().__init__(f'{source} 상류 오류 {status} — {self.safe_url}')


def check(response: httpx.Response, source: str, secret: str = '') -> httpx.Response:
    """`raise_for_status()` 를 대신한다. 4xx·5xx 면 `UpstreamError` 를 올린다.

    `secret` 은 이 호출에 실어 보낸 자격증명이다. 쿼리스트링으로 보냈다면 어차피 통째로 버려지니
    넘길 필요가 없고, **경로로 보냈다면 반드시 넘긴다**(ECOS).

    httpx 의 원본 예외는 `from None` 으로 끊는다 — 체인에 남겨 두면 traceback 을 찍는
    어딘가에서 URL 이 다시 드러난다.
    """
    if response.is_success:
        return response
    raise UpstreamError(source, response.status_code, response.request.url, secret) from None


REDACTED = '***'


def redact(text: str, secret: str) -> str:
    """상류가 오류 문장에 되돌려준 비밀, 또는 URL 에 남은 비밀을 지운다.

    세 형태를 모두 지운다 — 원문, **쿼리스트링** 인코딩(`+` 는 `%2B`, 공백은 `+`), **경로**
    인코딩(`quote(safe='')` — 공백은 `%20`). 상류는 우리가 보낸 쿼리스트링을 그대로 인용하기도
    하고, 경로 기반 API 의 안전한 URL 에는 경로 인코딩 형태가 남는다.

    빈 비밀은 아무것도 지우지 않는다(`''` 를 치환하면 문자열이 통째로 망가진다).
    """
    if not text or not secret:
        return text
    query_encoded = str(httpx.QueryParams({'k': secret})).split('=', 1)[1]
    path_encoded = quote(secret, safe='')
    for form in (secret, query_encoded, path_encoded):
        text = text.replace(form, REDACTED)
    return text
