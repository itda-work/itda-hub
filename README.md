# 잇다 허브 (itda-hub)

> 도구를 골라 **도구함**에 담고, 한 번의 로그인으로 Claude·Cowork 에 연결하는 오픈소스 MCP 허브.
> 사내 도구 카탈로그 · 사용자별 도구함 · 자격증명 금고 · 궤적(감사) 을 Django 위에 세운다.
> 판정과 궤적은 [django-itda](https://github.com/itda-work/django-itda) 가 맡고, 이 저장소는 그 첫 외부 소비자다.

- 상태: 골격 (2026-09-18). 첫 목표는 **스파이크** — Cowork 커스텀 커넥터가 허브의 OAuth 왕복을 통과해 도구함 스코프대로 도구 목록을 받는가.
- 운영 주소(예정): `https://hub.itda.work` · MCP 엔드포인트 `https://hub.itda.work/mcp`
- 라이선스: MIT. 도구 어댑터가 [스킬.잇다 스킬팩](https://github.com/itda-skills)의 코드를 가져오면 그 파일은 Apache-2.0 헤더와 NOTICE 를 유지한다.

## 무엇인가

PlayMCP 의 소비자 쪽 모양을 Django 로 세운 것이다. 세 층이 있다.

| 층 | 무엇 | 어디에 |
|---|---|---|
| 사람 → 허브 | Google 로그인으로 들어와 카탈로그에서 도구를 도구함에 담고, 도구별 설정(내 API 키 또는 관리자 공용 키)을 둔다 | Django 웹 (`hub/`, `apps/`) |
| Claude → 허브 | 커스텀 커넥터가 허브의 OAuth 인가 서버(django-oauth-toolkit 3.4, PKCE·CIMD·DCR)로 사용자 동의를 받는다. **동의 화면의 스코프가 곧 도구함**이다 | `apps/oauth` |
| 도구 실행 | 별도 프로세스의 MCP 서버(fastmcp 4, Streamable HTTP)가 토큰을 introspection 으로 검증하고, 토큰의 스코프대로 도구 목록을 거른 뒤, 사용자의 설정으로 도구를 부른다. 모든 호출은 궤적으로 남는다 | `mcp_server/` |

Django 안에 MCP 를 호스팅하지 않는다. django-itda 의 결정을 따른다 — "LLM 은 월드 서버의 클라이언트" 를 구조로 보인다.

## v1 범위

- Google 로그인(django-allauth). 다른 제공자는 이후 추가.
- 카탈로그 4종: KOSIS 통계 검색·조회, 환율, 유가, 날씨. 전부 HTTPS GET, 읽기 전용.
- 도구함, 도구별 설정(암호화 저장), 관리자 공용 키.
- OAuth 인가 서버: CIMD 우선, DCR 병행, PKCE S256.
- 요청 단위 도구 목록 필터(스코프), 궤적 화면, 관리자 열람.
- 배포: 리버스 프록시 뒤 Django 와 MCP 프로세스 둘.

비목표(v1): 외부 MCP 서버 등록·중계, 쓰기 도구, 결제.

## 구조

```
hub/            Django 프로젝트 · 설정은 환경변수(.env.example)
apps/accounts   Google 로그인 · 프로필
apps/catalog    도구 카탈로그 · 도구별 스코프 정의
apps/toolbox    사용자 도구함 · 도구별 설정(암호화)
apps/oauth      인가 서버 설정 · 동의 화면(스코프 = 도구함)
apps/trajectory 궤적 화면(django-itda ToolCall 위)
mcp_server/     별도 프로세스 · fastmcp HTTP · introspection 검증 · 도구 어댑터
deploy/         compose · 리버스 프록시 · 절차
docs/           아키텍처 · 배포 · 강의 가이드
```

## 빠른 시작 (개발)

필요한 것: Python 3.12+, [uv](https://docs.astral.sh/uv/), [just](https://just.systems).

```bash
cp .env.example .env      # 값을 채운다 (개발은 DEBUG=1, sqlite)
just setup                # uv sync → migrate → seed_catalog
just run                  # http://127.0.0.1:8000
just mcp                  # MCP 프로세스 (기본 http://127.0.0.1:8080/mcp)
just check                # ruff · manage.py check · 마이그레이션 누락 · pytest
```

## 문서

- [docs/architecture.md](docs/architecture.md) — 두 겹의 OAuth, 스코프 = 도구함, 프로세스 경계
- [docs/deploy.md](docs/deploy.md) — 운영 배포 절차
- [docs/lecture-guide.md](docs/lecture-guide.md) — Cowork 교육생 연결 가이드
- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md)
