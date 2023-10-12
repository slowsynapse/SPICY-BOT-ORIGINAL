from django.core.management.base import BaseCommand, CommandError
from main.tasks import kickstart_userscan


class Command(BaseCommand):
    help = "Use for checking missed deposit transactions"

    def handle(self, *args, **options):
        kickstart_userscan.delay()
        self.stdout.write(self.style.SUCCESS(f'A task was delayed to trigger per_user_scanning of deposits...')) 