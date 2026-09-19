# 배포

## 로컬 (docker compose)

```bash
just env    # .env 생성 — 비밀 4종(SECRET_KEY · Fernet 키 · introspection 시크릿 · 관리자 비밀번호)을 채운다
just up     # docker compose up -d --build  →  web 127.0.0.1:8000 · mcp 127.0.0.1:8080
just logs   # 부팅 로그: migrate → seed_catalog → bootstrap → gunicorn / MCP 서버
just down
```

- `deploy/entrypoint.sh` 가 web 컨테이너에서만 `migrate` → `seed_catalog` → `bootstrap` 을 돌린다. mcp 컨테이너는 web 이 `/healthz` 로 healthy 가 된 뒤 뜬다.
- `bootstrap` 이 환경변수로 보장하는 것: introspection 리소스 서버 Application(`HUB_INTROSPECTION_CLIENT_ID/SECRET`), 연결 토큰용 Application(`hub-personal`), 관리자 계정(`HUB_ADMIN_EMAIL/PASSWORD` — 이미 있으면 비밀번호 불변). 멱등이고 비밀은 출력하지 않는다.
- 두 컨테이너는 볼륨 `hub-data` 의 SQLite 파일 하나를 공유한다(WAL). mcp 의 토큰 검증은 공개 주소가 아니라 서비스 이름으로 간다(`HUB_INTROSPECTION_URL=http://web:8000/o/introspect/`, `DJANGO_ALLOWED_HOSTS` 에 `web` 추가 — compose 가 넣는다).
- web 워커 수는 `WEB_CONCURRENCY`(기본 2)다. gunicorn 이 직접 읽는다. 유휴 실측은 워커 2개 125 MiB · 1개 약 90 MiB · mcp 92 MiB 이므로, RAM 1 GiB 호스트에 다른 서비스와 같이 올리면 1 로 둔다.
- 포트가 겹치면 `.env` 의 `HUB_WEB_PORT`/`HUB_MCP_PORT` 를 바꾸고 `HUB_BASE_URL`/`HUB_MCP_URL` 도 같이 맞춘다. 두 주소는 화면과 발급 안내에 그대로 찍힌다.
- 로그인은 이메일+비밀번호(`HUB_LOCAL_LOGIN=1`). Google 을 붙이려면 `GOOGLE_OAUTH_CLIENT_ID/SECRET` 을 채운다(리디렉션 URI `${HUB_BASE_URL}/accounts/google/login/callback/`).
- 연결 확인: `just token <이메일> --tools weather,kosis --shared` 로 토큰을 찍고 `HUB_TOKEN=<토큰> just smoke`. 토큰 없이 거부 · 도구함 스코프만큼의 목록 · 날씨 호출 · KOSIS(키 있으면 ok, 없으면 거부) 네 축을 한 번에 잰다.

## 운영 (공개 HTTPS)

### 전제

- 공개 HTTPS 도메인 하나(`HUB_BASE_URL`). Claude 는 Anthropic 아웃바운드 대역 `160.79.104.0/21` 에서 허브와 인가 서버 양쪽에 닿아야 한다. WAF 가 이 대역을 막으면 연결이 실패한다.
- 프로세스 둘: Django(web) 와 MCP(`python -m mcp_server`). 같은 DB 를 본다. v1 은 SQLite(WAL) 로 충분하다.
  - WAL 은 설정의 `init_command` 가 연결마다 건다(`journal_mode=WAL`, `synchronous=NORMAL`), 잠금 대기는 `timeout=20`(초), 쓰기 트랜잭션은 `IMMEDIATE`.
  - 전제: DB 파일과 `-wal`·`-shm` 파일이 **같은 로컬 볼륨**에 있고 두 프로세스가 **같은 호스트**에서 돈다. NFS·SMB 같은 네트워크 파일시스템 금지.
  - 백업은 파일 복사가 아니라 `sqlite3 /data/hub.sqlite3 ".backup /backup/hub-$(date +%F).sqlite3"` 또는 `VACUUM INTO`. 쓰기 중 파일 복사는 깨진 사본을 만든다.
- OAuth 엔드포인트는 10초 안에 답해야 한다.

### 절차

1. `.env` 를 서버에만 둔다. `just env` 로 만들고 운영 값으로 고친다: `HUB_BASE_URL=https://hub.itda.work`, `HUB_MCP_URL=https://hub.itda.work/mcp`, `DJANGO_ALLOWED_HOSTS=hub.itda.work`, `HUB_LOCAL_LOGIN=0`(Google 만) + Google 자격. `HUB_SETTINGS_ENCRYPTION_KEY` 는 한 번 만들면 바꾸지 않는다 — 바꾸면 저장된 설정 값을 전부 풀 수 없다.
2. `docker compose up -d --build`. 부트스트랩이 introspection 앱·관리자 계정을 만든다(손으로 DOT Application 을 만들 필요가 없다).
3. Google OAuth 클라이언트의 리디렉션 URI 에 `${HUB_BASE_URL}/accounts/google/login/callback/` 을 등록한다.
4. 리버스 프록시(Caddy 등)에서 HTTPS 를 종단하고 `/mcp` 는 `127.0.0.1:8080`, 나머지는 `127.0.0.1:8000` 으로 보낸다. `/.well-known/*` 는 Django 로 간다. `X-Forwarded-Proto: https` 를 붙인다(설정이 `HUB_BASE_URL` 이 https 일 때 그 헤더를 신뢰한다).
5. 스모크: `curl -sS ${HUB_BASE_URL}/.well-known/oauth-authorization-server | jq .issuer` 가 `HUB_BASE_URL` 과 같아야 하고, `curl -sS ${HUB_BASE_URL}/.well-known/oauth-protected-resource/mcp | jq .resource` 가 `HUB_MCP_URL` 과 같아야 한다. `curl -si ${HUB_MCP_URL} -X POST` 는 401 과 `WWW-Authenticate: Bearer resource_metadata=…` 를 돌려준다.
6. 커스텀 커넥터 왕복 실측은 [#1](https://github.com/itda-work/itda-hub/issues/1) 의 체크리스트로 한다.

## 기수 리셋

교육 기수가 끝나면 `ToolboxEntry`·`ToolSetting`·`ToolCall`·연결 토큰(`AccessToken` 중 `hub-personal`)을 비우고 관리자 공용 키를 재발급한다. 사용자 계정은 남겨도 되지만 요청이 있으면 삭제한다.
