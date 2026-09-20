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
"""

import httpx


class UpstreamError(Exception):
    """상류가 오류 응답을 냈다. 문자열에 쿼리스트링을 싣지 않는다.

    상태 코드는 구조화 필드로도 들고 있다 — 호출하는 쪽이 문장을 파싱하지 않게.
    """

    def __init__(self, source: str, status: int, url: httpx.URL):
        self.source = source
        self.status = status
        # 스킴·호스트·경로만. 쿼리·프래그먼트·userinfo 는 버린다.
        self.safe_url = f'{url.scheme}://{url.host}{url.path}'
        super().__init__(f'{source} 상류 오류 {status} — {self.safe_url}')


def check(response: httpx.Response, source: str) -> httpx.Response:
    """`raise_for_status()` 를 대신한다. 4xx·5xx 면 `UpstreamError` 를 올린다.

    httpx 의 원본 예외는 `from None` 으로 끊는다 — 체인에 남겨 두면 traceback 을 찍는
    어딘가에서 URL 이 다시 드러난다.
    """
    if response.is_success:
        return response
    raise UpstreamError(source, response.status_code, response.request.url) from None


REDACTED = '***'


def redact(text: str, secret: str) -> str:
    """상류가 오류 문장에 되돌려준 비밀을 지운다.

    원문과 URL 인코딩 형태를 모두 지운다 — 상류는 우리가 보낸 쿼리스트링을 그대로 인용하기도 한다.
    빈 비밀은 아무것도 지우지 않는다(`''` 를 치환하면 문자열이 통째로 망가진다).
    """
    if not text or not secret:
        return text
    encoded = str(httpx.QueryParams({'k': secret})).split('=', 1)[1]
    for form in (secret, encoded):
        text = text.replace(form, REDACTED)
    return text
