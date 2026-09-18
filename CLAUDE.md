# CLAUDE.md

잇다 허브 — 오픈소스 MCP 허브 서비스. 정체·범위는 [README.md](README.md), 구조 근거는 [docs/architecture.md](docs/architecture.md).

- 응답·문서·주석·커밋 메시지는 한국어. 툴 파라미터의 한글은 리터럴 UTF-8(`\uXXXX` 금지).
- 프로젝트 지식은 저장소 안에 자족적으로. 개인 메모리 의존 0.
- 스택: Python 3.12+ · uv · Django 5.2 LTS · django-itda · django-allauth · django-oauth-toolkit 3.4 · fastmcp 4 · pytest-django · ruff.
- **판정·궤적·승인 핸들·도구 선언은 `django_itda` 것을 쓴다.** 허브에서 범용으로 드러난 조각은 허브에 두지 않고 django-itda 로 PR 한다.
- **Django 안에 MCP 를 호스팅하지 않는다.** `mcp_server/` 는 별도 프로세스이고 토큰 검증은 introspection 이다.
- 비밀은 환경변수로만. 저장소에는 `.env.example` 과 가상 시드만. 도구 설정 값은 암호화 저장하고 화면·로그·궤적에 평문을 남기지 않는다.
- 도구는 기본 읽기 전용. 쓰기 도구는 별도 스코프와 승인 절차 없이 추가하지 않는다.
- 판정은 채널(구조화 필드)로 낸다. 문장 어휘로 성공/실패를 추론하지 않는다.
- 검증: `just check`. 라이브 판정은 Cowork 커스텀 커넥터 왕복 실측이 정본이다.
- 커밋·push·PR 은 사용자 요청 시에만.
