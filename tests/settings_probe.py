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
    out = {}

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

    if scenario == 'google':
        out['google_installed'] = (
            'allauth.socialaccount.providers.google' in settings.INSTALLED_APPS
        )
        out['callback_path'] = reverse('google_callback')
        out['login_path'] = reverse('google_login')
        page = Client().get('/accounts/login/').content.decode()
        out['login_page_has_google'] = out['login_path'] in page
        out['login_page_has_password'] = 'name="password"' in page
        # 콜백 절대 주소는 요청에서 만든다 — 프록시 뒤에서 https 로 나와야 Google 콘솔의 등록값과 맞는다.
        proxied = Client(HTTP_HOST='hub.itda.work', HTTP_X_FORWARDED_PROTO='https')
        redirect = proxied.post(out['login_path'])
        out['google_redirect_status'] = redirect.status_code
        out['google_redirect'] = redirect.get('Location', '')

    return out


if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1]), ensure_ascii=False))
