"""배포 전 DB 백업의 조회와 관리자 수동 정리.

runtime.py 는 Django 설정 전에 이 모듈을 쓰므로 Django 를 import 하지 않는다.
"""

from datetime import datetime, timezone
from pathlib import Path
import re
import stat
import time

from config.legal import DATABASE_BACKUP_RETENTION_DAYS

BACKUP_DIRECTORY_NAME = 'migration-backups'
BACKUP_NAME = re.compile(
    r'db-before-[A-Za-z0-9_-]+-(?P<created>\d{8}T\d{6}\.\d{6}Z)'
    r'\.sqlite3(?:\.partial)?'
)


def backup_created_at(name):
    """Read the creation time written by runtime._backup_database, independent of mtime."""
    match = BACKUP_NAME.fullmatch(name)
    if match is None:
        raise ValueError('Specify a generated backup filename, without a path.')
    return datetime.strptime(match['created'], '%Y%m%dT%H%M%S.%fZ').replace(tzinfo=timezone.utc)


def expired_database_backups(storage, now=None):
    """Return expired regular backup files without changing anything."""
    backup_directory = Path(storage) / BACKUP_DIRECTORY_NAME
    if backup_directory.is_symlink():
        raise ValueError('The migration backup directory must not be a symlink.')
    if not backup_directory.is_dir():
        return []
    cutoff = (time.time() if now is None else now) - DATABASE_BACKUP_RETENTION_DAYS * 86400
    expired = []
    # .partial 은 복사 도중 멈춘 잔여물이다. WAL/SHM, 링크와 하위 폴더는 제외한다.
    for path in sorted(backup_directory.iterdir()):
        try:
            created_at = backup_created_at(path.name)
        except ValueError:
            continue
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and created_at.timestamp() <= cutoff:
            expired.append(path)
    return expired


def delete_database_backup(storage, name, now=None):
    """Delete one explicitly selected, still-expired backup; never a whole directory."""
    if not BACKUP_NAME.fullmatch(name):
        raise ValueError('Specify a backup filename from the preview, without a path.')
    eligible = {path.name: path for path in expired_database_backups(storage, now=now)}
    if name not in eligible:
        raise ValueError(
            f'The selected backup is missing, unsafe, or less than {DATABASE_BACKUP_RETENTION_DAYS} days old.'
        )
    path = eligible[name]
    path.unlink()
    return path
