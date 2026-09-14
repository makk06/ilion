"""Offline ARM64 runtime checks with disposable data; keeps /private/tmp artifacts."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time

IMAGE = 'ilion-backend-smoke'


def docker(*args, check=True):
    return subprocess.run(['docker', *args], text=True, capture_output=True, check=check)


def start(directory):
    return docker('run', '-d', '--network', 'none', '--read-only', '--user', '0:0',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '1024m',
        '--pids-limit', '128', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
        '--mount', f'type=bind,src={directory},dst=/data',
        '-e', 'STORAGE_DIR=/data', '-e', 'APP_BASE_URL=https://ilion.example.test',
        '-e', 'DJANGO_SECRET_KEY=offline-smoke-only-never-use-in-production-1234567890-abcdefghij',
        '-e', 'DATA_WORKER_ENABLED=true', IMAGE).stdout.strip()


def healthy(container):
    for _ in range(60):
        if docker('exec', container, 'python', 'runtime_healthcheck.py', check=False).returncode == 0:
            return
        if docker('inspect', '--format', '{{.State.Running}}', container).stdout.strip() != 'true':
            raise AssertionError(docker('logs', container).stdout)
        time.sleep(1)
    raise AssertionError('Health timeout')


def main():
    directory = Path(tempfile.mkdtemp(prefix='ilion-runtime-smoke-', dir='/private/tmp'))
    print('Disposable database retained at', directory, flush=True)
    container = start(directory)
    try:
        healthy(container)
        second = docker('exec', container, 'python', 'manage.py', 'run_data_worker', '--once', check=False)
        assert second.returncode != 0 and 'already running' in second.stderr
        docker('exec', '-e', 'DJANGO_DEBUG=true', container, 'python', 'manage.py', 'seed_dev_data')
        probe = '''import json,urllib.request
request=urllib.request.Request('http://127.0.0.1:8000/api/recommendations',
 data=json.dumps({'latitude':37.575,'longitude':126.977,'limit':3,'weather_aware':False}).encode(),
 headers={'Content-Type':'application/json','X-Forwarded-Proto':'https'})
with urllib.request.urlopen(request,timeout=10) as response:
 body=json.load(response)
 assert body['success'] and len(body['data']['items'])>0,body
print('Recommendation API returned real fixture candidates')
'''
        print(docker('exec', container, 'python', '-c', probe).stdout.strip(), flush=True)
        with sqlite3.connect(directory/'db.sqlite3') as db:
            before = db.execute('select count(*) from places_place').fetchone()[0]
            assert before == 10
            assert db.execute('pragma journal_mode').fetchone()[0] == 'wal'
        # A collector crash must take down the web process too, permitting restart policy recovery.
        docker('exec', container, 'python', '-c', '''import os,signal
for entry in os.listdir('/proc'):
 if entry.isdigit():
  try: args=open('/proc/'+entry+'/cmdline','rb').read().split(b'\\0')
  except FileNotFoundError: continue
  if len(args)>3 and args[1:3]==[b'manage.py',b'run_data_worker']:
   os.kill(int(entry),signal.SIGKILL)
   break
else: raise SystemExit('collector not found')
''')
        result = subprocess.run(['docker', 'wait', container], text=True, capture_output=True, timeout=30, check=True)
        assert result.stdout.strip() == '1', result.stdout
        docker('rm', container)
        container = start(directory)
        healthy(container)
        with sqlite3.connect(directory/'db.sqlite3') as db:
            assert db.execute('select count(*) from places_place').fetchone()[0] == before
            assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        docker('stop', '--time', '30', container)
        assert docker('inspect', '--format', '{{.State.ExitCode}}', container).stdout.strip() == '0'
        print('PASS: constrained runtime, initial schema, single worker, API, crash recovery, persistence, clean shutdown', flush=True)
    finally:
        docker('stop', '--time', '30', container, check=False)
        docker('rm', container, check=False)


if __name__ == '__main__':
    main()
