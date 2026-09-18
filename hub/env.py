"""`.env` 최소 로더 — 있으면 읽어 os.environ 에 **없는 키만** 채운다. 배포 환경은 실제 환경변수가 우선한다."""

import os
from pathlib import Path


def load(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
