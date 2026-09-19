# 잇다 허브 — 개발·검증·로컬 실행 레시피

default:
    @just --list

# .env 생성 — 빈 비밀 값을 채운다(이미 있으면 건드리지 않는다)
env:
    uv run python scripts/make_env.py

# --- 호스트에서 직접(uv) ---
setup:
    uv sync
    uv run python manage.py migrate
    uv run python manage.py seed_catalog
    uv run python manage.py bootstrap

run:
    uv run python manage.py runserver 127.0.0.1:8000

mcp:
    uv run python -m mcp_server

# --- docker compose (hub-web :8000 · hub-mcp :8080, 127.0.0.1 에만) ---
up:
    docker compose up -d --build

down:
    docker compose down

logs *ARGS:
    docker compose logs -f --tail=100 {{ ARGS }}

# 연결 토큰 발급(컨테이너 안). 예: just token admin@example.com --tools weather,kosis --shared
token EMAIL *ARGS:
    @docker compose exec -T hub-web python manage.py issue_token --email {{ EMAIL }} {{ ARGS }}

# --- 운영 오버레이(compose.prod.yml: 포트 미노출 · 워커 1 · 로그 회전) — docs/deploy.md 「동거 배포」 ---
prod-up:
    docker compose -f compose.yml -f compose.prod.yml up -d --build

# SQLite 온라인 백업 → HUB_BACKUP_DIR(기본 ./backups)/hub-<시각>.sqlite3. 운영 cron 이 부른다
backup:
    docker compose -f compose.yml -f compose.prod.yml --profile ops run --rm hub-backup

# MCP 왕복 스모크 — HUB_TOKEN=<토큰> just smoke
smoke:
    uv run python scripts/mcp_smoke.py

# --- 화면(CSS) — 스킬.잇다 웹사이트와 같은 규약 ---
# Tailwind 빌드 → static/css/hub.css(minify, 커밋 대상 — 런타임에 Node 불필요). 처음 한 번 `bun install`.
# 템플릿에 새 클래스를 쓰면 반드시 다시 빌드한다(CI 의 css 잡이 커밋본과 빌드 결과가 같은지 검사한다).
css:
    bash scripts/build-css.sh

css-watch:
    bash scripts/build-css.sh --watch

# --- 검증 ---
check:
    uv run ruff check .
    uv run ruff format --check .
    uv run python manage.py check --fail-level WARNING
    uv run python manage.py makemigrations --check --dry-run
    uv run pytest -q

test *ARGS:
    uv run pytest -q {{ ARGS }}
