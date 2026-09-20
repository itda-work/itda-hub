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
- 로그인은 이메일+비밀번호(`HUB_LOCAL_LOGIN=1`), 가입도 열려 있다. Google 을 붙이려면 `GOOGLE_OAUTH_CLIENT_ID/SECRET` 을 채운다(리디렉션 URI `${HUB_BASE_URL}/accounts/google/login/callback/`). 자격이 있으면 로그인 화면에 Google 버튼이 비밀번호 폼과 함께 나오고, **이메일+비밀번호 가입은 닫힌다** — 아래 「가입 정책」.

### 상태 확인 (healthz)

| 프로세스 | 주소 | 판정 필드(하나라도 거짓이면 503) |
|---|---|---|
| hub-web | `GET /healthz` (공개 경로) | `db`(SELECT 1 왕복) · `introspection_app`(bootstrap 이 만든 리소스 서버 Application 존재) |
| hub-mcp | `GET /healthz` (프록시가 `/mcp` 만 넘기므로 비공개) | `db` · `introspection_secret`(환경에 시크릿 존재 — 값은 싣지 않는다) |

compose healthcheck 가 둘 다 부른다. hub-mcp 는 hub-web 이 healthy 여야 뜬다.

- 응답은 불리언뿐이고, 요청(UA·헤더)과 무관하게 200/503 만 낸다. `Cache-Control` 에 `no-store` 가 붙는다(web 은 `never_cache`).
- hub-mcp 의 uvicorn 접근 로그는 **성공한 `/healthz` 줄을 거른다**(`mcp_server/logs.py`) — healthcheck 10초 간격이 로그를 덮지 않게. 503 은 남긴다.
- web 의 `/healthz` 는 기본으로 공개다(프록시가 나머지를 전부 web 으로 보낸다). 내용이 불리언뿐이라 두지만, 닫으려면 아래 「동거 배포」의 Caddy 매처를 쓴다. compose healthcheck 는 컨테이너 안에서 `127.0.0.1` 로 부르므로 Caddy 설정과 무관하다.

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
- http → https 리디렉트는 Caddy 가 한다(자동 HTTPS). Django 는 `SECURE_SSL_REDIRECT` 를 켜지 않는다 — 켜면 컨테이너 사이 평문 호출(healthcheck, hub-mcp → hub-web introspection)이 301 로 튄다. HSTS 헤더는 Django 가 낸다(아래 「보안 설정」).

`/healthz` 를 바깥에서 닫으려면(선택) — 사설 대역(같은 VM·compose 네트워크의 점검)만 통과시키고 나머지는 404:

```caddyfile
hub.itda.work {
	@healthz_public {
		path /healthz
		not remote_ip private_ranges
	}
	handle @healthz_public {
		respond 404
	}
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

`handle` 블록은 위에서부터 첫 일치 하나만 탄다 — `@healthz_public` 을 맨 위에 둔다. 앞단에 CDN(Cloudflare 등)을 두면 `remote_ip` 는 CDN 주소가 되므로, 그때는 `client_ip` 와 `trusted_proxies` 를 같이 설정한다. 외부 가용성 감시가 필요하면 막지 말고 그대로 둔다(기본값).

백업은 호스트 cron(03:30)이 부른다. 사본은 `HUB_BACKUP_DIR`(uid 10001 이 쓸 수 있어야 한다)에 `hub-<서울 시각>.sqlite3` 로 남고, `HUB_BACKUP_KEEP_DAYS`(기본 14)보다 오래된 `hub-*.sqlite3` 만 지운다. 무결성 검사(`integrity_check`)가 ok 가 아니면 사본을 남기지 않고 종료 코드 1.

```cron
30 3 * * * cd /opt/itda-website && docker compose -f compose.yaml -f compose.prod.yaml --profile ops run --rm hub-backup
```

### 운영 `.env`

`.env.example` 의 「운영」 절이 정본이다. 요점:

- `HUB_BASE_URL=https://hub.itda.work` · `HUB_MCP_URL=https://hub.itda.work/mcp` · `DJANGO_ALLOWED_HOSTS=hub.itda.work` · `DJANGO_DEBUG=0`. CSRF 오리진은 비우면 `HUB_BASE_URL` 하나.
- `GOOGLE_OAUTH_CLIENT_ID/SECRET` — 옛 사이트의 OAuth 클라이언트를 재사용한다. 리디렉션 URI `https://hub.itda.work/accounts/google/login/callback/` 이 등록돼 있어야 한다.
- `HUB_LOCAL_LOGIN=1` 을 비상용으로 병행한다(관리자 계정 — Google 이 막혀도 들어갈 길). Google 이 켜져 있으므로 **이미 있는 로컬 계정의 로그인만** 된다 — 관리자는 `bootstrap` 이 `HUB_ADMIN_EMAIL/PASSWORD` 로 만든다. 0 이면 Google 만.
- `HUB_HSTS_SECONDS`(선택, 기본 31536000). 처음 공개할 때 짧게(예 300) 두고 확인한 뒤 올려도 된다.

### 가입 정책

| 환경 | 이메일+비밀번호 로그인 | 이메일+비밀번호 가입 | Google 가입·로그인 |
|---|---|---|---|
| Google 자격 없음 + `HUB_LOCAL_LOGIN=1`(로컬·자체 호스팅) | 됨 | **됨** | — |
| Google 자격 있음 + `HUB_LOCAL_LOGIN=1`(운영) | 기존 계정만 | **닫힘** — `/accounts/signup/` 은 「가입 닫힘」 화면, 로그인 화면에 가입 링크 없음 | 됨 |
| Google 자격 있음 + `HUB_LOCAL_LOGIN=0` | 없음 | 없음 | 됨 |

판정은 `settings.HUB_LOCAL_SIGNUP` 한 곳이고 allauth 어댑터(`apps/accounts/adapters.py`)가 쓴다. Google 가입은 소셜 어댑터가 따로 연다(기본 구현은 로컬 가입을 따라가 같이 닫힌다). 새 프로세스의 운영 env 로 `tests/test_production_settings.py` 가 고정한다.

### 보안 설정 (`check --deploy`)

운영 env(`HUB_BASE_URL` 이 https)에서 `python manage.py check --deploy --fail-level WARNING` 이 **0건**이다. `tests/test_production_settings.py` 가 새 프로세스로 잰다.

| 무엇 | 설정 | 비고 |
|---|---|---|
| implicit·password grant 거부 | `COMPLIANT_BCP_RFC9700_IMPLICIT_GRANT/PASSWORD_GRANT` | 메타데이터 `grant_types_supported` 에서도 빠진다 |
| PKCE S256 만(plain 거부), PKCE 필수 | `COMPLIANT_BCP_RFC9700_PKCE_METHOD` · `PKCE_REQUIRED` | 커스텀 커넥터는 S256 |
| 쿼리스트링 토큰 거부 | `COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT` | 토큰은 `Authorization` 헤더로만. introspection(POST 본문)은 무관 |
| RFC 9207 `iss` | `COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS` | 인가 응답 리디렉트에 `iss=HUB_BASE_URL` |
| refresh 재사용 탐지 | `REFRESH_TOKEN_REUSE_PROTECTION` | 회전된 옛 refresh 가 다시 오면 계열을 통째로 폐기 |
| 운영은 https 콜백만 | `ALLOWED_REDIRECT_URI_SCHEMES=['https']`(로컬은 http 도) | claude.ai·Cowork 콜백은 `https://claude.ai/api/mcp/auth_callback`. 대가: 네이티브 앱의 http 루프백 콜백(RFC 8252)은 운영에서 등록되지 않는다 — Claude Code 는 연결 토큰으로 붙으므로 무관 |
| 토큰 원문 미저장 | `COMPLIANT_BCP_RFC9700_TOKEN_STORAGE` | 체크섬만(기존) |
| HSTS | `SECURE_HSTS_SECONDS`(기본 1년) · `INCLUDE_SUBDOMAINS` | https 로 본 요청(프록시 헤더)에만 붙는다. includeSubDomains 는 `*.hub.itda.work` 만 덮는다 |
| 쿠키 Secure | `SESSION_COOKIE_SECURE` · `CSRF_COOKIE_SECURE` | 기존 |
| 조용히 둔 것 | `security.W008`(SSL 리디렉트 — Caddy 몫) · `security.W021`(HSTS preload — 등록 도메인 `itda.work` 단위의 결정) | https 일 때만 |
- `HUB_SETTINGS_ENCRYPTION_KEY` 는 한 번 정하면 불변이다 — 바꾸면 저장된 도구 설정(API 키)을 전부 풀 수 없다. 백업과 같이 보관한다.

### 카탈로그 정합 (`check --deploy`)

**그 DB 를 대상으로** `python manage.py check --deploy --fail-level WARNING` 을 돌린다. 코드의 어댑터와 **지금 그 DB 의 카탈로그 행**이 어긋났는지 본다(`apps/catalog/checks.py`). 위 「보안 설정」과 같은 한 줄이 둘 다 잰다.

| id | 판정 | 사용자가 겪는 것 |
|---|---|---|
| `catalog.E001` | 공개(`enabled=True`)인데 어댑터가 없다 | 동의 화면과 토큰에는 스코프가 실리는데 `tools/list` 에 도구가 없다 — 「허용했는데 도구가 안 보인다」 |
| `catalog.E002` | 어댑터만 있고 카탈로그 행이 없다 | 스코프가 정의되지 않아 아무도 부를 수 없는 죽은 코드 |
| `catalog.E003` | 자격증명이 필요한 공개 도구의 설정 키가 비었다 | 넣을 칸의 이름을 모르고, 공용 키 환경변수 이름도 만들 수 없다 |
| `catalog.W001` | 카탈로그를 **읽지 못했다** — DB 에 못 붙었거나 파일이 손상됐다 | 점검이 통과한 것이 아니다. `--fail-level WARNING` 이 여기서 멈춘다 |

`tests/test_catalog_adapter_contract.py` 가 보는 것은 **CI 가 심은 시드**다. 운영 DB 는 그것과 다를 수 있다 — admin 목록에서 `enabled` 를 바로 켤 수 있고(`list_editable`), `seed_catalog` 는 멱등이지만 CATALOG 에 없는 기존 행을 지우지 않는다. 그래서 CI 가 초록인 채로 운영만 어긋날 수 있고, 그 구멍을 이 커맨드가 메운다. **admin 에서 `enabled` 나 설정 키를 고친 뒤에는 매번 돌린다.**

- **`--deploy` 에서만 돈다. 기동과 복구는 무엇도 막지 않는다.** 일반 체크로 등록하면 `BaseCommand.execute` 가 모든 관리 커맨드 앞에서 돌려, 불일치가 생긴 순간 `migrate` 가 종료코드 1 을 내고 `entrypoint.sh` 의 `set -eu` 때문에 hub-web 이 **부팅하지 못한다** — 복구 수단인 `seed_catalog`·`backup_db` 까지 함께. 배포 체크는 그 경로에 실리지 않는다. 대가로 `just check`(`--deploy` 없음)에서는 돌지 않는다.
- `E002` 를 고치는 방법은 그 DB 에서 `manage.py seed_catalog` 를 돌리는 것이다. 카탈로그가 **통째로** 비어 있으면 복원이 덜 됐는지부터 본다 — 행 0 도 판정 대상이다.
- **조용히 건너뛰는 것은 「붙었는데 테이블이 없다」 하나뿐이다**(`check` 는 `migrate` 앞에서도 돈다). 나머지는 드러낸다 — 접속 실패는 `catalog.W001`, 붙은 뒤의 조회 실패(`database is locked` — WAL 로 두 프로세스가 같은 파일을 쓴다)는 그대로 터진다. SQLite 손상(`file is not a database`)이 **새 연결의 초기 PRAGMA** 에서 드러나면 접속 실패와 구분되지 않으므로, 둘을 가르는 대신 둘 다 `W001` 로 보이게 한다(붙은 뒤 드러나는 손상은 위대로 터진다). 배포 직전 점검이 DB 장애를 초록으로 덮는 것이 가장 나쁘다.
- 이 커맨드는 **이미 발급된 토큰을 회수하지 않는다.** `tokens.sync_scope()` 는 도구함 변경 경로에만 있고 admin 의 `enabled` 수정은 그것을 부르지 않는다.

## 운영 전제

- 공개 HTTPS 도메인 하나(`HUB_BASE_URL`). Claude 는 Anthropic 아웃바운드 대역 `160.79.104.0/21` 에서 허브와 인가 서버 양쪽에 닿아야 한다. WAF 가 이 대역을 막으면 연결이 실패한다.
- 프로세스 둘: Django(hub-web) 와 MCP(`python -m mcp_server`). 같은 DB 를 본다. v1 은 SQLite(WAL) 로 충분하다.
  - WAL 은 설정의 `init_command` 가 연결마다 건다(`journal_mode=WAL`, `synchronous=NORMAL`), 잠금 대기는 `timeout=20`(초), 쓰기 트랜잭션은 `IMMEDIATE`.
  - 전제: DB 파일과 `-wal`·`-shm` 파일이 **같은 로컬 볼륨**에 있고 두 프로세스가 **같은 호스트**에서 돈다. NFS·SMB 같은 네트워크 파일시스템 금지.
  - 백업은 파일 복사가 아니라 `manage.py backup_db`(sqlite3 백업 API). 쓰기 중 파일 복사는 깨진 사본을 만든다.
- OAuth 엔드포인트는 10초 안에 답해야 한다.

## 검증 절차

세 단계를 차례로 한다. 앞 단계가 통과해야 다음으로 간다.

1. **로컬 스모크** — `just check`(ruff · `manage.py check --fail-level WARNING` · 마이그레이션 누락 · pytest, 폐기 경고는 실패 — 운영 env 의 `check --deploy` 0건 포함) → `just up` → `just token <이메일> --tools weather,kosis --shared` 로 토큰을 찍고 `HUB_TOKEN=<토큰> just smoke`. 토큰 없이 거부 · 도구함 스코프만큼의 목록 · 날씨 호출 · KOSIS(키 있으면 ok, 없으면 거부) 네 축을 한 번에 잰다.
2. **원격 스모크**(공개 HTTPS 배포 뒤)
   - 발견 문서: `uv run --with httpx python -c "import httpx; b='https://hub.itda.work'; print(httpx.get(b+'/.well-known/oauth-authorization-server').json()['issuer']); print(httpx.get(b+'/.well-known/oauth-protected-resource/mcp').json()['resource']); r=httpx.post(b+'/mcp'); print(r.status_code, r.headers.get('www-authenticate'))"` — `issuer` 가 `HUB_BASE_URL`, `resource` 가 `HUB_MCP_URL`, `/mcp` 는 401 과 `Bearer resource_metadata=…`.
   - `https://hub.itda.work/healthz` 가 `{"ok": true, …}`(Caddy 매처로 닫았다면 404, VM 안에서 `docker compose … exec hub-web python -c "…urlopen('http://127.0.0.1:8000/healthz')…"` 는 200). 응답 헤더에 `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
   - VM 에서 `docker compose … exec -T hub-web python manage.py check --deploy --fail-level WARNING` → `no issues (2 silenced)`. 보안 설정(위 표)과 **운영 DB 의 카탈로그 정합**(`catalog.E001~E003`)을 한 번에 잰다 — 「카탈로그 정합」 절. admin 에서 도구를 켜고 끈 뒤에는 이 한 줄을 다시 돌린다.
   - `https://hub.itda.work/accounts/signup/` 이 「가입 닫힘」, 로그인 화면에 Google 버튼과 비밀번호 폼(가입 링크 없음).
   - 운영 VM 에서 토큰을 찍고(`docker compose … exec -T hub-web python manage.py issue_token --email <이메일> --tools weather`) 로컬에서 `HUB_MCP_URL=https://hub.itda.work/mcp HUB_TOKEN=<토큰> just smoke`.
   - Google 로그인 한 번(브라우저) — 콜백이 `https://hub.itda.work/accounts/google/login/callback/` 으로 돌아와 도구함에 들어간다.
3. **커스텀 커넥터 OAuth 왕복** — claude.ai(또는 Cowork)에서 커스텀 커넥터로 `https://hub.itda.work/mcp` 를 붙인다. 동의 화면의 스코프가 도구함과 같고, 연결 뒤 도구 목록이 도구함만큼이며, 호출이 궤적에 남는지. 체크리스트는 [#1](https://github.com/itda-work/itda-hub/issues/1). 이 축은 공개 HTTPS 에서의 실측이 정본이다.

## 기수 리셋

교육 기수가 끝나면 `ToolboxEntry`·`ToolSetting`·`ToolCall`·연결 토큰(`AccessToken` 중 `hub-personal`)을 비우고 관리자 공용 키를 재발급한다. 사용자 계정은 남겨도 되지만 요청이 있으면 삭제한다.
