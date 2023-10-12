from main.models import User
from main.utils.account import get_balance
from django.conf import settings
import logging


logger = logging.getLogger(__name__)



class BalanceUpdated(object):

    def __init__(self,beg ,end):
        self.beg = beg
        self.end = end

    def execute(self):
        users = User.objects.all()[self.beg:self.end]
        for user in users:
            balance = get_balance(user.id, settings.SPICE_TOKEN_ID)
            if balance > 0:
                transaction = user.transactions.last()
                transaction.running_balance = balance
                transaction.save()
                print(f'updated - {user.id}')

