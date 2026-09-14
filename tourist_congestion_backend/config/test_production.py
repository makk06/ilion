from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import subprocess
import sys

from django.test import TestCase, override_settings


class ProductionHealthTests(TestCase):
    @override_settings(DEBUG=False, DATA_WORKER_ENABLED=True)
    def test_worker_heartbeat_is_required_and_expires(self):
        with TemporaryDirectory() as directory, override_settings(STORAGE_DIR=Path(directory)):
            self.assertEqual(self.client.get('/healthz').status_code, 503)
            path = Path(directory) / '.data-worker-heartbeat'
            path.touch()
            self.assertEqual(self.client.get('/healthz').status_code, 200)
            os.utime(path, (1, 1))
            self.assertEqual(self.client.get('/healthz').status_code, 503)

    def test_production_refuses_development_secret(self):
        result = subprocess.run([sys.executable, '-c', 'import config.settings'],
            env={'PATH': os.environ['PATH'], 'PYTHON_DOTENV_DISABLED': '1', 'DJANGO_DEBUG': 'false'},
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', result.stderr)

    @override_settings(DEBUG=False)
    def test_health_reports_database_failure_without_error_details(self):
        from django.db import OperationalError
        with patch('config.views.connection.cursor', side_effect=OperationalError('private diagnostic')):
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})
