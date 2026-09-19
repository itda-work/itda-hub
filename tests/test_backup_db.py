"""backup_db — 운영 cron 이 부르는 SQLite 온라인 백업. 사본이 열리고, 오래된 사본만 지운다.

테스트 트랜잭션 안에서는 원본이 잠겨 백업 API 가 끝나지 않으므로 transaction=True 로 돈다(운영 연결은 autocommit).
"""

import os
import sqlite3
import time
from io import StringIO

import pytest
from django.core.management import CommandError, call_command


def _run(*args):
    out = StringIO()
    call_command('backup_db', *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_사본이_무결하고_데이터가_들어_있다(user, tmp_path):
    text = _run('--dest', str(tmp_path))
    [copy] = list(tmp_path.glob('hub-*.sqlite3'))
    assert str(copy) in text
    assert not list(tmp_path.glob('.*partial')), '임시 파일이 남지 않는다'
    with sqlite3.connect(copy) as db:
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        emails = [r[0] for r in db.execute('SELECT email FROM auth_user')]
    assert emails == ['alice@example.com']


@pytest.mark.django_db(transaction=True)
def test_보관_기한이_지난_hub_사본만_지운다(tmp_path):
    old = tmp_path / 'hub-20200101-033000.sqlite3'
    other = tmp_path / 'notes-20200101.sqlite3'
    for path in (old, other):
        path.write_bytes(b'')
        stale = time.time() - 30 * 86400
        os.utime(path, (stale, stale))
    text = _run('--dest', str(tmp_path), '--keep-days', '14')
    assert not old.exists() and other.exists()
    assert '삭제 1개' in text
    assert len(list(tmp_path.glob('hub-*.sqlite3'))) == 1


@pytest.mark.django_db(transaction=True)
def test_디렉터리를_만들_수_없으면_명시_에러(tmp_path):
    blocker = tmp_path / 'file'
    blocker.write_text('x')
    with pytest.raises(CommandError, match='백업 디렉터리'):
        _run('--dest', str(blocker / 'sub'))


def test_트랜잭션_안에서는_거부한다(db, tmp_path):
    """테스트 트랜잭션처럼 원본이 잠긴 상태면 백업 API 가 끝나지 않는다 — 매달리지 않고 거부한다."""
    with pytest.raises(CommandError, match='트랜잭션'):
        _run('--dest', str(tmp_path))
