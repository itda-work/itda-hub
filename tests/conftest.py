"""공용 픽스처. 환경변수 기본값은 tests/settings.py 가 settings import 전에 박는다."""

import pytest


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username='alice', email='alice@example.com', password='x'
    )
