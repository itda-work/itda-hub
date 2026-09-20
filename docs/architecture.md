# 아키텍처

## 한 줄

사람은 허브에 로그인해 **도구함**을 만들고, 클라이언트는 그 사람의 **도구함 스코프**가 실린 토큰(OAuth 동의 또는 연결 토큰)으로 별도 프로세스의 MCP 서버에 붙어 그 스코프만큼의 도구를 본다. 모든 호출은 django-itda 궤적으로 남는다.

## 두 겹의 OAuth, 그리고 연결 토큰

| 겹 | 누가 누구에게 | 구현 |
|---|---|---|
| 사람 → 허브 | 운영: 교육생이 Google 계정으로 로그인. 로컬·자체 호스팅: 이메일+비밀번호(`HUB_LOCAL_LOGIN`) | django-allauth. Google 은 자격이 있을 때만 설치된다 |
| Claude → 허브 (OAuth) | 커스텀 커넥터가 허브 인가 서버에서 사용자 동의를 받는다. 동의 화면의 스코프 = 도구함 | django-oauth-toolkit 3.4 (PKCE S256 · CIMD · DCR · RFC 8414/9728 · RFC 9700/9207) |
| 클라이언트 → 허브 (연결 토큰) | 운영·스모크용. 헤더를 보낼 수 있는 클라이언트가 `issue_token` 커맨드로 발급한 토큰을 `Authorization: Bearer` 로 보낸다 | `apps/toolbox/tokens.py` — DOT `AccessToken` 그대로(별도 모델 없음). 30일 · 사용자당 하나 · 스코프는 도구함을 따라간다 |

fastmcp 의 Google 제공자(프록시)를 쓰지 않는 이유: Claude 가 Google 에 직접 로그인하면 도구함 스코프를 실을 자리가 없다. 신원은 로그인 제공자에서 받고 토큰은 허브가 발급한다.

연결 토큰이 OAuth 토큰과 같은 표에 사는 이유: MCP 서버의 검증 경로(introspection → `username` → actor, 스코프 → 도구 목록)가 하나여야 한다. 발급 경로만 다르다 — 동의 화면 대신 `issue_token` 커맨드(0.4.0 부터 화면 버튼은 없다 — 사용자에게는 OAuth 커넥터만 노출). 토큰 원문은 저장하지 않고 체크섬만 둔다(`COMPLIANT_BCP_RFC9700_TOKEN_STORAGE`) — DB·admin 어디에도 쓸 수 있는 토큰이 없다. claude.ai·Cowork 의 커스텀 커넥터는 헤더를 받지 않으므로(OAuth 또는 무인증) 그쪽은 OAuth 만이 길이다.

## 스코프 = 도구함

- 카탈로그의 도구 하나 = 스코프 하나 `tool:<slug>` (`apps/catalog/models.py`).
- 사용자가 담은 도구 = 그 사용자에게 허용되는 스코프 (`apps/toolbox/models.py: granted_scopes`).
- DOT 스코프 백엔드 `apps/oauth/scopes.py` 가 동의 화면·토큰 발급을 그 목록으로 상한한다.
- MCP 서버는 도구마다 `auth=require_scopes('tool:<slug>')`. 스코프 없는 도구는 `tools/list` 에서 빠지고 호출도 거부된다.

## 프로세스 경계

```
브라우저 ──로그인──▶ Django(web)   /  /o/*  /.well-known/*  /toolbox(도구함·설정)  /trajectory  /admin  /healthz
Claude ────OAuth───▶ Django(web)   동의 화면 · 토큰 · introspection
Claude ────MCP────▶ mcp_server    /mcp  (fastmcp · Streamable HTTP · introspection 으로 토큰 검증)
Claude Code ─Bearer▶ mcp_server    같은 /mcp — 연결 토큰도 같은 introspection 을 지난다
                       │ ORM(같은 SQLite, WAL)
                       └── 도구함·설정 읽기 · 궤적(ToolCall) 쓰기 · 도구 어댑터(HTTPS GET)
```

Django 안에 MCP 를 호스팅하지 않는다(django-itda 결정). compose 에서는 web·mcp 가 볼륨 하나를 공유하고, mcp 는 introspection 을 서비스 이름(`HUB_INTROSPECTION_URL=http://hub-web:8000/o/introspect/`)으로 부른다. 운영은 리버스 프록시가 `/mcp` 는 MCP 프로세스로, 나머지는 Django 로 보낸다.

## 메타데이터 발견

- 인가 서버 메타데이터: `GET /.well-known/oauth-authorization-server` (Django, DOT).
- 보호 리소스 메타데이터: `GET /.well-known/oauth-protected-resource/mcp` (Django, DOT 경로 형식). `resource` = `HUB_MCP_URL`, `authorization_servers` = `[HUB_BASE_URL]`.
- MCP 서버는 401 에 `WWW-Authenticate: Bearer resource_metadata=...` 를 실어 위 문서를 가리킨다.
- Claude 의 클라이언트 신원은 CIMD(공개 신원) 우선, DCR 병행. 콜백 `https://claude.ai/api/mcp/auth_callback`.
  CIMD 문서의 `grant_types` 중 허브가 지원하지 않는 것(예: `jwt-bearer`)은 무시하고 지원 grant 가 정확히 하나일 때만 받는다 — DOT 규칙을 기동 시 감싼다(`apps/oauth/cimd.py`, H-5).

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
| 본문이 올린 `ToolDenied` 의 궤적 분류 | 해결됨 — django-itda 0.4 가 본문의 `ToolDenied` 를 권한 검사 거부와 같은 갈래(`error='forbidden'`/`'denied'`)로 남긴다([django-itda#6](https://github.com/itda-work/django-itda/issues/6)). 허브는 손대지 않는다 |
