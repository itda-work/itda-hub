# 기여 안내

잇다 허브는 MIT 오픈소스이고 `django-itda` 와 나란히 자랍니다. 허브에서 범용으로 드러난 조각(요청 단위 자리, 목록 시점 가시성, 스코프↔권한 매핑, 설정 저장소)은 허브에 두지 않고 `django-itda` 로 PR 합니다. 허브는 그 패키지의 첫 외부 소비자입니다.

## 규칙

- 언어: 코드 식별자는 영어, 문서·주석·커밋 메시지는 한국어.
- 비밀은 저장소에 두지 않는다. `.env.example` 에는 이름과 형식만. 시드 데이터는 전부 가상.
- 도구 어댑터가 스킬.잇다 스킬팩(Apache-2.0)의 코드를 가져올 때는 그 파일의 라이선스 헤더와 `NOTICE` 를 유지한다.
- 도구는 기본 읽기 전용. 쓰기 도구는 별도 스코프와 승인 절차 없이는 추가하지 않는다.
- 판정은 채널로 낸다. 성공/실패를 문장으로 추론하지 않는다.
- 새 도구는 카탈로그 선언 + 어댑터 + 테스트 + 도구 문서 한 장이 한 묶음이다. 자격증명이 필요하면 `docs/tool-keys.md` 에 발급 절차 한 절과 `.env.example` 의 `SHARED_*` 항목을 함께 더한다.
- **어댑터는 `raise_for_status()` 를 쓰지 않는다.** httpx 예외 문자열에는 요청 URL 이 통째로 실리고 그것이 궤적(`ToolCall.reason`)에 저장된다 — 키를 쿼리스트링으로 받는 상류는 그대로 샌다. `mcp_server/tools/safe.py` 의 `check(response, source)` 를 쓴다. 상류 응답 본문을 결과에 실을 때는 `safe.redact(text, secret)` 로 반사된 비밀을 지운다.
- 화면: 템플릿은 Tailwind 유틸리티 클래스로 쓰고 `just css` 로 `static/css/hub.css` 를 다시 빌드해 함께 커밋한다(처음 한 번 `bun install`). CI 의 css 잡이 커밋본과 빌드 결과를 비교한다. 인라인 `<style>`·`style=`·인라인 `<script>`·`on*=` 속성은 쓰지 않는다 — 스크립트는 `static/js/` 파일로(`tests/test_templates_static.py`).

## 작업 흐름

1. 이슈를 먼저 세운다(목표·비목표·인수 조건).
2. 브랜치 `feat|fix/<slug>-<이슈번호>` 에서 작업한다.
3. `just check` 가 통과해야 한다(ruff · pytest · `manage.py check` · 마이그레이션 누락 검사).
4. PR 본문에 검증 명령과 결과를 적는다.
