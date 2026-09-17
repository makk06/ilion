from django.core.management.base import BaseCommand

from users.withdrawal import purge_withdrawn_users


class Command(BaseCommand):
    help = 'Purge accounts whose withdrawal grace period has elapsed.'

    def handle(self, *args, **options):
        purged = purge_withdrawn_users()
        self.stdout.write(f'purged={purged}')
