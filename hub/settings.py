"""잇다 허브 설정. 값은 환경변수에서 온다(.env.example 참고). 비밀은 여기 없다."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

from hub.env import load as _load_env

_load_env(BASE_DIR / '.env')


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f'환경변수 {name} 이 비어 있다 — .env.example 을 보라')
    return value


def env_bool(name, default=False):
    return str(env(name, '1' if default else '0')).lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [v.strip() for v in str(env(name, default)).split(',') if v.strip()]


SECRET_KEY = env('DJANGO_SECRET_KEY', required=True)
DEBUG = env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')

# 허브 공개 주소 — OAuth 발급자와 보호 리소스 URL 의 뿌리. 바꾸면 모든 커넥터가 재연결된다.
HUB_BASE_URL = env('HUB_BASE_URL', 'http://localhost:8000').rstrip('/')
HUB_MCP_URL = env('HUB_MCP_URL', 'http://localhost:8080/mcp').rstrip('/')
# 공개 주소가 https 면 쿠키·프록시 헤더도 https 전제. 로컬 compose(http://localhost)는 이 축이 꺼진다.
HUB_HTTPS = HUB_BASE_URL.startswith('https://')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS', HUB_BASE_URL)
HUB_SETTINGS_ENCRYPTION_KEY = env('HUB_SETTINGS_ENCRYPTION_KEY', '')
# MCP 프로세스가 토큰을 검증하러 부르는 introspection 주소. compose 안에서는 공개 주소 대신 서비스 이름(hub-web)으로 간다.
HUB_INTROSPECTION_URL = env('HUB_INTROSPECTION_URL', f'{HUB_BASE_URL}/o/introspect/')
# 그 호출의 리소스 서버 client_id — bootstrap 이 같은 값으로 Application 을 만들고 healthz 가 그 존재를 본다.
HUB_INTROSPECTION_CLIENT_ID = env('HUB_INTROSPECTION_CLIENT_ID', '').strip()

# --- 사람 → 허브 로그인 수단 ---
# Google 은 자격이 있을 때만 켜진다. 로컬(compose·개발)은 이메일+비밀번호(HUB_LOCAL_LOGIN, 기본값 = DEBUG).
GOOGLE_OAUTH_CLIENT_ID = env('GOOGLE_OAUTH_CLIENT_ID', '')
HUB_LOCAL_LOGIN = env_bool('HUB_LOCAL_LOGIN', DEBUG)
if not GOOGLE_OAUTH_CLIENT_ID and not HUB_LOCAL_LOGIN:
    raise RuntimeError(
        '로그인 수단이 없다 — GOOGLE_OAUTH_CLIENT_ID 를 두거나 HUB_LOCAL_LOGIN=1 로 켜라(.env.example 참고)'
    )
# 가입 정책: Google 이 켜지면 새 계정은 Google 로만. 그때 HUB_LOCAL_LOGIN 은 기존 로컬 계정(비상용 관리자)의 로그인만.
HUB_LOCAL_SIGNUP = HUB_LOCAL_LOGIN and not GOOGLE_OAUTH_CLIENT_ID

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # 사람 → 허브
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    # Claude → 허브 (인가 서버)
    'oauth2_provider',
    # 판정·궤적
    'django_itda',
    # 허브
    'apps.accounts',
    'apps.catalog',
    'apps.toolbox',
    'apps.oauth',
    'apps.trajectory',
]
if GOOGLE_OAUTH_CLIENT_ID:
    INSTALLED_APPS.append('allauth.socialaccount.providers.google')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_itda.middleware.CallContextMiddleware',
]

ROOT_URLCONF = 'hub.urls'
WSGI_APPLICATION = 'hub.wsgi.application'
ASGI_APPLICATION = 'hub.asgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.accounts.context_processors.signup',
            ],
        },
    },
]


def _database(url: str) -> dict:
    """DATABASE_URL 최소 해석 — sqlite 만 v1 에서 지원한다. 그 밖은 명시 에러."""
    if url.startswith('sqlite:///'):
        path = url[len('sqlite:///') :]
        name = path if path.startswith('/') else str(BASE_DIR / path)
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': name,
            'OPTIONS': {
                # WAL: 읽기와 쓰기가 서로 막지 않는다. web 과 mcp 두 프로세스가 같은 파일을 쓰므로 기본값이다.
                # journal_mode 는 파일에 영속되지만 연결마다 다시 걸어도 무해하다. 로컬 파일시스템 전제(NFS 금지).
                'init_command': (
                    'PRAGMA journal_mode=WAL;PRAGMA synchronous=NORMAL;PRAGMA temp_store=MEMORY;'
                ),
                # 쓰기 트랜잭션을 시작부터 잠가 "database is locked" 를 timeout(=sqlite busy_timeout, 20초) 안에서 해소한다(Django 5.1+).
                'transaction_mode': 'IMMEDIATE',
                'timeout': 20,
            },
        }
    raise RuntimeError(f'지원하지 않는 DATABASE_URL: {url!r} — v1 은 sqlite 만 받는다')


DATABASES = {'default': _database(env('DATABASE_URL', 'sqlite:///db.sqlite3'))}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# 화면 자산(static/css/hub.css 는 just css 산출물, static/js·img). static/src 는 Tailwind 입력이라 싣지 않아도 무해하다.
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # 매니페스트 저장소는 collectstatic 이 전제라 운영에서만. 개발·테스트는 단순 저장소.
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
        if DEBUG
        else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    },
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SITE_ID = 1
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = 'toolbox:home'
ACCOUNT_LOGOUT_REDIRECT_URL = 'account_login'

# --- 사람 → 허브: 운영은 Google, 로컬은 이메일+비밀번호. 제공자는 이후 추가한다. ---
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*'] if HUB_LOCAL_LOGIN else ['email*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_ONLY = not HUB_LOCAL_LOGIN
# 가입 여닫기는 어댑터가 HUB_LOCAL_SIGNUP 으로 판정한다(로컬 가입만 닫고 Google 가입은 연다).
ACCOUNT_ADAPTER = 'apps.accounts.adapters.AccountAdapter'
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.SocialAccountAdapter'
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_PROVIDERS = (
    {
        'google': {
            'APP': {
                'client_id': GOOGLE_OAUTH_CLIENT_ID,
                'secret': env('GOOGLE_OAUTH_CLIENT_SECRET', ''),
                'key': '',
            },
            'SCOPE': ['profile', 'email'],
            'AUTH_PARAMS': {'access_type': 'online'},
            'OAUTH_PKCE_ENABLED': True,
        }
    }
    if GOOGLE_OAUTH_CLIENT_ID
    else {}
)

# --- Claude → 허브: django-oauth-toolkit 3.4 을 MCP 인가 서버로 ---
OAUTH2_PROVIDER = {
    'SCOPES_BACKEND_CLASS': 'apps.oauth.scopes.CatalogScopes',
    'PKCE_REQUIRED': True,
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 60 * 60 * 24 * 30,
    'ROTATE_REFRESH_TOKEN': True,
    # RFC 8414 발급자 — HUB_BASE_URL 그대로. 메타데이터는 루트 /.well-known/oauth-authorization-server 에 게시된다.
    'OIDC_ISS_ENDPOINT': HUB_BASE_URL,
    # RFC 9728 보호 리소스 — MCP 엔드포인트. /.well-known/oauth-protected-resource/mcp 에 게시된다.
    'OAUTH2_PROTECTED_RESOURCE_IDENTIFIER': HUB_MCP_URL,
    'OAUTH2_PROTECTED_RESOURCE_AUTHORIZATION_SERVERS': [HUB_BASE_URL],
    'OAUTH2_PROTECTED_RESOURCE_NAME': '잇다 허브',
    # Claude 의 공개 신원(CIMD)은 토큰 엔드포인트에 public client 로 오므로 'none' 을 광고해야 선택된다.
    'OAUTH2_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED': [
        'none',
        'client_secret_post',
        'client_secret_basic',
    ],
    'CIMD_ENABLED': True,
    'CIMD_REGISTRATION_PERMISSION_CLASSES': ('oauth2_provider.cimd.HostAllowlistCIMDPermission',),
    'CIMD_ALLOWED_HOSTS': ['claude.ai', '.claude.ai'],
    # DCR 은 CIMD 폴백. 연결마다 클라이언트가 쌓이므로 CIMD 가 우선이다.
    'DCR_ENABLED': True,
    'DCR_REGISTRATION_PERMISSION_CLASSES': ('oauth2_provider.dcr.AllowAllDCRPermission',),
    # RFC 9700: 토큰 원문은 저장하지 않고 체크섬만 둔다. DB·admin 에서 쓸 수 있는 토큰이 보이지 않는다.
    # introspection·검증은 체크섬으로 찾으므로 동작이 같다. 연결 토큰(apps.toolbox.tokens)도 같은 저장소다.
    'COMPLIANT_BCP_RFC9700_TOKEN_STORAGE': True,
    # --- RFC 9700 나머지(DOT 4.0 에서 기본값이 된다). 커스텀 커넥터는 code + PKCE S256 + https 콜백만 쓴다. ---
    # implicit·password grant 거부 — 메타데이터 grant_types_supported 에서도 빠진다.
    'COMPLIANT_BCP_RFC9700_IMPLICIT_GRANT': True,
    'COMPLIANT_BCP_RFC9700_PASSWORD_GRANT': True,
    # PKCE plain 거부(S256 만). 메타데이터 code_challenge_methods_supported 도 S256 만.
    'COMPLIANT_BCP_RFC9700_PKCE_METHOD': True,
    'COMPLIANT_BCP_RFC9700_PKCE_REQUIRED': True,
    # ?access_token= 거부. 토큰은 Authorization 헤더로만(introspection 은 POST 본문이라 무관).
    'COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT': True,
    # RFC 9207 — 인가 응답 리디렉트에 iss(= HUB_BASE_URL)를 싣는다(mix-up 방어).
    'COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS': True,
    # 회전된 refresh 토큰이 다시 쓰이면 그 계열을 통째로 폐기한다. 게이트는 되돌림을 check 에러로 만든다.
    'REFRESH_TOKEN_REUSE_PROTECTION': True,
    'COMPLIANT_BCP_RFC9700_REFRESH_TOKEN': True,
    'COMPLIANT_BCP_RFC9700_REDIRECT_URI_MATCHING': True,
    # 공개(https) 배포에서는 https 콜백만 받는다 — claude.ai·Cowork 콜백은 https://claude.ai/api/mcp/auth_callback.
    # 로컬(http://localhost)은 http 도 받는다. 대가: 운영에서 네이티브 앱의 http 루프백 콜백(RFC 8252)은 등록되지 않는다 —
    # Claude Code 는 OAuth 대신 연결 토큰(Bearer)으로 붙으므로 영향이 없다.
    'ALLOWED_REDIRECT_URI_SCHEMES': ['https'] if HUB_HTTPS else ['http', 'https'],
    'COMPLIANT_BCP_RFC9700_REDIRECT_URI_SCHEME': HUB_HTTPS,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': env('DJANGO_LOG_LEVEL', 'INFO')},
    # httpx 는 INFO 에서 **요청 URL 을 통째로** 찍는다. 도구 어댑터는 인증키를 쿼리스트링으로 보내므로
    # (KOSIS 등) 루트가 INFO 인 채로 두면 성공 호출마다 키가 로그에 남는다 — #4. 상류 호출의 관측은
    # 궤적(ToolCall)이 맡는다. 로그는 경고 이상만 낸다.
    'loggers': {
        'httpx': {'level': 'WARNING'},
        'httpcore': {'level': 'WARNING'},
    },
}

if HUB_HTTPS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS 헤더는 Django 가 낸다(SecurityMiddleware 는 https 요청에만 붙인다 — 프록시 헤더로 판정).
    # includeSubDomains 는 이 호스트 아래(*.hub.itda.work)만 덮는다 — 형제 호스트(itda.work 등)는 무관하다.
    SECURE_HSTS_SECONDS = int(env('HUB_HSTS_SECONDS', str(60 * 60 * 24 * 365)))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # preload 목록은 등록 도메인(itda.work) 단위라 서브도메인 앱이 정할 일이 아니다 → 끄고 security.W021 을 조용히 둔다.
    SECURE_HSTS_PRELOAD = False
    # http → https 리디렉트는 앞단 Caddy 가 한다. Django 에서 켜면 컨테이너 사이 평문 호출(healthcheck,
    # hub-mcp → hub-web introspection)이 전부 301 로 튄다 → 끄고 security.W008 을 조용히 둔다.
    SECURE_SSL_REDIRECT = False
    SILENCED_SYSTEM_CHECKS = ['security.W008', 'security.W021']
