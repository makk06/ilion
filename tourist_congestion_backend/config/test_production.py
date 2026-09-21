from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import sqlite3
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


class ProductionMigrationTests(TestCase):
    backend_directory = Path(__file__).resolve().parents[1]
    migration_name = '0008_user_signup_consent'
    migration_target = f'users.{migration_name}'

    def _environment(self, storage, **updates):
        environment = {
            'PATH': os.environ['PATH'],
            'PYTHON_DOTENV_DISABLED': '1',
            'DJANGO_SETTINGS_MODULE': 'config.settings',
            'DJANGO_DEBUG': 'true',
            'DATA_WORKER_ENABLED': 'false',
            'STORAGE_DIR': str(storage),
        }
        environment.update(updates)
        return environment

    def _run(self, arguments, environment, *, check=True):
        return subprocess.run(
            [sys.executable, *arguments],
            cwd=self.backend_directory,
            env=environment,
            capture_output=True,
            text=True,
            check=check,
        )

    def _database_at_current_production_migration(self, storage):
        environment = self._environment(storage)
        script = (
            'import django; django.setup(); '
            'from django.db import connection; '
            'from django.db.migrations.executor import MigrationExecutor; '
            'executor = MigrationExecutor(connection); '
            "executor.migrate([('config', '0001_merge_main_recommendation'), "
            "('admin', '0003_logentry_add_action_flag_choices'), "
            "('sessions', '0001_initial')])"
        )
        self._run(['-c', script], environment)
        return environment

    def _initialize_existing_database(self, environment, *, check=True):
        script = (
            'import os; from pathlib import Path; import django; django.setup(); '
            'from runtime import initialize_database; '
            "initialize_database(Path(os.environ['STORAGE_DIR']))"
        )
        return self._run(['-c', script], environment, check=check)

    def _database_at_partial_withdrawal_migration(self, storage):
        environment = self._database_at_current_production_migration(storage)
        self._run(
            ['manage.py', 'migrate', 'users',
             '0006_anonymousactor_withdrawalreason_withdrawnemailhash_and_more',
             '--noinput'],
            environment,
        )
        return environment

    def _database_at_completed_withdrawal_migration(self, storage):
        environment = self._database_at_current_production_migration(storage)
        self._run(
            ['manage.py', 'migrate', 'users',
             '0007_favorite_actor_feedback_actor_recentplace_actor_and_more',
             '--noinput'],
            environment,
        )
        return environment

    def test_exact_approved_migration_plan_creates_verified_backup(self):
        with TemporaryDirectory() as directory:
            storage = Path(directory)
            environment = self._database_at_current_production_migration(storage)
            environment['DJANGO_MIGRATION_TARGET'] = self.migration_target

            result = self._initialize_existing_database(environment)

            backups = list((storage / 'migration-backups').glob('*.sqlite3'))
            self.assertEqual(len(backups), 1)
            self.assertIn(str(backups[0]), result.stdout)
            with sqlite3.connect(backups[0]) as backup:
                self.assertEqual(backup.execute('PRAGMA quick_check').fetchone(), ('ok',))
                self.assertIsNone(backup.execute(
                    'SELECT 1 FROM django_migrations WHERE app = ? AND name = ?',
                    ('users', self.migration_name),
                ).fetchone())
            with sqlite3.connect(storage / 'db.sqlite3') as database:
                self.assertEqual(database.execute('PRAGMA quick_check').fetchone(), ('ok',))
                self.assertEqual(database.execute(
                    'SELECT 1 FROM django_migrations WHERE app = ? AND name = ?',
                    ('users', self.migration_name),
                ).fetchone(), (1,))
                index_names = {
                    row[0]
                    for row in database.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index'"
                    )
                }
                table_names = {
                    row[0]
                    for row in database.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertIn('places_hist_crowd_a_88980c_idx', index_names)
            self.assertIn('places_crowdestimate', table_names)
            self.assertIn('users_companion', table_names)
            self.assertIn('users_feedback', table_names)

    def test_existing_database_refuses_unapproved_migration(self):
        with TemporaryDirectory() as directory:
            storage = Path(directory)
            environment = self._database_at_current_production_migration(storage)

            result = self._initialize_existing_database(environment, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('exact approved target', result.stderr)
            self.assertFalse((storage / 'migration-backups').exists())
            with sqlite3.connect(storage / 'db.sqlite3') as database:
                self.assertIsNone(database.execute(
                    'SELECT 1 FROM django_migrations WHERE app = ? AND name = ?',
                    ('users', self.migration_name),
                ).fetchone())

    def test_approved_plan_resumes_after_first_migration_was_committed(self):
        with TemporaryDirectory() as directory:
            storage = Path(directory)
            environment = self._database_at_partial_withdrawal_migration(storage)
            environment['DJANGO_MIGRATION_TARGET'] = self.migration_target

            self._initialize_existing_database(environment)

            backups = list((storage / 'migration-backups').glob('*.sqlite3'))
            self.assertEqual(len(backups), 1)
            with sqlite3.connect(backups[0]) as backup:
                self.assertEqual(backup.execute('PRAGMA quick_check').fetchone(), ('ok',))
                self.assertEqual(backup.execute(
                    'SELECT 1 FROM django_migrations WHERE app = ? AND name = ?',
                    ('users', '0006_anonymousactor_withdrawalreason_withdrawnemailhash_and_more'),
                ).fetchone(), (1,))
                self.assertIsNone(backup.execute(
                    'SELECT 1 FROM django_migrations WHERE app = ? AND name = ?',
                    ('users', self.migration_name),
                ).fetchone())
            with sqlite3.connect(storage / 'db.sqlite3') as database:
                self.assertEqual(database.execute('PRAGMA quick_check').fetchone(), ('ok',))
                self.assertEqual(database.execute(
                    'SELECT 1 FROM django_migrations WHERE app = ? AND name = ?',
                    ('users', self.migration_name),
                ).fetchone(), (1,))

    def test_approved_plan_applies_consent_after_completed_withdrawal_migration(self):
        with TemporaryDirectory() as directory:
            storage = Path(directory)
            environment = self._database_at_completed_withdrawal_migration(storage)
            environment['DJANGO_MIGRATION_TARGET'] = self.migration_target

            self._initialize_existing_database(environment)

            with sqlite3.connect(storage / 'db.sqlite3') as database:
                self.assertEqual(database.execute('PRAGMA quick_check').fetchone(), ('ok',))
                self.assertEqual(database.execute(
                    'SELECT 1 FROM django_migrations WHERE app = ? AND name = ?',
                    ('users', self.migration_name),
                ).fetchone(), (1,))
                columns = {row[1] for row in database.execute('PRAGMA table_info(users_user)')}
            self.assertTrue({'age_confirmed_at', 'terms_agreed_at', 'terms_version'} <= columns)
