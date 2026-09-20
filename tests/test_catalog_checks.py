"""운영 DB 를 흉내 내어 배포 점검의 카탈로그 판정을 잰다 (#5).

`test_catalog_adapter_contract.py` 는 **CI 가 심은 시드**가 코드와 맞는지를 본다. 여기서 보는 것은
**그 시점의 DB** 다 — 시드 뒤에 admin 으로 `enabled` 를 켠 운영 DB 가 그 대상이다. 둘은 같은 사건을
다른 자리에서 잡는다. 계약 테스트는 소스가 어긋나는 것을 막고, 이 체크는 DB 가 어긋난 것을 발견한다.

**체크 함수를 import 하지 않고 등록부에서 꺼낸다.** import 가 곧 `@register` 라, 테스트가 모듈을
직접 들여오면 `CatalogConfig.ready()` 의 등록 import 가 빠져도 등록 검사가 통과한다. 관측을
`django.core.checks` 등록부 한 곳으로 모아야 그 회귀가 드러난다.

**어디서 도느냐도 이 체크의 계약이다.** 배포 체크라 `manage.py check --deploy` 에만 실린다.
일반 체크로 등록하면 모든 관리 커맨드의 사전 체크에 실려, 불일치가 생긴 순간 `migrate` 가 죽고
`entrypoint.sh` 의 `set -eu` 때문에 컨테이너가 부팅하지 못한다 — 「기동 경로」 묶음이 그것을 지킨다.
"""

import pytest
from django.core.checks import Error, registry
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.db import DatabaseError

from apps.catalog.models import Tool

이름 = '카탈로그가_코드와_맞는다'


def 등록된():
    """등록부에서 꺼낸다 — 없으면 `CatalogConfig.ready()` 의 import 가 빠진 것이다."""
    for check in registry.registry.get_checks(include_deployment_checks=True):
        if check.__name__ == 이름:
            return check
    raise AssertionError(f'{이름} 가 등록되지 않았다 — CatalogConfig.ready() 를 확인한다')


def 메시지():
    return 등록된()(app_configs=None)


def 판정():
    """메시지 id 만. 판정은 id(채널)로 읽고 문구로 읽지 않는다."""
    return [m.id for m in 메시지()]


# --- 시드 상태: 조용해야 한다 ---------------------------------------------


def test_시드_그대로면_아무_판정도_나오지_않는다(catalog):
    assert 판정() == []


# --- 운영 DB 흉내: 시드 뒤에 DB 가 움직인 경우 -----------------------------


def test_어댑터가_없는_도구를_DB_에서_공개로_켜면_ERROR_다(catalog):
    """운영에서 실제로 일어나는 경로다 — admin 목록의 `list_editable` 로 `enabled` 를 켠다.

    시드는 `fuel` 을 「어댑터 준비 중」이라 비공개로 둔다(`seed_catalog.py`). 소스는 그대로인 채
    **DB 만** 켜지므로 계약 테스트는 초록이다. 그 구멍을 이 체크가 메운다.
    """
    assert 판정() == [], '시드 상태부터 빨갛다면 아래 판정이 무엇을 잡았는지 알 수 없다'

    Tool.objects.filter(slug='fuel').update(enabled=True)

    messages = 메시지()
    assert [m.id for m in messages] == ['catalog.E001']
    assert 'tool:fuel' in messages[0].msg, '어느 도구인지 말하지 않으면 운영자가 고칠 곳을 모른다'
    assert isinstance(messages[0], Error), '경고로 내면 --fail-level WARNING 없이는 배포가 지나간다'


def test_카탈로그_행을_지우면_그_어댑터가_고아로_잡힌다(catalog):
    """`seed_catalog` 는 CATALOG 에 없는 행을 지우지 않지만, 사람은 admin 에서 행을 지울 수 있다."""
    Tool.objects.filter(slug='weather').delete()

    messages = 메시지()
    assert [m.id for m in messages] == ['catalog.E002']
    assert 'tool:weather' in messages[0].msg


def test_카탈로그를_통째로_지워도_잡힌다(catalog):
    """행 0 은 판정 불가가 아니다 — 빈 DB 로 잘못 복원한 상태가 그것이고, 모든 어댑터가 고아다.

    「행이 하나라도 있을 때만 판정」으로 두면 일부 삭제는 잡고 **전체 삭제는 통과하는** 미탐이 된다.
    그 게이트가 필요했던 이유(migrate 직후·시드 전 오탐)는 이 체크가 기동 경로에 실리지 않게 되면서
    사라졌다.
    """
    Tool.objects.all().delete()

    messages = 메시지()
    assert [m.id for m in messages] == ['catalog.E002']
    assert 'tool:kosis' in messages[0].msg and 'tool:weather' in messages[0].msg


def test_공개_도구의_설정_키를_DB_에서_비우면_ERROR_다(catalog):
    """`setting_key` 도 admin 에서 지울 수 있다 — 그 순간 사용자는 넣을 칸의 이름을 모른다."""
    Tool.objects.filter(slug='kosis').update(setting_key='')

    messages = 메시지()
    assert [m.id for m in messages] == ['catalog.E003']
    assert 'kosis' in messages[0].msg


def test_자격증명이_필요해도_비공개면_판정하지_않는다(catalog):
    """공개되지 않은 도구는 도구함에 담기지 않는다 — 준비 중인 행을 빨갛게 만들지 않는다."""
    Tool.objects.filter(slug='kosis').update(setting_key='', enabled=False)

    assert 메시지() == []


# --- 판정할 수 없을 때: 침묵은 둘뿐이다 ------------------------------------


def test_테이블이_없으면_판정하지_않는다(db, monkeypatch):
    """`check` 는 `migrate` 앞에서도 돈다. 그때는 카탈로그 테이블 자체가 없다."""
    from django.db import connection

    monkeypatch.setattr(connection.introspection, 'table_names', lambda *a, **kw: [])
    assert 판정() == []


def test_DB_에_못_붙으면_경고로_드러낸다(db, monkeypatch):
    """접속 실패를 침묵으로 두면 점검이 DB 장애를 초록으로 덮는다.

    SQLite 손상(`file is not a database`)은 PRAGMA 등록 때문에 **접속 단계**에서 난다 — 못 붙은
    것과 구분되지 않는다. 그러니 둘을 가르려 애쓰는 대신 둘 다 보이게 만든다. ERROR 가 아니라
    WARNING 인 것은 「판정하지 못했다」 가 「불일치를 찾았다」 와 다른 사건이기 때문이고,
    배포 절차가 쓰는 `--fail-level WARNING` 이 여기서 멈춘다.

    패치는 `monkeypatch.context()` 로 본문 안에서 되돌린다. pytest-django 의 DB 정리도
    `ensure_connection` 을 지나므로, 픽스처 해체까지 끌고 가면 테스트가 아니라 정리가 깨진다.
    """
    from django.db import connection

    def 터진다(*args, **kwargs):
        raise DatabaseError('could not connect to server')

    with monkeypatch.context() as m:
        m.setattr(connection, 'ensure_connection', 터진다)
        messages = 메시지()

    assert [m.id for m in messages] == ['catalog.W001']
    assert 'could not connect to server' in messages[0].msg, '원인을 지우면 운영자가 볼 곳을 모른다'


def test_붙은_뒤_메타데이터_조회가_깨지면_삼키지_않는다(catalog, monkeypatch):
    """손상된 DB 는 접속까지는 되고 첫 조회에서 `file is not a database` 로 깨진다.

    `table_names()` 는 연결 여부를 묻는 함수가 아니라 `sqlite_master` 에 날리는 SELECT 다. 그
    예외를 삼키면 손상이 「테이블 없음」으로 둔갑해 점검이 초록으로 지나간다.
    """
    from django.db import connection
    from django.db.utils import DatabaseError as DBError

    def 손상(*args, **kwargs):
        raise DBError('file is not a database')

    monkeypatch.setattr(connection.introspection, 'table_names', 손상)
    with pytest.raises(DBError):
        메시지()


def test_붙은_뒤_행_조회가_깨지면_삼키지_않는다(catalog, monkeypatch):
    """`database is locked` 는 SQLite WAL 로 두 프로세스가 같은 파일을 쓰는 이 배포의 실제 오류다."""
    from django.db.utils import OperationalError

    def 잠김(*args, **kwargs):
        raise OperationalError('database is locked')

    monkeypatch.setattr(Tool.objects, 'all', 잠김)
    with pytest.raises(OperationalError):
        메시지()


# --- 기동 경로: 무엇도 막지 않는다 ------------------------------------------


def test_불일치_상태에서도_복구_커맨드가_막히지_않는다(catalog):
    """일반 체크로 등록했을 때의 실제 사고를 고정한다.

    `BaseCommand.execute` 는 `handle()` 앞에서 시스템 체크를 돌린다. 일반 체크였다면 불일치가 생긴
    순간 `seed_catalog` 가 종료코드 1 을 내 **복구 수단 자체가 막힌다** — 이 체크의 hint 가 권하는
    바로 그 커맨드다. `migrate` 도 같이 죽고, `entrypoint.sh` 는 `set -eu` 라 컨테이너가 부팅하지
    못한다. `skip_checks=False` 로 CLI 와 같은 조건을 만든다.
    """
    Tool.objects.filter(slug='fuel').update(enabled=True)

    call_command('seed_catalog', verbosity=0, skip_checks=False)

    assert Tool.objects.get(slug='fuel').enabled is False, '시드가 불일치를 되돌리지 못했다'


def test_deploy_없는_check_는_판정하지_않는다(catalog):
    """관리 커맨드의 사전 체크와 같은 조건이다(`include_deployment_checks=False`).

    `just check` 의 `manage.py check --fail-level WARNING` 이 기존 그대로 통과한다는 뜻이기도 하다.
    """
    Tool.objects.filter(slug='fuel').update(enabled=True)

    call_command('check', fail_level='WARNING')


def test_W001_은_fail_level_WARNING_에서만_배포를_멈춘다(catalog, monkeypatch):
    """경고 등급을 고른 대가가 정확히 무엇인지 고정한다.

    `check --deploy` 만 돌리면 W001 을 찍고 **종료코드 0** 이다 — 배포 절차가 `--fail-level
    WARNING` 을 쓰기 때문에 성립하는 선택이라, 그 한 글자가 빠지면 장애가 조용히 지나간다.
    `docs/deploy.md` 의 두 자리가 그 플래그를 달고 있다.
    """
    from django.db import connection

    def 터진다(*args, **kwargs):
        raise DatabaseError('could not connect to server')

    with monkeypatch.context() as m:
        m.setattr(connection, 'ensure_connection', 터진다)
        assert [msg.id for msg in 메시지()] == ['catalog.W001']

        call_command('check', deploy=True)  # 임계값 없음 — 찍기만 하고 통과한다

        with pytest.raises(SystemCheckError, match='catalog.W001'):
            call_command('check', deploy=True, fail_level='WARNING')


def test_deploy_점검은_판정한다(catalog):
    """함수를 직접 부르는 것과 커맨드가 그것을 돌리는 것은 다르다 — 등록까지 지난 경로를 한 번 잰다."""
    call_command('check', deploy=True)  # 시드 상태 — 통과한다

    Tool.objects.filter(slug='fuel').update(enabled=True)
    with pytest.raises(SystemCheckError, match='catalog.E001'):
        call_command('check', deploy=True)
