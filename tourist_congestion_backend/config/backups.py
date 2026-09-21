"""배포 전 DB 백업의 보관 기간 관리.

runtime.py 는 Django 설정 전에 이 모듈을 쓰므로 Django 를 import 하지 않는다.
"""

import time
from pathlib import Path

from config.legal import DATABASE_BACKUP_RETENTION_DAYS

BACKUP_DIRECTORY_NAME = 'migration-backups'


def prune_database_backups(storage, now=None):
    """처리방침에 적은 기간이 지난 백업을 지운다. 탈퇴 회원 정보가 백업에 남지 않게 한다."""
    backup_directory = Path(storage) / BACKUP_DIRECTORY_NAME
    if not backup_directory.is_dir():
        return []
    cutoff = (time.time() if now is None else now) - DATABASE_BACKUP_RETENTION_DAYS * 86400
    removed = []
    # .partial 은 복사 도중 멈춘 잔여물이다. 같은 기준으로 정리한다.
    for path in backup_directory.glob('db-before-*.sqlite3*'):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    return removed
