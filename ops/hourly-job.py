"""Task Scheduler entry point. Use pythonw.exe; child Python has no console window."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['collect', 'evaluate'])
    action = parser.parse_args().action
    project = Path(__file__).resolve().parents[1]
    backend = project/'tourist_congestion_backend'
    python = Path(sys.executable).with_name('python.exe')
    destination = project/'output/hourly-validation'
    destination.mkdir(parents=True, exist_ok=True)
    command = (['collect_crowd_inputs', '--once', '--max-seconds', '45'] if action == 'collect' else
               ['hourly_crowd', 'advance', '--artifacts', str(destination/'operational'), '--output', str(destination/'status.json')])
    result = subprocess.run([str(python), 'manage.py', *command], cwd=backend, capture_output=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=2400)
    if action == 'evaluate':
        event_result = subprocess.run([str(python), 'manage.py', 'event_crowd', 'tick'], cwd=backend, capture_output=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=600)
        result.stdout += event_result.stdout
        result.stderr += event_result.stderr
        result.returncode = result.returncode or event_result.returncode
    from dotenv import dotenv_values
    settings = {**dotenv_values(backend/'.env'), **os.environ}
    log = (result.stdout+result.stderr).decode('utf-8', errors='replace')
    for name, value in settings.items():
        if value and len(value) >= 4 and any(word in name.upper() for word in ('KEY', 'TOKEN', 'PASSWORD', 'SECRET')):
            log = log.replace(value, '[REDACTED]')
    handler = RotatingFileHandler(destination/f'{action}.log', maxBytes=1024*1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger = logging.getLogger('hourly-job')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info('exit=%s %s', result.returncode, log.strip())
    handler.close()
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
