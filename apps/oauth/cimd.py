"""CIMD 문서 해석 완화 두 가지 — grant 목록과 토큰 엔드포인트 인증 방식.

**grant**: 서버가 지원하지 않는 grant 는 무시하고, 지원 grant 가 정확히 하나면 통과시킨다.

DOT 3.4.1 `oauth2_provider.cimd._resolve_grant_type` 은 `refresh_token` 만 빼고 grant 가 **정확히 하나**이길
요구한다. claude.ai 의 CIMD 문서(2026-09-20 실측)는 `authorization_code` · `refresh_token` ·
`urn:ietf:params:oauth:grant-type:jwt-bearer` 를 선언해 여기서 떨어지고, 사용자는 커스텀 커넥터를 연결할 수 없다.
RFC 7591 §2 는 grant_types 를 클라이언트가 **쓸 수 있는** 것의 목록으로 두므로, 서버가 모르는 항목은 무시하는
것이 맞다(DOT 에 upstream 제안 — docs/reports/H-5.md).

`IGNORED_GRANT_TYPES` 를 넓히는 대신 함수를 감싼다: 무시 목록은 클라이언트가 앞으로 더할 이름을 미리 알아야
하지만, 여기서는 「`GRANT_TYPE_MAP` 에 있는 것만 센다」로 이름을 몰라도 된다. DOT 를 올려 이 내부 구조가 바뀌면
기동 시 자체 검사(`install`)가 경고 로그를 남긴다 — 그때는 upstream 반영 여부를 보고 이 모듈을 걷거나 고친다.

**인증 방식**: DOT 3.4.1 `_build_application_kwargs` 는 단수 `token_endpoint_auth_method` 가 `none` 이 아니면 거부한다
(CIMD 클라이언트는 공개 클라이언트로만 등록한다). ChatGPT 웹 커넥터의 CIMD 문서(2026-10-14 실측)는 단수 값이
`private_key_jwt` 지만 `token_endpoint_auth_methods_supported` 에 `none` 도 싣는다. ChatGPT 는 이 목록과 인가 서버
메타데이터의 `token_endpoint_auth_methods_supported` 의 **교집합**에서 방식을 고른다(OpenAI 문서) — 허브는
`none` 을 광고하므로 실제 토큰 교환은 `none`(PKCE 공개 클라이언트)이다. 그래서 문서가 `none` 도 지원한다고 밝히면
공개 클라이언트로 받는다. `none` 이 목록에 없으면 여전히 거부한다(#7).
"""

import logging

log = logging.getLogger(__name__)

# claude.ai 커스텀 커넥터가 실제로 내는 CIMD 문서의 모양(자체 검사용 — 비밀 없음).
CLAUDE_AI_SAMPLE = {
    'client_id': 'https://claude.ai/oauth/mcp-oauth-client-metadata',
    'client_name': 'Claude',
    'redirect_uris': ['https://claude.ai/api/mcp/auth_callback'],
    'grant_types': [
        'authorization_code',
        'refresh_token',
        'urn:ietf:params:oauth:grant-type:jwt-bearer',
    ],
    'response_types': ['code'],
    'token_endpoint_auth_method': 'none',
}

# ChatGPT 웹 커넥터의 CIMD 문서 모양(2026-10-14 실측, https://chatgpt.com/oauth/client.json — 비밀 없음).
CHATGPT_SAMPLE = {
    'client_id': 'https://chatgpt.com/oauth/client.json',
    'client_uri': 'https://chatgpt.com/',
    'client_name': 'ChatGPT',
    'redirect_uris': ['https://chatgpt.com/connector_platform_oauth_redirect'],
    'grant_types': ['authorization_code', 'refresh_token'],
    'response_types': ['code'],
    'token_endpoint_auth_method': 'private_key_jwt',
    'token_endpoint_auth_methods_supported': ['none', 'private_key_jwt'],
    'token_endpoint_auth_signing_alg': 'RS256',
    'jwks_uri': 'https://chatgpt.com/oauth/jwks.json',
}


def _make_resolver(cimd, original):
    def resolve_grant_type(grant_types):
        supported = [g for g in grant_types if g in cimd.GRANT_TYPE_MAP]
        if len(supported) != 1:
            raise cimd.CIMDError(
                'client metadata must declare exactly one supported grant type '
                f'(supported: {sorted(cimd.GRANT_TYPE_MAP)}); got grant_types={list(grant_types)!r}'
            )
        ignored = [
            g
            for g in grant_types
            if g not in cimd.GRANT_TYPE_MAP and g not in cimd.IGNORED_GRANT_TYPES
        ]
        if ignored:
            log.info(
                'CIMD: 지원하지 않는 grant 를 무시한다 %r (grant_types=%r)',
                ignored,
                list(grant_types),
            )
        return original(supported)

    resolve_grant_type.__wrapped__ = original
    resolve_grant_type.hub_relaxed = True
    return resolve_grant_type


def _make_builder(original):
    def build_application_kwargs(metadata):
        method = metadata.get('token_endpoint_auth_method', 'none')
        supported = metadata.get('token_endpoint_auth_methods_supported')
        if method != 'none' and isinstance(supported, list) and 'none' in supported:
            log.info(
                'CIMD: token_endpoint_auth_method %r 대신 none 으로 등록한다 '
                '(token_endpoint_auth_methods_supported=%r)',
                method,
                supported,
            )
            metadata = {**metadata, 'token_endpoint_auth_method': 'none'}
        return original(metadata)

    build_application_kwargs.__wrapped__ = original
    build_application_kwargs.hub_relaxed = True
    return build_application_kwargs


def install():
    """`oauth2_provider.cimd` 의 grant 해석·인증 방식 검사를 완화판으로 바꾸고, 표본 문서로 적용을 확인한다.

    실패해도 기동은 막지 않는다(OAuth 전체가 아니라 CIMD 한 경로의 문제) — 경고 로그만 남긴다. 반환값은 적용 여부.
    """
    try:
        from oauth2_provider import cimd

        original = cimd._resolve_grant_type
        if not getattr(original, 'hub_relaxed', False):
            if '_resolve_grant_type' not in cimd._build_application_kwargs.__code__.co_names:
                raise RuntimeError(
                    '_build_application_kwargs 가 더는 _resolve_grant_type 을 부르지 않는다'
                )
            for name in ('GRANT_TYPE_MAP', 'IGNORED_GRANT_TYPES', 'CIMDError'):
                if not hasattr(cimd, name):
                    raise RuntimeError(f'oauth2_provider.cimd.{name} 이 없다')
            cimd._resolve_grant_type = _make_resolver(cimd, original)
        builder = cimd._build_application_kwargs
        if not getattr(builder, 'hub_relaxed', False):
            if '_build_application_kwargs' not in cimd._fetch_validate_upsert.__code__.co_names:
                raise RuntimeError(
                    '_fetch_validate_upsert 가 더는 _build_application_kwargs 를 부르지 않는다'
                )
            cimd._build_application_kwargs = _make_builder(builder)
        # 자체 검사가 「완화했다」 INFO 를 기동마다 찍지 않게 이 동안만 끈다(기동 중 — 단일 스레드).
        log.disabled = True
        try:
            for name, sample in (('claude.ai', CLAUDE_AI_SAMPLE), ('ChatGPT', CHATGPT_SAMPLE)):
                grant = cimd._build_application_kwargs(sample)['authorization_grant_type']
                if grant != 'authorization-code':
                    raise RuntimeError(f'{name} 표본이 {grant!r} 로 해석됐다')
        finally:
            log.disabled = False
    except Exception as exc:  # noqa: BLE001 — 내부 구조가 어떻게 바뀌든 기동은 막지 않는다
        log.warning(
            'CIMD 완화 패치를 적용하지 못했다 — claude.ai·ChatGPT 커넥터 연결이 실패할 수 있다: %r',
            exc,
        )
        return False
    return True
