# 잇다 허브 — 개발·검증 레시피

default:
    @just --list

setup:
    uv sync
    uv run python manage.py migrate
    uv run python manage.py seed_catalog

run:
    uv run python manage.py runserver 127.0.0.1:8000

mcp:
    uv run python -m mcp_server

check:
    uv run ruff check .
    uv run ruff format --check .
    uv run python manage.py check
    uv run python manage.py makemigrations --check --dry-run
    uv run pytest -q

test *ARGS:
    uv run pytest -q {{ ARGS }}
