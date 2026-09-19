"""별도 프로세스에서 `hub.settings` 를 **운영 환경변수로** 읽고 요청 몇 개를 흘려 결과를 JSON 으로 낸다.

설정은 import 시점에 환경변수로 갈린다(HTTPS 전제·Google 제공자 설치). 한 pytest 프로세스 안에서는
tests/settings.py 의 로컬 조건으로 이미 굳었으므로, 운영 조건은 새 프로세스로 잰다.
tests/test_production_settings.py 가 부른다. DB 는 호출자가 주는 임시 파일이다.
"""

import json
import os
import sys

import django


def main(scenario: str) -> dict:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'hub.settings'
    django.setup()

    from django.conf import settings
    from django.core.management import call_command
    from django.test import Client, RequestFactory
    from django.urls import reverse

    call_command('migrate', verbosity=0)
    call_command('seed_catalog', verbosity=0)
    out = {'deploy_check': _deploy_check()}

    if scenario == 'https':
        out['settings'] = {
            'HUB_HTTPS': settings.HUB_HTTPS,
            'SECURE_PROXY_SSL_HEADER': list(settings.SECURE_PROXY_SSL_HEADER),
            'SESSION_COOKIE_SECURE': settings.SESSION_COOKIE_SECURE,
            'CSRF_COOKIE_SECURE': settings.CSRF_COOKIE_SECURE,
            'CSRF_TRUSTED_ORIGINS': settings.CSRF_TRUSTED_ORIGINS,
        }
        # Caddy 는 Host 를 그대로 넘기고 X-Forwarded-Proto 를 붙인다. 컨테이너까지는 평문 http 다.
        proxied = Client(HTTP_HOST='hub.itda.work', HTTP_X_FORWARDED_PROTO='https')
        doc = proxied.get('/.well-known/oauth-authorization-server').json()
        out['issuer'] = doc['issuer']
        out['authorization_endpoint'] = doc['authorization_endpoint']
        out['token_endpoint'] = doc['token_endpoint']
        prm = proxied.get('/.well-known/oauth-protected-resource/mcp').json()
        out['resource'] = prm['resource']
        out['authorization_servers'] = prm['authorization_servers']
        # 프록시가 붙인 헤더로 https 를 인정하는지 — 요청에서 만드는 절대 주소(allauth 콜백 등)가 그 물증이다.
        factory = RequestFactory(HTTP_HOST='hub.itda.work')
        behind = factory.get('/', HTTP_X_FORWARDED_PROTO='https')
        bare = factory.get('/')
        out['proxied_is_secure'] = behind.is_secure()
        out['proxied_absolute'] = behind.build_absolute_uri('/accounts/login/')
        out['bare_is_secure'] = bare.is_secure()
        # HSTS 는 https 로 본 요청에만 붙는다(SecurityMiddleware) — 컨테이너 사이 평문 호출에는 없다.
        out['hsts_proxied'] = proxied.get('/healthz').get('Strict-Transport-Security', '')
        out['hsts_bare'] = (
            Client().get('/healthz', HTTP_HOST='hub-web').get('Strict-Transport-Security', '')
        )
        out['healthz_bare_status'] = Client().get('/healthz', HTTP_HOST='hub-web').status_code
        # 운영(https)에서 등록되는 콜백 스킴 — DCR 로 https 와 http 루프백을 각각 등록해 본다.
        out['redirect_schemes'] = settings.OAUTH2_PROVIDER['ALLOWED_REDIRECT_URI_SCHEMES']
        out['dcr_https'] = _dcr(proxied, 'https://claude.ai/api/mcp/auth_callback')
        out['dcr_http_loopback'] = _dcr(proxied, 'http://127.0.0.1:33418/callback')

    if scenario == 'google':
        out['google_installed'] = (
            'allauth.socialaccount.providers.google' in settings.INSTALLED_APPS
        )
        out['callback_path'] = reverse('google_callback')
        out['login_path'] = reverse('google_login')
        page = Client().get('/accounts/login/').content.decode()
        out['login_page_has_google'] = out['login_path'] in page
        out['login_page_has_password'] = 'name="password"' in page
        # 화면 계약(H-4): Google 이 1차 액션으로 먼저, 이메일+비밀번호는 접힌(<details>) 2차.
        google_at, password_at = page.find(out['login_path']), page.find('name="password"')
        out['login_page_google_first'] = 0 <= google_at < password_at
        details_at = page.find('<details')
        out['login_page_password_collapsed'] = (
            0 <= details_at < password_at and '<details open' not in page[details_at:password_at]
        )
        # DEBUG=0 의 오류 화면 — 404 는 허브 레이아웃, 500 은 컨텍스트 없이 렌더되는 독립 문서.
        missing = Client().get('/no-such-page/')
        out['page404_status'] = missing.status_code
        out['page404_branded'] = '페이지를 찾을 수 없습니다' in missing.content.decode()
        from django.template import loader

        out['page500_branded'] = '일시적인 오류' in loader.get_template('500.html').render()
        # 콜백 절대 주소는 요청에서 만든다 — 프록시 뒤에서 https 로 나와야 Google 콘솔의 등록값과 맞는다.
        proxied = Client(HTTP_HOST='hub.itda.work', HTTP_X_FORWARDED_PROTO='https')
        redirect = proxied.post(out['login_path'])
        out['google_redirect_status'] = redirect.status_code
        out['google_redirect'] = redirect.get('Location', '')
        out.update(_signup_policy())

    return out


def _deploy_check() -> list[str]:
    """`manage.py check --deploy` 가 내는 것 중 조용히 두지 않은 WARNING 이상의 id."""
    from django.core import checks

    return sorted(
        m.id
        for m in checks.run_checks(include_deployment_checks=True)
        if m.level >= checks.WARNING and not m.is_silenced()
    )


def _dcr(client, redirect_uri) -> int:
    response = client.post(
        '/o/register/',
        data=json.dumps(
            {
                'client_name': 'probe',
                'redirect_uris': [redirect_uri],
                'grant_types': ['authorization_code', 'refresh_token'],
                'response_types': ['code'],
                'token_endpoint_auth_method': 'none',
            }
        ),
        content_type='application/json',
    )
    return response.status_code


def _signup_policy() -> dict:
    """Google 이 켜진 운영 — 로컬 가입은 닫히고, 로컬 로그인·Google 가입은 열린다."""
    from allauth.core.context import request_context
    from allauth.socialaccount.adapter import get_adapter as get_social_adapter
    from allauth.socialaccount.helpers import complete_social_login
    from allauth.socialaccount.models import SocialAccount
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import Client, RequestFactory

    User = get_user_model()
    out = {'local_signup_setting': settings.HUB_LOCAL_SIGNUP}
    client = Client()
    out['login_page_has_signup_link'] = (
        '/accounts/signup/' in client.get('/accounts/login/').content.decode()
    )
    page = client.get('/accounts/signup/')
    out['signup_page_status'] = page.status_code
    out['signup_page_has_form'] = 'name="password1"' in page.content.decode()
    client.post(
        '/accounts/signup/',
        {
            'email': 'mallory@example.com',
            'password1': 'long-enough-pw',
            'password2': 'long-enough-pw',
        },
    )
    out['local_signup_created'] = User.objects.filter(email='mallory@example.com').exists()

    # 비상용 관리자 — 이미 있는 로컬 계정은 비밀번호로 들어온다.
    User.objects.create_user(username='admin', email='admin@example.com', password='admin-pw')
    login = client.post('/accounts/login/', {'login': 'admin@example.com', 'password': 'admin-pw'})
    out['local_login_status'] = login.status_code
    out['local_login_authenticated'] = client.get('/toolbox/').status_code == 200

    # Google 가입 — 콜백이 끝난 뒤의 allauth 흐름(complete_social_login)을 그대로 탄다.
    request = RequestFactory().get('/accounts/google/login/callback/')
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = AnonymousUser()
    # Google userinfo 응답 모양 그대로 제공자에게 SocialLogin 을 만들게 한다(콜백 뒤와 같은 객체).
    provider = get_social_adapter().get_provider(request, 'google')
    sociallogin = provider.sociallogin_from_response(
        request,
        {'sub': 'g-123', 'email': 'carol@gmail.com', 'email_verified': True, 'name': 'Carol'},
    )
    sociallogin.state = {'process': 'login'}
    # allauth 어댑터는 요청을 컨텍스트에서 읽는다(평소엔 AccountMiddleware 가 건다).
    with request_context(request):
        response = complete_social_login(request, sociallogin)
    out['google_signup_status'] = response.status_code
    out['google_signup_created'] = SocialAccount.objects.filter(
        provider='google', uid='g-123', user__email='carol@gmail.com'
    ).exists()
    return out


if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1]), ensure_ascii=False))
