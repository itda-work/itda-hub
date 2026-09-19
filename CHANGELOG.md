# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 를 따른다. 과업별 근거·검증은 `docs/reports/` 에 있다.

## [0.2.1] — 2026-09-20

공개(`hub.itda.work`) 전 보안 강화. 근거: [docs/reports/H-3.md](docs/reports/H-3.md).

### 보안

- **동의 스코프 우회 수정.** 요청 스코프와 도구함의 교집합이 비면 DOT 가 기본 스코프(= 카탈로그 전체)를 넣어,
  도구함 밖 스코프만 요청하거나 빈 도구함으로 동의 폼을 직접 보내면 **카탈로그 전체 스코프의 토큰**이 나왔다
  (`approval_prompt=auto` 경로 포함). 발급 관문을 `ToolboxAuthorizationView.create_authorization_response` 하나로
  모으고, 교집합이 비면 `access_denied` 로 돌려보낸다. v0.1.0 부터 있던 결함.
- 인가 서버 RFC 9700: implicit·password grant 거부, PKCE `plain` 거부(S256 만), 쿼리스트링 토큰 거부,
  RFC 9207 `iss` 를 인가 응답에 싣는다, refresh 토큰 재사용 탐지(계열 폐기), 운영(https)에서는 https 콜백만 등록.
- Google 이 켜지면 이메일+비밀번호 **가입을 닫는다**. `HUB_LOCAL_LOGIN=1` 은 이때 기존 로컬 계정(비상용 관리자)의
  로그인만 뜻한다. Google 가입은 그대로 열려 있다. Google 이 없으면(로컬·자체 호스팅) 가입이 열린다.
- HSTS(기본 1년, `includeSubDomains` — `*.hub.itda.work` 만). SSL 리디렉트는 Caddy 몫이라 Django 는 켜지 않는다.
- 운영 env 에서 `manage.py check --deploy --fail-level WARNING` 0건(조용히 둔 것: `security.W008`·`W021`).

### 변경

- `/healthz`(web·mcp) 응답에 `Cache-Control: no-store`.
- hub-mcp 의 uvicorn 접근 로그에서 성공한 `/healthz` 줄을 거른다(503 은 남긴다).
- allauth 화면이 허브 레이아웃(`templates/base.html`)을 쓴다. 로그인 화면의 가입 안내는 가입이 열려 있을 때만.
- 문서: 가입 정책·보안 설정 표, Caddy 에서 `/healthz` 를 내부 전용으로 두는 매처 예시(`docs/deploy.md`).

## [0.2.0] — 2026-09-20

Python 3.14 · Django 6.1 최신화와 운영 준비. 근거: [docs/reports/H-2.md](docs/reports/H-2.md).

- 의존성: Python 3.14.7 · Django 6.1.1 · django-itda v0.4.0(태그 고정). pytest 는 폐기 경고를 실패로 본다.
- web·mcp 두 `/healthz` 가 판정을 필드로 낸다.
- 운영 오버레이 `compose.prod.yml`(포트 미노출 · 워커 1 · 로그 회전 · SQLite 온라인 백업), 서비스 이름 `hub-web`/`hub-mcp`.
- 프록시(Caddy) 뒤 https·Google 로그인을 운영 env 의 새 프로세스로 고정하는 테스트.
- GitHub Actions CI.

## [0.1.0]

- 로컬 docker compose 로 끝까지 — 로그인 → 도구함 → 연결 토큰 → MCP 클라이언트 → 궤적.
