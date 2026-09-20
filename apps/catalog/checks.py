"""지금 이 DB 와 지금 이 코드가 어긋났는지 — 배포 점검이 본다 (#5).

`tests/test_catalog_adapter_contract.py` 는 **CI 가 심은 시드**를 본다. 운영 DB 는 그것과 다를 수
있다 — admin 목록에서 `enabled` 를 바로 켤 수 있고(`apps/catalog/admin.py` 의 `list_editable`),
`seed_catalog` 는 멱등이지만 CATALOG 에 없는 기존 행을 지우지 않는다. 그래서 CI 가 초록인 채로
운영에는 「공개됐는데 어댑터가 없는 도구」가 있을 수 있다. 증상은 #2 와 같다 — 동의 화면에 스코프가
뜨고 토큰에도 실리는데 `tools/list` 에 도구가 없다.

**배포 체크(`deploy=True`)로 등록한다 — 판정하는 자리는 `manage.py check --deploy` 하나다.**
일반 체크로 등록하면 `BaseCommand.execute` 가 모든 관리 커맨드 앞에서 돌린다. 그러면 이 체크가
잡으려던 바로 그 상태(admin 이 도구를 켠 운영 DB)에서 `migrate` 가 종료코드 1 을 내고,
`deploy/entrypoint.sh` 는 `set -eu` 라 **hub-web 이 부팅하지 못한다**. 복구 수단인 `seed_catalog`
와 `backup_db` 까지 같이 막힌다. 배포 체크는 `check --deploy` 에만 실려 그 경로가 없다.

**판정 하나에 함수 하나다.** 세 판정이 같은 행 목록을 보므로 나누면 DB 왕복이 갑절이 되고, 읽지
못했을 때의 경고가 두 번 난다.

판정 문구는 계약 테스트와 **같은 말**을 쓴다. 같은 사건을 두 곳이 다른 말로 부르면 운영자가 둘을
같은 것으로 읽지 못한다. 다른 것은 hint 뿐이다 — 테스트는 소스를 고치라 하고, 여기서는 DB 를 본다.
"""

from django.core.checks import Error, Warning, register
from django.db import DatabaseError, connection


class 읽지못함(Exception):
    """카탈로그를 읽지 못했다. `.이유` 는 사람에게 보일 원인."""

    def __init__(self, 이유):
        super().__init__(이유)
        self.이유 = 이유


def _rows():
    """판정에 쓸 카탈로그 행.

    **조용히 건너뛰는 것은 「붙었는데 테이블이 없다」 하나뿐이다.** `check` 는 `migrate` 앞에서도
    도니 마이그레이션 전은 정상이고, 그때는 판정할 근거가 없다.

    나머지는 전부 드러낸다. 접속 실패는 `읽지못함` 으로 올려 `catalog.W001` 이 되고, 붙은 뒤의
    조회 실패(`database is locked` — SQLite WAL 로 두 프로세스가 같은 파일을 쓴다)는 그대로
    터진다. **접속 단계와 조회 단계를 가르는 이유**: `table_names()` 는 연결 여부를 묻는 함수가
    아니라 `sqlite_master` 에 SELECT 를 날리는 조회라(`django/db/backends/sqlite3/introspection.py`)
    그 예외를 삼키면 손상이 「테이블 없음」으로 둔갑한다.

    SQLite 손상(`file is not a database`)이 **새 연결의 초기 PRAGMA** 에서 드러나면 접속 실패와
    구분되지 않는다. 그래서 접속 실패를 침묵이 아니라 경고로 낸다 — 붙은 뒤에 드러나는 손상은 위
    규칙대로 터진다. 배포 직전 점검이 DB 장애를 초록으로 덮는 것이 가장 나쁘다.

    **행이 0 인 것은 판정 불가가 아니다.** 카탈로그를 통째로 지웠거나 빈 DB 로 잘못 복원한 상태가
    그것이고, 그때 모든 어댑터가 고아라는 판정은 참이다. 기동 경로에는 이 체크가 실리지 않으므로
    (`deploy=True`) 「migrate 직후·시드 전」을 오탐으로 걱정할 자리가 없다.
    """
    from apps.catalog.models import Tool

    try:
        connection.ensure_connection()
    except DatabaseError as exc:
        raise 읽지못함(f'{type(exc).__name__}: {exc}') from exc
    if Tool._meta.db_table not in connection.introspection.table_names():
        return None
    return list(Tool.objects.all())


@register(deploy=True)
def 카탈로그가_코드와_맞는다(app_configs, **kwargs):
    from apps.catalog.models import Tool

    try:
        rows = _rows()
    except 읽지못함 as exc:
        return [
            Warning(
                f'카탈로그를 읽지 못해 판정을 건너뛴다 — {exc.이유}',
                hint='DB 에 못 붙었거나 파일이 손상됐다. 점검이 통과한 것이 아니다. '
                '`--fail-level WARNING` 으로 돌리면 여기서 멈춘다.',
                id='catalog.W001',
            )
        ]
    if rows is None:
        return []  # 붙었지만 테이블이 없다 — 마이그레이션 전

    # 스코프 원문끼리 비교한다. `scope.split(':', 1)[1]` 로 slug 를 되뽑으면 `other:weather` 도
    # weather 로 인정돼 접두 오류가 통과한다 — 계약 테스트와 같은 규율이다.
    from mcp_server.tools import specs  # 등록부를 읽을 뿐, Django 안에 MCP 를 호스팅하지 않는다

    공개 = {t.scope for t in rows if t.enabled}
    전체 = {t.scope for t in rows}
    어댑터 = {s.scope for s in specs()}

    errors = []
    빠진 = 공개 - 어댑터
    if 빠진:
        errors.append(
            Error(
                f'카탈로그에 공개됐는데 어댑터가 없다: {sorted(빠진)} — '
                '동의 화면과 토큰에는 실리지만 tools/list 에는 나타나지 않는다.',
                hint='이 DB 의 판정이다. admin 에서 켠 행이면 되돌리고, 정말 공개할 것이면 '
                'mcp_server/tools 에 @hub_tool 을 더한다.',
                id='catalog.E001',
            )
        )

    고아 = 어댑터 - 전체
    if 고아:
        errors.append(
            Error(
                f'어댑터만 있고 카탈로그 행이 없다: {sorted(고아)} — '
                '스코프가 정의되지 않아 아무도 그 도구를 부를 수 없다.',
                hint='이 DB 의 판정이다. 이 DB 에서 `manage.py seed_catalog` 를 돌린다 '
                '(카탈로그가 통째로 비었다면 복원이 덜 됐는지 먼저 본다).',
                id='catalog.E002',
            )
        )

    # 설정 키가 비면 사용자는 넣을 칸의 이름을 모르고, 공용 키 환경변수 이름도 만들 수 없다.
    errors.extend(
        Error(
            f'{tool.slug} 가 자격증명을 요구하면서 설정 키가 비었다.',
            hint='이 DB 의 판정이다. admin 에서 설정 키를 채우거나 그 도구를 비공개로 돌린다.',
            id='catalog.E003',
        )
        for tool in rows
        if tool.enabled and tool.credential != Tool.Credential.NONE and not tool.setting_key.strip()
    )
    return errors
