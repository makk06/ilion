"""One web master and one SQLite collector, supervised by container PID 1."""
import fcntl
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time


def initialize_database(storage):
    """Initialize only an absent database; never auto-migrate an existing DB."""
    database = storage / 'db.sqlite3'
    if not database.exists():
        staging = storage / 'initializing'
        staging.mkdir(exist_ok=True)
        subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'],
                       env={**os.environ, 'STORAGE_DIR': str(staging)}, check=True)
        os.replace(staging / 'db.sqlite3', database)
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
