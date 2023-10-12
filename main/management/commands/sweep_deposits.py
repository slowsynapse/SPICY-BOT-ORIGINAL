from django.core.management.base import BaseCommand, CommandError
from main.utils.sweep import SweepDeposits
import getpass


class Command(BaseCommand):
    help = 'Sweeps SPICE deposits to the bot wallet'

    def handle(self, *args, **options):
        seed = getpass.getpass('Seed: ')
        sweep = SweepDeposits(seed)
        sweep.execute()
        self.stdout.write(self.style.SUCCESS('Successfully swept all unswept deposits!'))

