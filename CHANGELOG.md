# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 를 따른다. 과업별 근거·검증은 `docs/reports/` 에 있다.

## [0.3.1] — 2026-09-20

claude.ai 커스텀 커넥터가 연결되지 않던 문제의 핫픽스. 근거: [docs/reports/H-5.md](docs/reports/H-5.md).

### 수정

- **CIMD grant 해석 완화.** claude.ai 의 클라이언트 메타데이터 문서에 `urn:ietf:params:oauth:grant-type:jwt-bearer` 가
  더해져 DOT 3.4.1 이 「non-refresh grant 가 정확히 하나」 규칙으로 해석을 거부했다(인가 요청이 모르는 클라이언트로
  떨어짐). 허브가 기동 시 `oauth2_provider.cimd._resolve_grant_type` 을 감싸, 서버가 지원하지 않는 grant 는 무시하고
  **지원 grant 가 정확히 하나**일 때만 통과시킨다(`apps/oauth/cimd.py`). 지원 grant 가 0개·2개면 여전히 거부.
  기동 시 claude.ai 표본으로 적용을 자체 검사하고, 실패하면 경고 로그를 남긴다(DOT 를 올릴 때 신호).
- **인가 오류가 「도구함이 비어 있습니다」 로 보이던 오표시.** `ToolboxAuthorizationView.get` 이 DOT 오류 화면(`error`
  컨텍스트, `scopes` 없음)까지 빈 도구함으로 바꾸고 있었다. 이제 오류는 오류 화면으로, **검증 성공 + 도구함과의
  교집합 없음**일 때만 빈 도구함 화면을 낸다. CIMD URL 클라이언트를 확인하지 못한 경우 「클라이언트 등록(CIMD) 실패」
  와 재시도 안내를 보여 준다.

### 변경

- CIMD 해석 실패 메시지에 문서의 `grant_types` 전체와 지원 목록이 실린다(기존 로그의 client_id URL 과 함께). 무시한
  grant 는 INFO 로그로 남는다.

## [0.3.0] — 2026-09-20

화면을 스킬.잇다(`itda.work`)와 한 브랜드로. 기능·모델·URL·OAuth 흐름·폼 필드 이름은 그대로다. 근거: [docs/reports/H-4.md](docs/reports/H-4.md).

### 추가

- Tailwind CSS 빌드 규약(사이트와 같음): `package.json`(tailwindcss 3.4 + typography, bun) · `tailwind.config.cjs`(사이트 토큰 — Pretendard, 기본 팔레트, `darkMode: 'class'`) · `static/src/tailwind.css` → `static/css/hub.css`(minify, 커밋). `just css`/`just css-watch`. CI 에 「CSS 최신 여부」 잡(빌드 후 `git status --porcelain` 0).
- 공통 셸: 상단 네비(워드마크 · 도구함 · 궤적 · 관리자(스태프) · 이메일 · 로그아웃), 메시지 배너, 푸터(스킬.잇다 · Powered by Python · Django), 본문 건너뛰기 링크, 라이트/다크 토글(`html.dark` + `localStorage` `theme`, 부트 가드는 정적 파일 `static/js/theme-boot.js`).
- 로그인: Google 을 1차 액션으로, 이메일+비밀번호는 Google 이 있을 때 접힌 2차. allauth 요소(`templates/allauth/elements/`)를 입혀 가입·비밀번호 재설정·로그아웃 확인도 같은 모양.
- 도구함 카드 · 연결 카드, 연결 토큰 화면의 복사 버튼(`static/js/hub.js`)과 Claude Code 명령 복사, 도구 설정 폼 라벨.
- 궤적 표(판정 배지, 빈 상태 안내), OAuth 동의 화면(`templates/oauth2_provider/authorize.html` — 앱 이름·허용할 도구·허용/거부), 404·500 화면.
- 테스트: 템플릿 정적 검사(`<style>`·`style=`·인라인 `<script>`·`on*=` 0, `lang="ko"`), 주요 화면 렌더(렌더된 동의 폼으로 허용·거부 왕복 포함), 운영(Google) 조건의 로그인 배치와 404/500.

### 변경

- `STATICFILES_DIRS = [BASE_DIR / 'static']` — 새 정적 파일을 collectstatic·whitenoise 가 찾도록(화면 자산 경로만).
- 인라인 `<style>` 과 `style=` 속성 제거.

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
