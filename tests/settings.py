"""테스트 설정 — hub.settings 를 읽기 **전에** 환경변수를 박는다.

pytest-django 는 conftest 의 env 기본값보다 먼저 settings 를 import 하므로, 개발자의 .env 가 있으면 그 값
(DJANGO_DEBUG=0 등)이 테스트를 바꾼다. 여기서 명시 대입해 .env 유무와 무관하게 같은 조건으로 돈다.
"""

import os

from cryptography.fernet import Fernet

os.environ.update(
    {
        'DJANGO_SECRET_KEY': 'test-only',
        'DJANGO_DEBUG': '1',
        'DJANGO_ALLOWED_HOSTS': 'testserver,localhost,127.0.0.1',
        'DATABASE_URL': 'sqlite:///db.sqlite3',
        'HUB_BASE_URL': 'http://testserver',
        'HUB_MCP_URL': 'http://testserver/mcp',
        'HUB_LOCAL_LOGIN': '1',
        'GOOGLE_OAUTH_CLIENT_ID': '',
        'HUB_SETTINGS_ENCRYPTION_KEY': Fernet.generate_key().decode(),
        'HUB_INTROSPECTION_CLIENT_ID': 'hub-mcp',
    }
)
os.environ.pop('HUB_INTROSPECTION_URL', None)

from hub.settings import *
