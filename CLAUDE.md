# CLAUDE.md

잇다 허브 — 오픈소스 MCP 허브 서비스. 정체·범위는 [README.md](README.md), 구조 근거는 [docs/architecture.md](docs/architecture.md).

- 응답·문서·주석·커밋 메시지는 한국어. 툴 파라미터의 한글은 리터럴 UTF-8(`\uXXXX` 금지).
- 프로젝트 지식은 저장소 안에 자족적으로. 개인 메모리 의존 0.
- 스택: Python 3.14 · uv · Django 6.1 · django-itda 0.4(태그 고정) · django-allauth · django-oauth-toolkit 3.4 · fastmcp 4 · pytest-django · ruff.
- **판정·궤적·승인 핸들·도구 선언은 `django_itda` 것을 쓴다.** 허브에서 범용으로 드러난 조각은 허브에 두지 않고 django-itda 로 PR 한다.
- **Django 안에 MCP 를 호스팅하지 않는다.** `mcp_server/` 는 별도 프로세스이고 토큰 검증은 introspection 이다.
- **연결 토큰은 DOT `AccessToken` 을 그대로 쓴다**(`apps/toolbox/tokens.py`). 별도 토큰 모델·별도 검증 경로를 만들지 않는다 — MCP 서버가 OAuth 토큰과 연결 토큰을 구분하지 않는 것이 계약이다. 원문은 체크섬만 저장(RFC 9700).
- 로그인 수단: Google 은 `GOOGLE_OAUTH_CLIENT_ID` 가 있을 때만, 로컬·자체 호스팅은 `HUB_LOCAL_LOGIN`. 둘 다 없으면 부팅이 거부된다. Google 이 켜지면 가입은 Google 로만(`HUB_LOCAL_SIGNUP`, `apps/accounts/adapters.py`) — 로컬은 기존 계정 로그인만.
- 인가 서버는 RFC 9700 자세(implicit·password·PKCE plain·쿼리스트링 토큰 거부, `iss`, refresh 재사용 탐지, 운영 https 콜백만). 운영 env 의 `check --deploy` 0건을 `tests/test_production_settings.py` 가 지킨다. 토큰 발급 관문은 `ToolboxAuthorizationView.create_authorization_response` 하나 — 도구함과의 교집합이 비면 거부.
- 비밀은 환경변수로만. 저장소에는 `.env.example` 과 가상 시드만. 도구 설정 값은 암호화 저장하고 화면·로그·궤적에 평문을 남기지 않는다. 토큰 원문을 찍는 곳은 발급 화면(1회)과 `issue_token` 의 stdout 뿐이다.
- 도구는 기본 읽기 전용. 쓰기 도구는 별도 스코프와 승인 절차 없이 추가하지 않는다.
- 판정은 채널(구조화 필드)로 낸다. 문장 어휘로 성공/실패를 추론하지 않는다.
- 검증: `just check`(단위) → `just up` 뒤 `HUB_TOKEN=… just smoke`(로컬 compose 라이브). 커스텀 커넥터 축은 공개 HTTPS 배포에서의 OAuth 왕복 실측이 정본이다.
- 테스트 환경변수는 `tests/settings.py` 가 settings import 전에 박는다 — conftest 의 env 기본값은 너무 늦다(pytest-django 가 먼저 settings 를 읽는다).
- 커밋·push·PR 은 사용자 요청 시에만.
