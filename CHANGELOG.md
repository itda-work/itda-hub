# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 를 따른다. 과업별 근거·검증은 `docs/reports/` 에 있다.

## [0.5.0] — 2026-09-20

### 추가

- **도구 셋 — 부동산 실거래가 · 한국은행 경제지표 · 환율**([H-6](docs/reports/H-6.md)). 공개 도구가 KOSIS·날씨 둘뿐이라 「매주 자료를 모아 요약」 하는 과업을 받칠 수 없었다. 전부 읽기 전용 HTTPS GET 이고, 키는 도구함 설정 또는 관리자 공용 키로 해석된다(기존 `credentials.resolve` 경로 그대로 — 키가 없으면 `ToolDenied` 이고 그 사실이 궤적에 남는다).
  - `realty-deals` / `realty_deals` — 국토교통부 실거래가(data.go.kr). 시군구 코드(법정동코드 앞 5 자리)·계약연월로 **아파트 매매·전월세**를 조회한다. 설정 키 `DATA_GO_KR_API_KEY`. **전 페이지를 끌어오지 않는다** — 한 호출이 한 페이지이고 `total_count` 를 함께 내 부르는 쪽이 다음 페이지를 고른다(결과가 모델의 컨텍스트로 통째로 들어간다).
  - `ecos` / `ecos_stats` — 한국은행 ECOS. `stat_code` 를 주면 시계열을, 안 주면 `keyword` 로 통계표를 검색한다. 설정 키 `ECOS_API_KEY`.
  - `fx` / `fx_rate` — 비공개였던 카탈로그 행에 어댑터를 붙여 공개로 돌렸다. 출처를 서울외국환중개(공개 API 가 아니라 화면 스크래핑이다)에서 **한국은행 ECOS 의 일별 대원화환율**로 바꿨고, 그래서 `ecos` 와 **같은 인증키**를 쓴다. 도구 행을 따로 둔 이유와 그 대가는 보고서에 적었다.
  - **통화 항목코드를 저장소에 박지 않는다.** `fx_rate` 는 통화 이름 → 항목코드를 상류(`StatisticItemList`)에 묻는다. 코드표를 박아 두면 상류가 항목을 개편했을 때 조용히 다른 통화를 돌려준다. 못 찾으면 고를 수 있는 항목 이름을 함께 낸다.
  - **판정은 채널로.** 세 어댑터 모두 `ok`·`error_code` 에 더해 `error_kind`(`credential`·`argument`·`transient`)를 낸다 — 부르는 쪽이 문장을 파싱하지 않고 「키를 볼지 인자를 볼지 기다릴지」를 안다. 상류의 **데이터 없음**(data.go.kr `03`, ECOS `INFO-200`)은 실패가 아니라 빈 결과로 낸다. 오류로 내면 「그 달에 거래가 없었다」 는 참인 답이 키 의심으로 둔갑한다.
  - **인자 검증을 상류에 미루지 않는다.** 실거래가 상류는 형식이 틀려도 빈 결과를 돌려주는 때가 있어 「코드를 잘못 적었다」 와 「거래가 없었다」 가 구분되지 않는다 — `lawd_cd`(5 자리)·`deal_ymd`(`YYYYMM`)·`deal_type`, ECOS 의 주기·기간을 상류에 닿기 전에 막는다.
  - `seed_catalog` 에 세 행(멱등), `docs/tool-keys.md` 에 발급 가이드 세 절, `.env.example` 에 `SHARED_DATA_GO_KR_API_KEY`·`SHARED_ECOS_API_KEY`, README 에 도구 표.
  - `scripts/mcp_smoke.py` 가 도구마다 한 번씩 부른다(키가 없으면 거부가 그대로 보고서에 남는다). **키가 필요한 도구의 라이브 검증 자리가 여기다** — 단위 테스트는 응답 픽스처로 모양만 고정한다.

### 보안

- **인증키를 URL 경로에 싣는 상류의 누출 경로를 미리 닫았다.** #4 의 처방은 「쿼리스트링을 통째로 버린다」 였는데, ECOS 는 인증키를 **경로 세그먼트**로 받는다(`/api/StatisticSearch/<인증키>/json/kr/...`). 경로는 버릴 수 없다 — 버리면 어느 엔드포인트가 실패했는지가 사라져 안전한 URL 이 아무 말도 하지 않는다. `safe.check(response, source, secret)` 이 **그 호출에 실어 보낸 비밀 값**을 받아 안전한 URL 에서 지운다(파라미터 이름 목록이 아니라 값이라, 새 도구가 목록 갱신을 잊어 새는 경로가 없다). `safe.redact` 는 이제 원문·쿼리 인코딩에 더해 **경로 인코딩**(`quote(safe='')` — 공백이 `+` 가 아니라 `%20`)까지 지운다. `tests/test_credential_leak.py` 가 세 형태를 어댑터 셋 전부에 대해 잰다.

- **상류 HTTP 오류로 API 인증키가 새던 경로를 닫았다**([#4](https://github.com/itda-work/itda-hub/issues/4)). httpx 의 `raise_for_status()` 가 만드는 예외 문자열에는 요청 URL 이 통째로 실리고, django-itda 가 그것을 `ToolCall.reason` 에 저장한다 — KOSIS 처럼 인증키를 쿼리스트링으로 받는 상류는 키가 궤적 DB·궤적 화면·admin 검색에 평문으로 남았다. 게다가 httpx 는 INFO 레벨에서 **성공 호출마다** 요청 URL 을 찍는데 루트 로거가 INFO 였다.
  - 어댑터는 `raise_for_status()` 를 쓰지 않는다. 새 `mcp_server/tools/safe.py` 의 `check()` 가 **쿼리스트링을 버리고** 스킴·호스트·경로만 남긴 `UpstreamError` 로 바꾼다. 원본 예외는 `from None` 으로 체인에서 끊는다 — 남겨 두면 traceback 을 찍는 곳에서 URL 이 다시 드러난다.
  - 「어느 파라미터가 비밀인가」를 목록으로 관리하지 않는다. 쿼리스트링을 통째로 버려 기본을 안전한 쪽에 둔다 — 목록 방식은 새 도구가 목록 갱신을 잊는 순간 다시 샌다.
  - 상류가 오류 문장에 키를 되돌려주는 경우는 `safe.redact()` 가 지운다(KOSIS `errMsg`).
  - `httpx`·`httpcore` 로거를 WARNING 으로 묶었다(`hub/settings.py: LOGGING`). 상류 호출의 관측은 궤적이 맡는다.
  - 회귀 테스트 `tests/test_credential_leak.py` — 키를 **원문과 URL 인코딩 두 형태로** 검사한다(`+`·`/`·`=` 가 `%2B`·`%2F`·`%3D` 가 되므로 원문 검사만으로는 통과하는데 새는 테스트가 된다). 궤적 `reason`·`arguments` 와 **성공·실패 양쪽 로그**를 본다.

### 문서

- `docs/tool-keys.md` 신규 — 도구별 인증키 발급 가이드(KOSIS 절차·오류 코드 대응표·공용 키와 개인 키). 새 도구를 더할 때 채울 항목도 적었다.
- 0.4.0 에서 없앤 연결 토큰 화면을 아직 가리키던 서술을 정리했다 — `docs/lecture-guide.md`(운영자·교육생 순서를 `issue_token` 의 실제 제약에 맞게 다시 씀), `SECURITY.md`, `scripts/mcp_smoke.py` 의 오류 안내, `apps/toolbox/tokens.py`, `issue_token.py`, `static/js/hub.js`, `CLAUDE.md`·`AGENTS.md`, 궤적 빈 화면 문구.
- `docs/architecture.md` — django-itda 0.4 가 본문의 `ToolDenied` 를 `forbidden`/`denied` 로 분류하므로 「돌려보낼 조각」 표의 해당 줄을 해결됨으로 바꾸고, 상류 실패의 구조화 기록을 새 후보로 올렸다.

## [0.4.1] — 2026-09-20

### 변경

- **로고.** 자리표시였던 인디고 바탕 「있」 아이콘(`static/img/favicon.svg`)을 지우고, 스킬.잇다(`itda.work`)의 로고
  `static/img/logo.png` 를 헤더·로그인 화면·파비콘에 쓴다. 워드마크는 「잇다 허브」 그대로.

## [0.4.0] — 2026-09-20

### 변경

- **설정이 필요한 도구는 설정을 마쳐야 담긴다.** 자격증명이 필요한 도구(예: KOSIS)를 설정 없이 담으면 스코프에는 실리고
  호출은 늘 「자격증명이 없다」 로 거부됐다. 이제 담기가 곧 설정이다 — 도구함의 `+` 는 설정 화면으로 가고, 「저장하고
  담기」 가 사용자 키 저장 또는 (실제로 있는) 관리자 공용 키 사용을 확인한 뒤에만 도구함에 넣는다. 공용 키가 있으면
  기본으로 켜져 한 번에 담긴다. 판정은 `apps/toolbox/models.py: is_configured` 한 곳이고 MCP 자격증명 해석과 같은
  규칙이다. `/toolbox/add/` 와 `issue_token` 도 같은 관문을 지난다. 담긴 도구를 미설정 상태로 되돌리는 저장은 거부된다.
- **기존 미설정 항목 정리.** 마이그레이션 `toolbox.0002` 가 설정 없이 담겨 있던 항목(사용자 키 없음 · 공용 키 미사용
  또는 공용 키 부재)을 걷어 낸다. 연결 토큰에 남은 스코프는 다음 담기/빼기·재발급 때 맞춰지고, 그 사이 호출은 MCP 가
  「도구함에 없다」 로 거부한다.
- **연결 토큰 화면 제거 — 사용자에게는 OAuth 커넥터만 노출.** 도구함의 연결 토큰 카드와 `/toolbox/token/`
  (발급·표시·폐기) 경로를 없앴다. 연결 카드는 claude.ai·Cowork 커스텀 커넥터 안내와 MCP 주소 복사만 둔다. 연결 토큰
  자체(`apps/toolbox/tokens.py`, DOT `AccessToken`)와 `issue_token` 커맨드는 운영·스모크용으로 남는다. 이미 발급된
  토큰은 만료(30일)까지 유효하고, 관리자 화면에서 폐기할 수 있다.
- **도구함 카드 UI.** Claude Cowork 커넥터 목록처럼 아이콘 타일 · 이름 · 설명 · 오른쪽 `+`(담기) / `✓`(담김, 누르면
  빼기) 토글로 바꿨다. 라이트/다크.

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
