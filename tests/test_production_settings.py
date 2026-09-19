"""운영 조건 — 프록시(Caddy) 뒤 https 와 Google 로그인. 설정이 import 시점에 갈리므로 새 프로세스로 잰다."""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent


def _probe(scenario, tmp_path, **env):
    base = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(('HUB_', 'DJANGO_', 'GOOGLE_', 'DATABASE_'))
    }
    # 개발자의 .env 가 빈칸을 채우지 않도록 전부 명시한다(hub.env 는 없는 키만 채운다).
    base.update(
        {
            'DJANGO_SECRET_KEY': secrets.token_urlsafe(
                50
            ),  # check --deploy 가 약한 키(W009)를 본다
            'DJANGO_DEBUG': '0',
            'DATABASE_URL': f'sqlite:///{tmp_path / "hub.sqlite3"}',
            'HUB_SETTINGS_ENCRYPTION_KEY': Fernet.generate_key().decode(),
            'HUB_INTROSPECTION_CLIENT_ID': 'hub-mcp',
            'HUB_INTROSPECTION_URL': '',
            'GOOGLE_OAUTH_CLIENT_ID': '',
            'GOOGLE_OAUTH_CLIENT_SECRET': '',
            'DJANGO_LOG_LEVEL': 'WARNING',
        }
    )
    base.update(env)
    # 운영 이미지는 collectstatic 을 굽지만 여기는 아니다 — 매니페스트 없이 템플릿이 렌더되도록 단순 저장소로.
    code = (
        'import sys, runpy; sys.argv = ["probe", sys.argv[1]];'
        'import hub.settings as s;'
        's.STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"};'
        'runpy.run_module("tests.settings_probe", run_name="__main__")'
    )
    done = subprocess.run(
        [sys.executable, '-W', 'error::DeprecationWarning', '-c', code, scenario],
        cwd=ROOT,
        env=base,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope='module')
def https(tmp_path_factory):
    return _probe(
        'https',
        tmp_path_factory.mktemp('https'),
        HUB_BASE_URL='https://hub.itda.work',
        HUB_MCP_URL='https://hub.itda.work/mcp',
        DJANGO_ALLOWED_HOSTS='hub.itda.work,hub-web',
        HUB_LOCAL_LOGIN='1',
    )


def test_https_주소면_프록시_헤더를_신뢰하고_쿠키가_secure(https):
    assert https['settings'] == {
        'HUB_HTTPS': True,
        'SECURE_PROXY_SSL_HEADER': ['HTTP_X_FORWARDED_PROTO', 'https'],
        'SESSION_COOKIE_SECURE': True,
        'CSRF_COOKIE_SECURE': True,
        'CSRF_TRUSTED_ORIGINS': ['https://hub.itda.work'],
    }


def test_프록시가_붙인_X_Forwarded_Proto_로만_https_가_된다(https):
    """Caddy → 컨테이너는 평문 http 다. 헤더를 믿지 않으면 요청에서 만드는 절대 주소가 http 로 샌다."""
    assert https['proxied_is_secure'] is True
    assert https['proxied_absolute'] == 'https://hub.itda.work/accounts/login/'
    assert https['bare_is_secure'] is False, '헤더 없는 직접 요청까지 https 로 치지는 않는다'


def test_프록시_뒤에서_RFC8414_issuer_는_HUB_BASE_URL(https):
    assert https['issuer'] == 'https://hub.itda.work'
    assert https['authorization_endpoint'] == 'https://hub.itda.work/o/authorize/'
    assert https['token_endpoint'] == 'https://hub.itda.work/o/token/'
    assert https['resource'] == 'https://hub.itda.work/mcp'
    assert https['authorization_servers'] == ['https://hub.itda.work']


@pytest.fixture(scope='module')
def google(tmp_path_factory):
    return _probe(
        'google',
        tmp_path_factory.mktemp('google'),
        HUB_BASE_URL='https://hub.itda.work',
        HUB_MCP_URL='https://hub.itda.work/mcp',
        DJANGO_ALLOWED_HOSTS='hub.itda.work,testserver',
        HUB_LOCAL_LOGIN='1',
        GOOGLE_OAUTH_CLIENT_ID='dummy.apps.googleusercontent.com',
        GOOGLE_OAUTH_CLIENT_SECRET='dummy-secret',
    )


def test_구글_자격이_있으면_제공자가_켜지고_콜백_경로가_고정이다(google):
    assert google['google_installed'] is True
    # Google 콘솔에 등록하는 리디렉션 URI 의 경로. 바뀌면 운영 로그인이 전부 깨진다.
    assert google['callback_path'] == '/accounts/google/login/callback/'
    assert google['login_page_has_google'] is True
    assert google['login_page_has_password'] is True, 'HUB_LOCAL_LOGIN=1 이면 비상용으로 병행된다'


def test_구글로_보내는_redirect_uri_가_프록시_뒤에서_https(google):
    assert google['google_redirect_status'] == 302
    location = urlparse(google['google_redirect'])
    assert location.netloc == 'accounts.google.com'
    query = parse_qs(location.query)
    assert query['redirect_uri'] == ['https://hub.itda.work/accounts/google/login/callback/']
    assert query['client_id'] == ['dummy.apps.googleusercontent.com']


def test_운영_env_의_check_deploy_는_0건(https, google):
    """RFC 9700(DOT W001–W008)·HSTS 까지 — 조용히 둔 것은 security.W008(SSL 리디렉트는 Caddy)·W021(preload)뿐."""
    assert https['deploy_check'] == []
    assert google['deploy_check'] == []


def test_HSTS_는_https_로_본_요청에만_붙는다(https):
    assert https['hsts_proxied'] == 'max-age=31536000; includeSubDomains'
    assert https['hsts_bare'] == '', '컨테이너 사이 평문 호출에는 HSTS 가 없다'
    assert https['healthz_bare_status'] in (200, 503), 'SSL 리디렉트(301)로 튀지 않는다'


def test_운영에서는_https_콜백만_등록된다(https):
    """claude.ai·Cowork 콜백(https)은 등록되고, http 루프백은 거부된다(RFC 9700 §2.1)."""
    assert https['redirect_schemes'] == ['https']
    assert https['dcr_https'] == 201
    assert https['dcr_http_loopback'] == 400


def test_구글이_켜지면_로컬_가입만_닫힌다(google):
    """HUB_LOCAL_LOGIN=1 은 이때 '기존 로컬 계정의 로그인' 만 — 새 계정은 Google 로만 생긴다."""
    assert google['local_signup_setting'] is False
    assert google['login_page_has_signup_link'] is False
    assert google['signup_page_has_form'] is False
    assert google['local_signup_created'] is False
    assert google['local_login_status'] == 302
    assert google['local_login_authenticated'] is True
    assert google['google_signup_created'] is True
    assert google['google_signup_status'] == 302
