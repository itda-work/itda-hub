#!/usr/bin/env bash
# Tailwind CSS 빌드 — 스킬.잇다 웹사이트(scripts/build-css.sh)와 같은 규약.
#
# 결과물 static/css/hub.css 는 커밋 대상이다 — 런타임(이미지·서버)에 Node 를 요구하지 않기 위함.
# 템플릿에 새 클래스를 쓰면 반드시 다시 빌드한다. CI 의 css 잡이 커밋본과 빌드 결과가 같은지 검사한다.
#
# 사용법(처음 한 번 `bun install`):
#   bash scripts/build-css.sh            # 1회 빌드(minify)
#   bash scripts/build-css.sh --watch    # 파일 변경 감시(개발용, minify 안 함)
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${1:-}" = "--watch" ]; then
  exec bun x tailwindcss -c tailwind.config.cjs -i static/src/tailwind.css -o static/css/hub.css --watch
fi

bun x tailwindcss -c tailwind.config.cjs -i static/src/tailwind.css -o static/css/hub.css --minify
