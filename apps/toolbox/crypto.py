"""도구 설정 값의 대칭 암호화. 키는 환경변수 HUB_SETTINGS_ENCRYPTION_KEY(Fernet) 하나다.

값은 저장 직전에만 암호화되고 도구를 부르는 순간에만 복호화된다. 화면·로그·궤적에는
평문이 실리지 않는다 — 그것이 SECURITY.md 가 약속하는 계약이다.
"""

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    key = settings.HUB_SETTINGS_ENCRYPTION_KEY
    if not key:
        raise RuntimeError('HUB_SETTINGS_ENCRYPTION_KEY 가 비어 있다 — .env.example 을 보라')
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
