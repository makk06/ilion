"""One web master and one SQLite collector, supervised by container PID 1."""
import fcntl
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time


APPROVED_MIGRATION_PLANS = {
    'config.0001_merge_main_recommendation': (
        ('users', '0003_user_preferences_companion_inquiry_plan_review_and_more'),
        ('users', '0004_companion_time_alter_companion_date'),
        ('users', '0003_feedback'),
        ('users', '0005_merge_20260917_0915'),
        ('places', '0004_nationwide_crowd'),
        ('places', '0005_crowd_demand'),
        ('places', '0006_baseline_lookup_index'),
        ('places', '0011_merge_20260917_1750'),
        ('config', '0001_merge_main_recommendation'),
    ),
}


def _pending_migrations():
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor

    connection = connections['default']
    try:
        executor = MigrationExecutor(connection)
        return [
            (migration.app_label, migration.name)
            for migration, backwards in executor.migration_plan(
                executor.loader.graph.leaf_nodes()
            )
            if not backwards
        ]
    finally:
        connections.close_all()


def _quick_check(database):
    with sqlite3.connect(database) as connection:
        result = connection.execute('PRAGMA quick_check').fetchone()
    if result != ('ok',):
        raise RuntimeError('SQLite integrity check failed')


def _backup_database(storage, database, target):
    backup_directory = storage / 'migration-backups'
    backup_directory.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup = backup_directory / f'db-before-{target.replace(".", "-")}-{timestamp}.sqlite3'
    partial = backup.with_suffix('.sqlite3.partial')
    with sqlite3.connect(database) as source, sqlite3.connect(partial) as destination:
        source.backup(destination)
    _quick_check(partial)
    os.replace(partial, backup)
    return backup


def _apply_approved_migration(storage, database):
    pending = _pending_migrations()
    if not pending:
        return None

    target = os.environ.get('DJANGO_MIGRATION_TARGET', '').strip()
    approved_plan = APPROVED_MIGRATION_PLANS.get(target)
    if approved_plan is None or tuple(pending) != approved_plan:
        raise RuntimeError('Database migrations require an exact approved target')

    backup = _backup_database(storage, database, target)
    target_app, target_name = approved_plan[-1]
    subprocess.run(
        [sys.executable, 'manage.py', 'migrate', target_app, target_name, '--noinput'],
        env=os.environ.copy(),
        check=True,
    )
    if _pending_migrations():
        raise RuntimeError('Approved database migration did not reach the current schema')
    _quick_check(database)
    print(f'runtime: database backup retained at {backup}', flush=True)
    return backup


def initialize_database(storage):
    """Initialize a new DB, or apply one exact, explicitly approved migration plan."""
    database = storage / 'db.sqlite3'
    if not database.exists():
        staging = storage / 'initializing'
        staging.mkdir(exist_ok=True)
        subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'],
                       env={**os.environ, 'STORAGE_DIR': str(staging)}, check=True)
        os.replace(staging / 'db.sqlite3', database)
    else:
        _apply_approved_migration(storage, database)
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--check'], check=True)
    with sqlite3.connect(database) as connection:
        connection.execute('PRAGMA journal_mode=WAL')


def main():
    storage = Path(os.environ.get('STORAGE_DIR', '/data'))
    os.environ['STORAGE_DIR'] = str(storage)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()  # Validate secrets/configuration before touching durable state.
    storage.mkdir(parents=True, exist_ok=True)
    lock = (storage / '.runtime.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    initialize_database(storage)
    children = []
    stopping = False
    started = time.monotonic()

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if os.environ.get('DATA_WORKER_ENABLED', 'false').lower() == 'true':
            children.append(subprocess.Popen([sys.executable, 'manage.py', 'run_data_worker', '--scheduled']))
        children.append(subprocess.Popen([
            sys.executable, '-m', 'gunicorn', 'config.wsgi:application',
            '--bind', os.environ.get('HOST', '0.0.0.0') + ':' + os.environ.get('PORT', '8000'),
            '--workers', '1', '--threads', '4', '--timeout', '60',
            '--graceful-timeout', '20', '--worker-tmp-dir', '/tmp',
            '--access-logfile', '-', '--error-logfile', '-',
        ]))
        while not stopping:
            if any(child.poll() is not None for child in children):
                print('runtime: child exited; restarting the whole container is required', flush=True)
                return 1
            if os.environ.get('DATA_WORKER_ENABLED', 'false').lower() == 'true':
                heartbeat = storage / '.data-worker-heartbeat'
                if time.monotonic() - started > 180 and (not heartbeat.exists() or time.time() - heartbeat.stat().st_mtime > 180):
                    print('runtime: collector heartbeat expired', flush=True)
                    return 1
            time.sleep(1)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + 22
        for child in children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        lock.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('runtime startup failed: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
