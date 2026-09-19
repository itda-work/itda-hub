# 배포

지원 버전: Python 3.14(이미지 `python:3.14.7-slim`) · Django 6.1 · django-itda v0.4.0(태그 고정) · uv 0.12.

## 로컬 (docker compose)

```bash
just env    # .env 생성 — 비밀 4종(SECRET_KEY · Fernet 키 · introspection 시크릿 · 관리자 비밀번호)을 채운다
just up     # docker compose up -d --build  →  hub-web 127.0.0.1:8000 · hub-mcp 127.0.0.1:8080
just logs   # 부팅 로그: migrate → seed_catalog → bootstrap → gunicorn / MCP 서버
just down
```

- `deploy/entrypoint.sh` 가 hub-web 컨테이너에서만 `migrate` → `seed_catalog` → `bootstrap` 을 돌린다. hub-mcp 는 hub-web 이 `/healthz` 로 healthy 가 된 뒤 뜬다.
- `bootstrap` 이 환경변수로 보장하는 것: introspection 리소스 서버 Application(`HUB_INTROSPECTION_CLIENT_ID/SECRET`), 연결 토큰용 Application(`hub-personal`), 관리자 계정(`HUB_ADMIN_EMAIL/PASSWORD` — 이미 있으면 비밀번호 불변). 멱등이고 비밀은 출력하지 않는다.
- 두 컨테이너는 볼륨 `hub-data` 의 SQLite 파일 하나를 공유한다(WAL). hub-mcp 의 토큰 검증은 공개 주소가 아니라 서비스 이름으로 간다(`HUB_INTROSPECTION_URL=http://hub-web:8000/o/introspect/`, `DJANGO_ALLOWED_HOSTS` 에 `hub-web` 추가 — compose 가 넣는다).
- 서비스 이름에 `hub-` 가 붙은 이유: 웹사이트 compose 가 이 파일을 include 해도 그쪽 `web` 과 부딪히지 않는다(아래 「동거 배포」).
- web 워커 수는 `WEB_CONCURRENCY`(로컬 기본 2, 운영 오버레이 기본 1)다. gunicorn 이 직접 읽는다. 유휴 실측은 워커 2개 125 MiB · 1개 약 90 MiB · mcp 92 MiB.
- 포트가 겹치면 `.env` 의 `HUB_WEB_PORT`/`HUB_MCP_PORT` 를 바꾸고 `HUB_BASE_URL`/`HUB_MCP_URL` 도 같이 맞춘다. 두 주소는 화면과 발급 안내에 그대로 찍힌다.
- 로그인은 이메일+비밀번호(`HUB_LOCAL_LOGIN=1`). Google 을 붙이려면 `GOOGLE_OAUTH_CLIENT_ID/SECRET` 을 채운다(리디렉션 URI `${HUB_BASE_URL}/accounts/google/login/callback/`). 자격이 있으면 로그인 화면에 Google 버튼이 비밀번호 폼과 함께 나온다.

### 상태 확인 (healthz)

| 프로세스 | 주소 | 판정 필드(하나라도 거짓이면 503) |
|---|---|---|
| hub-web | `GET /healthz` (공개 경로) | `db`(SELECT 1 왕복) · `introspection_app`(bootstrap 이 만든 리소스 서버 Application 존재) |
| hub-mcp | `GET /healthz` (프록시가 `/mcp` 만 넘기므로 비공개) | `db` · `introspection_secret`(환경에 시크릿 존재 — 값은 싣지 않는다) |

compose healthcheck 가 둘 다 부른다. hub-mcp 는 hub-web 이 healthy 여야 뜬다.

## 운영 오버레이 — `compose.prod.yml`

`compose.yml` 위에 얹는다. 달라지는 것은 넷이다.

1. **호스트 포트를 묶지 않는다**(`ports: !reset []`, compose v2.24+). 리버스 프록시가 같은 compose 네트워크에서 `hub-web:8000` · `hub-mcp:8080` 으로 간다.
2. **web 워커 기본 1**(`WEB_CONCURRENCY` — `.env` 에 값이 있으면 그 값).
3. **로그 회전**(json-file 10m × 5).
4. **일회성 `hub-backup`**(profile `ops`) — SQLite 온라인 백업.

그 밖에 볼륨 이름을 `itda-hub_hub-data` 로 고정한다 — 단독 프로젝트로 띄우든 다른 프로젝트에 include 되든 같은 DB 를 본다. 이미지 태그는 `HUB_IMAGE`(기본 `itda-hub:local`, 이 저장소에서 빌드).

```bash
# 허브만의 compose 프로젝트로
just prod-up     # docker compose -f compose.yml -f compose.prod.yml up -d --build
just backup      # docker compose -f compose.yml -f compose.prod.yml --profile ops run --rm hub-backup
```

### 동거 배포 (스킬.잇다 웹사이트 VM)

웹사이트 저장소의 compose 가 두 파일을 **한 덩어리로 include** 한다. 그러면 허브 서비스가 웹사이트 프로젝트의 기본 네트워크에 붙어 Caddy 가 서비스 이름으로 닿는다. 상대 경로(`build: .` · `env_file: .env` · `HUB_BACKUP_DIR`)는 이 저장소 디렉터리 기준으로 풀리고, 허브 `.env` 는 웹사이트 `.env` 와 분리된 채로 남는다.

```yaml
# 웹사이트 compose.prod.yaml (예시 — 경로는 VM 의 허브 체크아웃 위치)
include:
  - path: [/opt/itda-hub/compose.yml, /opt/itda-hub/compose.prod.yml]
```

Caddy(웹사이트 `Caddyfile.prod`)에 허브 호스트 블록을 둔다. **응답 캐시를 걸지 않는다** — OAuth·MCP 응답은 사용자별이다.

```caddyfile
hub.itda.work {
	# /mcp 는 MCP 프로세스(Streamable HTTP — 즉시 흘려보낸다), 나머지(/o/*, /.well-known/*, 화면, /healthz)는 Django
	handle /mcp* {
		reverse_proxy hub-mcp:8080 {
			flush_interval -1
		}
	}
	handle {
		reverse_proxy hub-web:8000
	}
}
```

- Caddy 의 `reverse_proxy` 는 기본으로 `Host` 를 그대로 넘기고 `X-Forwarded-Proto: https` 를 붙인다. `HUB_BASE_URL` 이 https 면 설정이 그 헤더를 신뢰해(`SECURE_PROXY_SSL_HEADER`) 요청을 https 로 보고, 세션·CSRF 쿠키를 Secure 로 낸다. `USE_X_FORWARDED_HOST` 는 쓰지 않는다(Host 가 이미 공개 이름이다).
- 허브 컨테이너는 호스트 포트가 없으므로 그 헤더를 위조할 수 있는 경로는 Caddy 뿐이다.
- RFC 8414 `issuer` 는 요청과 무관하게 `HUB_BASE_URL` 그대로다(`OIDC_ISS_ENDPOINT`). 프록시 뒤 동작은 `tests/test_production_settings.py` 가 고정한다.

백업은 호스트 cron(03:30)이 부른다. 사본은 `HUB_BACKUP_DIR`(uid 10001 이 쓸 수 있어야 한다)에 `hub-<서울 시각>.sqlite3` 로 남고, `HUB_BACKUP_KEEP_DAYS`(기본 14)보다 오래된 `hub-*.sqlite3` 만 지운다. 무결성 검사(`integrity_check`)가 ok 가 아니면 사본을 남기지 않고 종료 코드 1.

```cron
30 3 * * * cd /opt/itda-website && docker compose -f compose.yaml -f compose.prod.yaml --profile ops run --rm hub-backup
```

### 운영 `.env`

`.env.example` 의 「운영」 절이 정본이다. 요점:

- `HUB_BASE_URL=https://hub.itda.work` · `HUB_MCP_URL=https://hub.itda.work/mcp` · `DJANGO_ALLOWED_HOSTS=hub.itda.work` · `DJANGO_DEBUG=0`. CSRF 오리진은 비우면 `HUB_BASE_URL` 하나.
- `GOOGLE_OAUTH_CLIENT_ID/SECRET` — 옛 사이트의 OAuth 클라이언트를 재사용한다. 리디렉션 URI `https://hub.itda.work/accounts/google/login/callback/` 이 등록돼 있어야 한다.
- `HUB_LOCAL_LOGIN=1` 을 비상용으로 병행한다(관리자 계정 — Google 이 막혀도 들어갈 길). 0 이면 Google 만.
- `HUB_SETTINGS_ENCRYPTION_KEY` 는 한 번 정하면 불변이다 — 바꾸면 저장된 도구 설정(API 키)을 전부 풀 수 없다. 백업과 같이 보관한다.

## 운영 전제

- 공개 HTTPS 도메인 하나(`HUB_BASE_URL`). Claude 는 Anthropic 아웃바운드 대역 `160.79.104.0/21` 에서 허브와 인가 서버 양쪽에 닿아야 한다. WAF 가 이 대역을 막으면 연결이 실패한다.
- 프로세스 둘: Django(hub-web) 와 MCP(`python -m mcp_server`). 같은 DB 를 본다. v1 은 SQLite(WAL) 로 충분하다.
  - WAL 은 설정의 `init_command` 가 연결마다 건다(`journal_mode=WAL`, `synchronous=NORMAL`), 잠금 대기는 `timeout=20`(초), 쓰기 트랜잭션은 `IMMEDIATE`.
  - 전제: DB 파일과 `-wal`·`-shm` 파일이 **같은 로컬 볼륨**에 있고 두 프로세스가 **같은 호스트**에서 돈다. NFS·SMB 같은 네트워크 파일시스템 금지.
  - 백업은 파일 복사가 아니라 `manage.py backup_db`(sqlite3 백업 API). 쓰기 중 파일 복사는 깨진 사본을 만든다.
- OAuth 엔드포인트는 10초 안에 답해야 한다.

## 검증 절차

세 단계를 차례로 한다. 앞 단계가 통과해야 다음으로 간다.

1. **로컬 스모크** — `just check`(ruff · `manage.py check --fail-level WARNING` · 마이그레이션 누락 · pytest, 폐기 경고는 실패) → `just up` → `just token <이메일> --tools weather,kosis --shared` 로 토큰을 찍고 `HUB_TOKEN=<토큰> just smoke`. 토큰 없이 거부 · 도구함 스코프만큼의 목록 · 날씨 호출 · KOSIS(키 있으면 ok, 없으면 거부) 네 축을 한 번에 잰다.
2. **원격 스모크**(공개 HTTPS 배포 뒤)
   - 발견 문서: `uv run --with httpx python -c "import httpx; b='https://hub.itda.work'; print(httpx.get(b+'/.well-known/oauth-authorization-server').json()['issuer']); print(httpx.get(b+'/.well-known/oauth-protected-resource/mcp').json()['resource']); r=httpx.post(b+'/mcp'); print(r.status_code, r.headers.get('www-authenticate'))"` — `issuer` 가 `HUB_BASE_URL`, `resource` 가 `HUB_MCP_URL`, `/mcp` 는 401 과 `Bearer resource_metadata=…`.
   - `https://hub.itda.work/healthz` 가 `{"ok": true, …}`.
   - 운영 VM 에서 토큰을 찍고(`docker compose … exec -T hub-web python manage.py issue_token --email <이메일> --tools weather`) 로컬에서 `HUB_MCP_URL=https://hub.itda.work/mcp HUB_TOKEN=<토큰> just smoke`.
   - Google 로그인 한 번(브라우저) — 콜백이 `https://hub.itda.work/accounts/google/login/callback/` 으로 돌아와 도구함에 들어간다.
3. **커스텀 커넥터 OAuth 왕복** — claude.ai(또는 Cowork)에서 커스텀 커넥터로 `https://hub.itda.work/mcp` 를 붙인다. 동의 화면의 스코프가 도구함과 같고, 연결 뒤 도구 목록이 도구함만큼이며, 호출이 궤적에 남는지. 체크리스트는 [#1](https://github.com/itda-work/itda-hub/issues/1). 이 축은 공개 HTTPS 에서의 실측이 정본이다.

## 기수 리셋

교육 기수가 끝나면 `ToolboxEntry`·`ToolSetting`·`ToolCall`·연결 토큰(`AccessToken` 중 `hub-personal`)을 비우고 관리자 공용 키를 재발급한다. 사용자 계정은 남겨도 되지만 요청이 있으면 삭제한다.
