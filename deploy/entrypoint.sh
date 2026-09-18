#!/bin/sh
# web 역할만 스키마·시드·부트스트랩을 돌린다. mcp 는 web 이 healthy 가 된 뒤 뜬다(compose depends_on).
set -eu
if [ "${HUB_ROLE:-web}" = "web" ]; then
  python manage.py migrate --noinput
  python manage.py seed_catalog
  python manage.py bootstrap
fi
exec "$@"
