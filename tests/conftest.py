import os

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault('DJANGO_SECRET_KEY', 'test-only')
os.environ.setdefault('DJANGO_DEBUG', '1')
os.environ.setdefault('HUB_BASE_URL', 'http://testserver')
os.environ.setdefault('HUB_MCP_URL', 'http://testserver/mcp')
os.environ.setdefault('HUB_SETTINGS_ENCRYPTION_KEY', Fernet.generate_key().decode())


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username='alice', email='alice@example.com', password='x'
    )
