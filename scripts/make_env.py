"""`.env.example` → `.env`. 빈 비밀 값(SECRET_KEY·Fernet 키·introspection 시크릿·관리자 비밀번호)을 생성해 채운다.

    python scripts/make_env.py            # .env 가 없을 때 새로 만든다(있으면 거부)
    python scripts/make_env.py --update   # 있는 .env 에 .env.example 의 새 키만 덧붙인다(기존 값은 불변)

기존 값을 바꾸지 않는 이유: HUB_SETTINGS_ENCRYPTION_KEY 가 바뀌면 저장된 암호문을, DJANGO_SECRET_KEY 가
바뀌면 세션을, introspection 시크릿이 바뀌면 부트스트랩이 앱을 갱신할 때까지 MCP 검증을 잃는다.
"""

import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
GENERATED = {
    'DJANGO_SECRET_KEY': lambda: secrets.token_urlsafe(48),
    'HUB_SETTINGS_ENCRYPTION_KEY': lambda: Fernet.generate_key().decode(),
    'HUB_INTROSPECTION_CLIENT_SECRET': lambda: secrets.token_urlsafe(32),
    'HUB_ADMIN_PASSWORD': lambda: secrets.token_urlsafe(12),
}


def _example_lines():
    return (ROOT / '.env.example').read_text(encoding='utf-8').splitlines()


def _fill(key, value):
    if not value.strip() and key in GENERATED:
        return GENERATED[key]()
    return value.strip()


def create(target: Path) -> list[str]:
    lines, filled = [], []
    for raw in _example_lines():
        key, sep, value = raw.partition('=')
        if sep and not raw.startswith('#'):
            new = _fill(key.strip(), value)
            if new != value.strip():
                filled.append(key.strip())
            lines.append(f'{key.strip()}={new}')
        else:
            lines.append(raw)
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return filled


def update(target: Path) -> list[str]:
    present = set()
    for raw in target.read_text(encoding='utf-8').splitlines():
        key, sep, _ = raw.partition('=')
        if sep and not raw.startswith('#'):
            present.add(key.strip())
    added = []
    for raw in _example_lines():
        key, sep, value = raw.partition('=')
        if sep and not raw.startswith('#') and key.strip() not in present:
            added.append(f'{key.strip()}={_fill(key.strip(), value)}')
    if added:
        with target.open('a', encoding='utf-8') as f:
            f.write('\n# --- make_env --update 가 덧붙인 키 ---\n' + '\n'.join(added) + '\n')
    return [line.partition('=')[0] for line in added]


def main() -> int:
    target = ROOT / '.env'
    if '--update' in sys.argv[1:]:
        if not target.exists():
            print('.env 가 없다 — --update 없이 실행해 새로 만들어라.', file=sys.stderr)
            return 1
        keys = update(target)
        print(f'.env 갱신 — 덧붙인 키: {", ".join(keys) or "없음"}')
        return 0
    if target.exists():
        print(
            '.env 가 이미 있다 — 새 키만 더하려면 --update, 새로 만들려면 지우고 다시 실행하라.',
            file=sys.stderr,
        )
        return 1
    keys = create(target)
    print(
        f'.env 생성 — 채운 값: {", ".join(keys)}. 관리자 비밀번호는 .env 의 HUB_ADMIN_PASSWORD 에 있다.'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
