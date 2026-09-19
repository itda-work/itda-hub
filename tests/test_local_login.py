"""로컬 로그인 — Google 자격이 없는 환경(compose·개발)은 이메일+비밀번호로 들어온다."""

from io import StringIO

from django.conf import settings
from django.core.management import call_command


def test_구글_자격이_없으면_제공자를_설치하지_않고_로컬_로그인이_켜진다():
    assert settings.HUB_LOCAL_LOGIN is True
    assert settings.SOCIALACCOUNT_ONLY is False
    assert 'allauth.socialaccount.providers.google' not in settings.INSTALLED_APPS
    assert 'password1*' in settings.ACCOUNT_SIGNUP_FIELDS


def test_구글이_꺼져_있으면_로컬_가입이_열린다(client, db, django_user_model):
    """로컬·자체 호스팅 — 가입 수단이 이메일+비밀번호뿐이므로 연다. 로그인 화면에 가입 안내가 나온다."""
    from django.conf import settings

    assert settings.HUB_LOCAL_SIGNUP is True
    assert '/accounts/signup/' in client.get('/accounts/login/').content.decode()
    page = client.get('/accounts/signup/')
    assert page.status_code == 200 and 'name="password1"' in page.content.decode()
    response = client.post(
        '/accounts/signup/',
        {'email': 'bob@example.com', 'password1': 'long-enough-pw', 'password2': 'long-enough-pw'},
    )
    assert response.status_code == 302, response.content[:300]
    assert django_user_model.objects.filter(email='bob@example.com').exists()


def test_이메일_비밀번호로_로그인해_도구함에_들어간다(client, user):
    page = client.get('/accounts/login/')
    assert page.status_code == 200 and 'name="password"' in page.content.decode()
    response = client.post('/accounts/login/', {'login': 'alice@example.com', 'password': 'x'})
    assert response.status_code == 302, response.content[:300]
    home = client.get('/toolbox/')
    assert home.status_code == 200 and 'alice@example.com' in home.content.decode()


def test_로컬_주소는_https_전제가_꺼진다():
    assert settings.HUB_HTTPS is False
    assert getattr(settings, 'SESSION_COOKIE_SECURE', False) is False


def test_healthz_는_introspection_앱이_없으면_503(client, db):
    response = client.get('/healthz')
    assert response.status_code == 503
    assert response.json() == {'ok': False, 'db': True, 'introspection_app': False}
    assert 'no-store' in response['Cache-Control'], '실패 응답도 캐시에 남지 않는다'


def test_healthz_는_bootstrap_뒤_200(client, db, monkeypatch):
    monkeypatch.setenv('HUB_INTROSPECTION_CLIENT_SECRET', 'rs-secret')
    call_command('bootstrap', stdout=StringIO(), stderr=StringIO())
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json() == {'ok': True, 'db': True, 'introspection_app': True}
    assert 'rs-secret' not in response.content.decode()
    assert 'no-store' in response['Cache-Control']
    # 공개 경로다 — 누가 부르든(UA) 같은 불리언·같은 상태 코드만 나간다.
    for ua in ('Mozilla/5.0', 'Googlebot/2.1', 'curl/8.0', ''):
        other = client.get('/healthz', HTTP_USER_AGENT=ua)
        assert (other.status_code, other.json()) == (200, response.json())
        assert 'no-store' in other['Cache-Control']
