"""카탈로그↔어댑터↔인가 서버의 대응 — 한쪽만 고치면 여기서 막힌다 (#2).

같은 것을 세 곳이 선언한다.

- **카탈로그** (`apps/catalog`) — 도구 행 하나와 그 스코프 `tool:<slug>`. 공개(`enabled=True`)만 세상에 뜬다.
- **어댑터** (`mcp_server/tools`) — `@hub_tool(slug)` 이 붙인 spec. 스코프 문자열만 들고 slug 는 따로 없다.
- **인가 서버** (`apps/oauth`) — DOT 스코프 백엔드와 두 발견 문서.

어긋나면 사용자가 겪는 것은 둘 중 하나다. 카탈로그만 공개면 동의 화면에 스코프가 뜨고 토큰에도 실리는데
`tools/list` 에 도구가 없다 — "허용했는데 도구가 안 보인다". 어댑터만 있으면 스코프가 정의되지 않아
아무도 부를 수 없는 죽은 코드다. 어느 쪽도 화면·로그에 나타나지 않는다.

**slug 를 스코프에서 되뽑지 않는다 — 스코프 원문끼리 비교한다.** `scope.split(':', 1)[1]` 로 뽑으면
`other:weather` 도 weather 로 인정돼 접두 오류가 통과한다.

이 파일이 **보장하지 않는 것**: 어댑터가 올바른 상류를 부르는지, 결과가 쓸모 있는지, 그리고 이미 발급된
토큰이 비공개 전환 때 회수되는지(`apps/toolbox/tokens.py` 의 `sync_scope` 는 도구함 변경 경로에만 있다).
여기서 보는 것은 **CI 가 심은 시드**다 — 운영 DB 는 admin 수정으로 달라질 수 있고, 그쪽은 #5 의 몫이다.
"""

import asyncio

import httpx
import pytest
from django.test import RequestFactory
from fastmcp.exceptions import AuthorizationError, NotFoundError
from oauth2_provider.models import get_application_model
from oauth2_provider.scopes import get_scopes_backend

from apps.catalog.models import Tool
from apps.toolbox.models import ToolboxEntry, ToolSetting, granted_scopes
from mcp_server.tools import specs, toolset

DISCOVERY_URLS = (
    '/.well-known/oauth-authorization-server',
    '/.well-known/oauth-protected-resource/mcp',
)


def public_scopes():
    return {t.scope for t in Tool.objects.filter(enabled=True)}


def catalog_scopes():
    return {t.scope for t in Tool.objects.all()}


def adapter_scopes():
    return {s.scope for s in specs()}


# --- 축 1·2: 양방향 대응 -------------------------------------------------


def test_공개된_도구는_전부_어댑터가_있다(catalog):
    """스코프에는 실리고 호출은 안 되는 도구를 만들지 않는다."""
    빠진 = public_scopes() - adapter_scopes()
    assert not 빠진, (
        f'카탈로그에 공개됐는데 어댑터가 없다: {sorted(빠진)} — '
        '동의 화면과 토큰에는 실리지만 tools/list 에는 나타나지 않는다. '
        'mcp_server/tools 에 @hub_tool 을 더하거나 seed_catalog.py 에서 enabled=False 로 둔다'
    )


def test_어댑터가_있는_도구는_카탈로그에_있다(catalog):
    """카탈로그 행이 없으면 스코프가 정의되지 않아 아무도 그 도구를 부를 수 없다."""
    고아 = adapter_scopes() - catalog_scopes()
    assert not 고아, (
        f'어댑터만 있고 카탈로그 행이 없다: {sorted(고아)} — '
        'seed_catalog.py 의 CATALOG 에 행을 더한다(어댑터가 아직이면 enabled=False)'
    )


def test_스코프는_slug_에서_기계적으로_나온다(catalog):
    """`tool:<slug>` 는 토큰에 실려 나가는 와이어 포맷이다. 규약을 손으로 두 번 쓰지 않는다."""
    for tool in Tool.objects.all():
        assert tool.scope == f'tool:{tool.slug}'


# --- 유일성 ---------------------------------------------------------------


def test_도구_선언은_이름도_스코프도_겹치지_않는다():
    """`_SPECS` 는 리스트다 — 집합·dict 로 바꾸는 순간 중복이 조용히 사라진다."""
    names = [s.name for s in specs()]
    scopes = [s.scope for s in specs()]
    assert len(names) == len(set(names)), f'도구 이름이 겹친다: {sorted(names)}'
    assert len(scopes) == len(set(scopes)), (
        f'스코프가 겹친다(카탈로그 slug 하나에 도구 하나): {sorted(scopes)}'
    )


# --- 실제 등록: 선언 → Toolset → MCP -------------------------------------


def test_선언된_도구는_Toolset_에_등록돼_있다():
    """기대는 허브의 spec 에서, 관측은 django-itda 의 등록부에서 — 두 저장소 사이의 계약이다."""
    assert {s.name for s in specs()} == {s.name for s in toolset.specs()}
    for spec in specs():
        toolset.get(spec.name)  # 없으면 KeyError


def test_각_도구는_자기_스코프_토큰에만_보인다(hub_env, with_token):
    """이름 집합만 비교하면 「kosis 가 weather 스코프까지 요구한다」 같은 오배선을 놓친다."""
    from mcp_server.server import build

    mcp = build()
    for spec in specs():
        with_token([spec.scope])
        보이는 = [t.name for t in asyncio.run(mcp.list_tools())]
        assert 보이는 == [spec.name], f'{spec.scope} 만 든 토큰에 {보이는} 가 보인다'


def test_인증됐지만_빈_스코프면_도구가_없다(hub_env, with_token):
    """빈 도구함(인증됨)과 토큰 없음(미인증)은 다른 조건이다 — 둘 다 아무것도 보이지 않아야 한다."""
    from mcp_server.server import build

    mcp = build()
    with_token([])
    assert asyncio.run(mcp.list_tools()) == []


# --- 실제 호출: 등록된 이름이 어댑터까지 닿는가 ---------------------------


@pytest.mark.django_db(transaction=True)
def test_등록된_도구를_실제로_부르면_어댑터_결과와_궤적이_남는다(
    hub_env, with_token, upstream, django_user_model
):
    """이름이 맞다는 것과 그 이름으로 부를 수 있다는 것은 다르다.

    **인증 컨텍스트를 주입한 프로세스 내부 통합 호출**이다 — introspection·bearer 검증·HTTP 전송은
    지나지 않는다(`with_token`). 그 뒤로는 대역이 없다: MCP 등록 도구 → `_actor` 의 사용자 조회 →
    `Toolset.call` → `resolve` 와 복호화 → 어댑터 → 궤적까지 실제로 돌고, 상류 HTTP 하나만 막는다.
    도구함 설정의 사용자 키가 그 어댑터에 닿는지도 여기서 드러난다 — 어댑터가 `resolve` 에 다른 slug 를
    적으면(`mcp_server/tools/__init__.py`) 설정을 마친 사용자가 호출에 실패한다.

    관측 범위는 KOSIS 한 도구다. 모든 spec 의 실제 호출까지 재지는 않는다.
    """
    from django.core.management import call_command
    from django_itda.models import ToolCall

    from mcp_server.server import build

    call_command('seed_catalog', verbosity=0)
    user = django_user_model.objects.create_user(username='alice', email='a@example.com')
    entry = ToolboxEntry.objects.create(user=user, tool=Tool.objects.get(slug='kosis'))
    setting = ToolSetting(entry=entry, key='KOSIS_API_KEY')
    setting.set_value('user-key')
    setting.save()

    본_키 = []

    def handler(request):
        본_키.append(request.url.params.get('apiKey'))
        return httpx.Response(
            200,
            json=[{'ORG_ID': '101', 'ORG_NM': '국가데이터처', 'TBL_ID': 'T1', 'TBL_NM': '인구'}],
        )

    upstream(handler)
    mcp = build()
    with_token(['tool:kosis'], username='alice')
    result = asyncio.run(mcp.call_tool('kosis_search', {'keyword': '인구', 'count': 3}))

    assert 본_키 == ['user-key'], '도구함에 저장한 사용자 키가 어댑터까지 닿지 않았다'
    assert result.structured_content['ok'] is True
    assert result.structured_content['tables'][0]['tbl_id'] == 'T1'
    row = ToolCall.objects.filter(tool='kosis_search').order_by('-id').first()
    assert row is not None, 'MCP 를 지난 호출이 궤적에 남지 않았다'
    assert row.actor_id == user.pk


@pytest.mark.django_db(transaction=True)
def test_스코프가_없으면_어댑터에_닿지_않는다(hub_env, with_token, upstream, django_user_model):
    """가시성만이 아니라 호출도 막힌다 — 목록에서 감추기만 하면 이름을 아는 클라이언트가 부른다."""
    from django.core.management import call_command

    from mcp_server.server import build

    call_command('seed_catalog', verbosity=0)
    django_user_model.objects.create_user(username='alice', email='a@example.com')

    닿음 = []
    upstream(lambda request: 닿음.append(request.url) or httpx.Response(200, json=[]))
    mcp = build()
    with_token(['tool:weather'], username='alice')
    # fastmcp 는 권한 없는 도구를 아예 없는 것으로 답한다(`NotFoundError`). 거부 방식보다 중요한 것은
    # 어댑터에 닿지 않았다는 사실이라, 인가 실패의 두 갈래를 모두 받는다.
    with pytest.raises((NotFoundError, AuthorizationError)):
        asyncio.run(mcp.call_tool('kosis_search', {'keyword': '인구'}))
    assert 닿음 == [], 'kosis 스코프 없이도 상류까지 갔다'


# --- DOT 스코프 백엔드·발견 문서 -----------------------------------------


def assert_scopes_are(client, expected, where, **caller):
    """인가 서버가 밖으로 내는 스코프가 전부 `expected` 와 같은지.

    한 자리만 보면 나머지가 상수로 굳은 회귀를 놓친다 — `all`·`available`·`default` 와 두 발견 문서를
    **매번 전체 집합으로** 비교한다. `caller` 는 백엔드에 넘기는 `application`·`request` 다.
    """
    backend = get_scopes_backend()
    assert set(backend.get_all_scopes()) == expected, f'{where}: get_all_scopes'
    assert set(backend.get_available_scopes(**caller)) == expected, f'{where}: get_available_scopes'
    assert set(backend.get_default_scopes(**caller)) == expected, (
        f'{where}: get_default_scopes — 기본 스코프가 곧 Claude 가 받는 상한이다'
    )
    for url in DISCOVERY_URLS:
        assert set(client.get(url).json()['scopes_supported']) == expected, f'{where}: {url}'


def test_설정된_스코프_백엔드와_발견_문서가_공개_카탈로그와_같다(catalog, client):
    """기대값은 카탈로그 행에서 직접 만든다.

    `scope_choices()` 로 기대값을 만들면 `enabled` 필터 오류가 양쪽에서 함께 통과한다. 관측도
    `CatalogScopes()` 를 손으로 만들지 않고 **설정이 고른 백엔드**에서 얻는다(`hub/settings.py` 의
    `SCOPES_BACKEND_CLASS`) — 그래야 설정이 다른 클래스를 가리키는 회귀가 드러난다.
    설명 문구는 이 계약에 묶지 않는다. `all` 은 키만 본다.
    """
    assert_scopes_are(client, public_scopes(), '시드 상태')


def test_카탈로그_행을_더하고_감추면_백엔드와_발견_문서가_따라온다(catalog, client):
    """시드만 보면 두 스코프를 **상수로** 돌려주는 백엔드도 통과한다 — 행을 움직여 본다.

    probe 의 포함 여부만 보면 기존 공개 스코프가 함께 사라지는 경우를 놓치므로, 움직인 뒤에도 매번
    전체 집합을 비교한다.
    """
    probe = Tool.objects.create(
        slug='probe',
        name='탐침',
        description='이 테스트에서만 산다',
        provider='테스트',
        order=900,
        enabled=True,
    )
    assert 'tool:probe' in public_scopes(), '탐침 행이 공개로 서지 않았다'
    assert_scopes_are(client, public_scopes(), '공개 행을 더한 뒤')

    probe.enabled = False
    probe.save()
    assert 'tool:probe' not in public_scopes()
    assert_scopes_are(client, public_scopes(), '그 행을 감춘 뒤')


def test_스코프_백엔드는_사용자_도구함으로_좁혀지지_않는다(catalog, client, user):
    """좁히는 일은 인가 뷰의 몫이다(`apps/oauth/views.py`).

    백엔드가 요청을 보고 좁히면 Claude 가 메타데이터에 광고된 전체 스코프를 요청할 때 `invalid_scope`
    로 거절되고, 사용자 세션이 없는 토큰 엔드포인트에서도 검증이 깨진다.

    인자 없이 부르는 검사만으로는 요청 의존 필터를 잡지 못한다. DOT 는 검증과 기본 범위 계산에서
    **`application` 과 `request` 를 함께** 넘기므로(`oauth2_provider/oauth2_validators.py`), 여기서도
    실제 Application 을 만들어 **같은 `application`·`user`·`client` 속성으로 직접 호출한다** —
    도구함이 빈 사용자와 일부만 담은 사용자 둘 다.

    OAuthlib 의 `Request` 나 DOT validator 를 지나지는 않는다. 그 속성들을 읽는 회귀는 잡지만
    `grant_type`·사용자 없는 토큰 단계까지 입증하지는 않는다.
    """
    Application = get_application_model()
    application = Application.objects.create(
        name='claude-test',
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris='https://claude.ai/api/mcp/auth_callback',
        client_secret='',
    )

    def 요청():
        request = RequestFactory().get('/o/authorize/')
        request.user = user
        request.client = application
        return request

    공개 = public_scopes()
    assert_scopes_are(client, 공개, '빈 도구함', application=application, request=요청())
    ToolboxEntry.objects.create(user=user, tool=catalog['weather'])
    assert_scopes_are(client, 공개, '일부만 담은 도구함', application=application, request=요청())


# --- 비공개 전환: 필터가 실제로 도는가 -------------------------------------


def test_공개된_도구를_비공개로_돌리면_스코프에서_빠진다(catalog, user):
    """`granted_scopes` 의 `tool__enabled=True` 필터가 사라지는 회귀를 잡는다.

    변경 **전** 포함까지 봐야 한다 — 부재만 확인하면 처음부터 아무 스코프도 돌려주지 않는 구현도 통과한다.
    항목은 남고 스코프만 빠지는 것이 이 필터의 뜻이다.

    이 테스트는 「비공개 도구가 **이미 발급된** 토큰에서도 사라진다」 를 뜻하지 않는다. admin 의
    `enabled` 수정은 `tokens.sync_scope()` 를 부르지 않고(`apps/catalog/admin.py`), 동기화는 도구함
    변경 경로에만 있다. 기존 토큰 회수는 별도 과제다.
    """
    weather = catalog['weather']
    ToolboxEntry.objects.create(user=user, tool=weather)
    assert granted_scopes(user) == ['tool:weather']

    weather.enabled = False
    weather.save()

    assert granted_scopes(user) == []
    assert ToolboxEntry.objects.filter(user=user, tool=weather).exists(), (
        '도구함 항목까지 지워지면 공개를 되돌렸을 때 사용자가 다시 담아야 한다'
    )


# --- 자격증명 선언 ---------------------------------------------------------


def test_자격증명이_필요한_공개_도구는_설정_키를_선언한다(catalog):
    """`setting_key` 가 비면 사용자는 넣을 칸의 이름을 모르고, 공용 키 환경변수 이름도 만들 수 없다."""
    for tool in Tool.objects.filter(enabled=True).exclude(credential=Tool.Credential.NONE):
        assert tool.setting_key.strip(), f'{tool.slug} 가 자격증명을 요구하면서 설정 키가 비었다'
