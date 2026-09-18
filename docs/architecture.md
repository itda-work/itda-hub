# 아키텍처

## 한 줄

사람은 Google 로 허브에 들어와 **도구함**을 만들고, Claude 는 허브의 OAuth 로 그 사람의 **도구함 스코프**를 받은 토큰을 얻어, 별도 프로세스의 MCP 서버에서 그 스코프만큼의 도구를 본다. 모든 호출은 django-itda 궤적으로 남는다.

## 두 겹의 OAuth

| 겹 | 누가 누구에게 | 구현 |
|---|---|---|
| 사람 → 허브 | 교육생이 Google 계정으로 로그인 | django-allauth Google. 이후 제공자 추가 |
| Claude → 허브 | 커스텀 커넥터가 허브 인가 서버에서 사용자 동의를 받는다. 동의 화면의 스코프 = 도구함 | django-oauth-toolkit 3.4 (PKCE S256 · CIMD · DCR · RFC 8414/9728) |

fastmcp 의 Google 제공자(프록시)를 쓰지 않는 이유: Claude 가 Google 에 직접 로그인하면 도구함 스코프를 실을 자리가 없다. 신원은 Google 에서 받고 토큰은 허브가 발급한다.

## 스코프 = 도구함

- 카탈로그의 도구 하나 = 스코프 하나 `tool:<slug>` (`apps/catalog/models.py`).
- 사용자가 담은 도구 = 그 사용자에게 허용되는 스코프 (`apps/toolbox/models.py: granted_scopes`).
- DOT 스코프 백엔드 `apps/oauth/scopes.py` 가 동의 화면·토큰 발급을 그 목록으로 상한한다.
- MCP 서버는 도구마다 `auth=require_scopes('tool:<slug>')`. 스코프 없는 도구는 `tools/list` 에서 빠지고 호출도 거부된다.

## 프로세스 경계

```
브라우저 ──Google──▶ Django(web)   /  /o/*  /.well-known/*  /toolbox  /trajectory  /admin
Claude ───OAuth────▶ Django(web)   동의 화면 · 토큰 · introspection
Claude ───MCP─────▶ mcp_server    /mcp  (fastmcp · Streamable HTTP · introspection 으로 토큰 검증)
                       │ ORM(같은 DB)
                       └── 도구함·설정 읽기 · 궤적(ToolCall) 쓰기 · 도구 어댑터(HTTPS GET)
```

Django 안에 MCP 를 호스팅하지 않는다(django-itda 결정). 리버스 프록시가 `/mcp` 는 MCP 프로세스로, 나머지는 Django 로 보낸다.

## 메타데이터 발견

- 인가 서버 메타데이터: `GET /.well-known/oauth-authorization-server` (Django, DOT).
- 보호 리소스 메타데이터: `GET /.well-known/oauth-protected-resource/mcp` (Django, DOT 경로 형식). `resource` = `HUB_MCP_URL`, `authorization_servers` = `[HUB_BASE_URL]`.
- MCP 서버는 401 에 `WWW-Authenticate: Bearer resource_metadata=...` 를 실어 위 문서를 가리킨다.
- Claude 의 클라이언트 신원은 CIMD(공개 신원) 우선, DCR 병행. 콜백 `https://claude.ai/api/mcp/auth_callback`.

## 자격증명

도구 설정 값은 Fernet 으로 암호화해 저장한다(`apps/toolbox/crypto.py`). 값은 도구를 부르는 순간 `mcp_server/tools/credentials.py` 가 풀어 어댑터에 넘기고, 도구 인자에는 실리지 않으므로 궤적에도 남지 않는다. 관리자 공용 키는 환경변수 `SHARED_<KEY>` 로만 존재한다.

## django-itda 에 돌려보낼 조각

허브에서 범용으로 드러난 것은 허브에 두지 않는다.

| 조각 | 지금 허브의 임시 구현 |
|---|---|
| 요청 단위 자리(토큰 → 사용자) | `mcp_server/server.py: _actor` |
| 목록 시점 가시성(스코프) | `require_scopes` 를 도구마다 수동 부착 |
| 스코프 ↔ 권한 매핑 | 카탈로그 slug 규약 |
| 설정 저장소 | `apps/toolbox` |
| HTTP 브리지 예제 | `mcp_server/__main__.py` |
