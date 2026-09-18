# 잇다 허브 — web(gunicorn)·mcp(python -m mcp_server) 가 같은 이미지를 쓴다. 역할은 compose 의 command 가 정한다.
FROM python:3.12-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
# django-itda 는 git 소스라 빌드 단계에만 git 이 필요하다.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .
# 정적 파일은 이미지에 굽는다(whitenoise manifest). 설정 import 에 필요한 값만 빌드용으로 준다.
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=0 HUB_LOCAL_LOGIN=1 python manage.py collectstatic --noinput \
 && useradd --system --uid 10001 --create-home hub && mkdir -p /data && chown -R hub:hub /data /app
USER hub
VOLUME ["/data"]
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "hub.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
