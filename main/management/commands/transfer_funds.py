from django.core.management.base import BaseCommand, CommandError
from main.tasks import transfer_telegram_funds

class Command(BaseCommand):
	help = 'Transfer funds from one telegram account to another'

	def add_arguments(self, parser):
		parser.add_argument(
			'sender-user-id',
			nargs='+',
			type=int,
			help='The user ID of the account you want to transfer from'
		)
		parser.add_argument(
			'recipient-user-id',
			nargs='+',
			type=int,
			help='The user ID of the account you want to transfer to'
		)

	def handle(self, *args, **options):
		success = transfer_telegram_funds(
			options['sender-user-id'][0], 
			options['recipient-user-id'][0]
		)

		if success:
			self.stdout.write(self.style.SUCCESS('Successfully transferred funds!'))
