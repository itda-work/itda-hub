"""SQLite 온라인 백업 — 운영 VM 의 cron(03:30)이 부른다(compose.prod.yml 의 `hub-backup`).

파일 복사가 아니라 sqlite3 백업 API 로 뜬다. web·mcp 가 WAL 로 쓰는 중에도 일관된 사본이 나오고,
쓰기를 오래 막지 않는다. 임시 이름으로 뜬 뒤 `integrity_check` 가 ok 일 때만 제 이름으로 옮긴다 —
깨진 사본이 최신 백업 자리를 차지하지 않는다. 보관 기한이 지난 `hub-*.sqlite3` 만 지운다.

출력은 사본 경로·크기·지운 개수뿐이다(DB 내용·비밀 없음). 실패는 CommandError → 종료 코드 1.
"""

import sqlite3
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

PREFIX = 'hub-'
SUFFIX = '.sqlite3'


class Command(BaseCommand):
    help = 'SQLite DB 를 온라인 백업해 --dest 에 hub-<시각>.sqlite3 로 남기고 오래된 사본을 지운다'

    def add_arguments(self, parser):
        parser.add_argument('--dest', default='/backups', help='사본을 둘 디렉터리(기본 /backups)')
        parser.add_argument(
            '--keep-days', type=int, default=14, help='이보다 오래된 사본은 지운다(0 = 지우지 않음)'
        )

    def handle(self, *args, dest, keep_days, **options):
        if connection.vendor != 'sqlite':
            raise CommandError(f'SQLite 만 지원한다 — 현재 {connection.vendor}')
        if connection.in_atomic_block:
            # 열린 트랜잭션이 원본을 잠그면 sqlite3 백업 API 는 풀릴 때까지 무한히 재시도한다.
            raise CommandError('트랜잭션 안에서는 백업하지 않는다 — autocommit 연결에서 부른다')
        dest_dir = Path(dest)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CommandError(f'백업 디렉터리를 만들 수 없다: {dest_dir} ({exc})') from None

        stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')  # TIME_ZONE(서울) 기준
        target = dest_dir / f'{PREFIX}{stamp}{SUFFIX}'
        partial = dest_dir / f'.{target.name}.partial'
        connection.ensure_connection()
        try:
            with sqlite3.connect(partial) as copy:
                connection.connection.backup(copy)
                verdict = copy.execute('PRAGMA integrity_check').fetchone()[0]
            copy.close()
            if verdict != 'ok':
                raise CommandError(f'사본 무결성 검사 실패: {verdict}')
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)

        removed = self._prune(dest_dir, keep_days, keep=target)
        self.stdout.write(
            f'백업 완료: {target} ({target.stat().st_size} bytes) · 보관 {keep_days}일 · 삭제 {removed}개'
        )

    def _prune(self, dest_dir: Path, keep_days: int, keep: Path) -> int:
        if keep_days <= 0:
            return 0
        cutoff = time.time() - keep_days * 86400
        removed = 0
        for path in dest_dir.glob(f'{PREFIX}*{SUFFIX}'):
            if path != keep and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        return removed
