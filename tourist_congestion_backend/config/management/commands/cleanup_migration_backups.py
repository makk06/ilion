from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.backups import backup_created_at, delete_database_backup, expired_database_backups
from config.legal import DATABASE_BACKUP_RETENTION_DAYS


class Command(BaseCommand):
    help = 'Preview old migration backups. Delete only filenames explicitly supplied with --delete.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete', action='append', default=[], metavar='FILENAME',
            help='Delete this exact expired backup after previewing it. Repeat for each file.',
        )

    def handle(self, *args, **options):
        try:
            candidates = expired_database_backups(settings.STORAGE_DIR)
            selected = list(dict.fromkeys(options['delete']))
            eligible = {path.name for path in candidates}
            # Validate the complete selection before deleting the first file.
            if any(name not in eligible for name in selected):
                raise CommandError('Nothing deleted: select only exact filenames from the current preview.')
            if not selected:
                self.stdout.write(
                    f'PREVIEW ONLY: {DATABASE_BACKUP_RETENTION_DAYS}+ days old; no files deleted.'
                )
                for path in candidates:
                    info = path.lstat()
                    created_at = backup_created_at(path.name).isoformat()
                    self.stdout.write(f'{path.name}\t{info.st_size} bytes\tcreated={created_at}')
                self.stdout.write(f'eligible={len(candidates)}')
                return
            for name in selected:
                # Recheck eligibility at deletion time; earlier successful deletions are logged.
                removed = delete_database_backup(settings.STORAGE_DIR, name)
                self.stdout.write(f'deleted={removed.name}')
                self.stdout.flush()
        except (OSError, ValueError) as error:
            raise CommandError(f'Backup cleanup stopped: {error}') from error
