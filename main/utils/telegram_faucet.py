from django.utils import timezone
from datetime import timedelta
from main.models import FaucetDisbursement, User, SLPToken, Transaction
from django.db.models import Q, Sum
from django.conf import settings
import random
from .account import get_balance
from main.tasks import process_faucet_request

class Faucet(object):

    def __init__(self, *args, **kwargs):
        self.slp_address = kwargs.get('slp_address', None)
        token = kwargs.get('token', None)
        assert self.slp_address, 'required slp_address'
        assert token, 'required token'
        self.token = SLPToken.objects.get(name=token.upper())
        self.amount = 0
        self.error_message = None

    def address_valid(self):
        if not self.slp_address.startswith('simpleledger') and not len(slp_address) == 55:
            self.error_message = "invalid `simple_ledger address`."
            return False
        return True

    def within_amount_limit(self):
        interval = timedelta(hours=self.token.faucet_period_hours)
        from_date = timezone.now() - interval

        self.disbursements_today = FaucetDisbursement.objects.filter(
            date_completed__gt=from_date            
        ).filter(
            token=self.token
        )
        total_disbursements_today = self.disbursements_today.aggregate(Sum('amount'))
        self.total_today = total_disbursements_today['amount__sum'] or 0
        if self.total_today > self.token.faucet_daily_allotment:
            self.error_message = 'Our daily limit for the amount of {self.token.name} to give out has been reached. Try again tomorrow!'
            return False
        return True

    def on_timing(self):
        address = self.disbursements_today.filter(slp_address=self.slp_address)
        if address.exists():
            self.error_message = f"You’re only allowed one {self.token.name} faucet request every {self.token.faucet_period_hours} hours."
            if self.token.faucet_period_hours == 1:
                _list_  = self.error_message.split(" ")
                _list_[-1] = "hour."
                self.error_message = ' '.join(_list_)
            return False
        return True

    def manager_has_balance(self, amount):
        self.error_message = f"No faucet manager for {self.token.name}."
        if self.token.faucet_telegram_manager:
            self.error_message = f"{self.token.faucet_telegram_manager} does not exist in Telegram."
            user_qs = User.objects.filter(telegram_id=self.token.faucet_telegram_manager)
            if user_qs.exists():
                self.manager = user_qs.first()
                self.error_message = f"{self.manager} doesn't have sufficient balance to disburse {self.token.name}."
                manager_balance = get_balance(self.manager.id, self.token.token_id)
                if amount != 0 and manager_balance >= amount:
                    self.amount = amount
                    return True
        return False
        
    def pre_release(self):
        amount_range = range(int(self.token.faucet_amount_min), int(self.token.faucet_amount_max) + 1)
        amount = random.choice(amount_range)
        daily_faucet_balance = int(self.token.faucet_daily_allotment) - self.total_today
        if amount > daily_faucet_balance:
            return self.manager_has_balance(daily_faucet_balance)
        return self.manager_has_balance(amount)

    def release(self, _continue):
        if _continue:
            # Creation of FaucetDisbursement
            obj = FaucetDisbursement()
            obj.ip_address = "telegram"
            obj.slp_address = self.slp_address
            obj.amount = self.amount
            obj.token = self.token
            obj.save()
            self.disburse(obj)
            return True
        return False

    def deduct_to_manager(self, disbursement):
        obj = Transaction()
        _hash = f"{timezone.now().strftime('%Y-%m-%d%H:%M:%s')}-telegram-faucet"
        obj.transaction_hash = _hash
        obj.user = self.manager
        obj.slp_token = disbursement.token
        obj.amount = disbursement.amount
        obj.transaction_type = "Outgoing"
        obj.operation = "telegram-faucet"
        obj.save()

    def send_to_user(self, disbursement):
        user = User.objects.get(simple_ledger_address=self.slp_address)
        obj = Transaction()
        _hash = f"{timezone.now().strftime('%Y-%m-%d%H:%M:%S.%f')}-telegram-faucet"
        obj.transaction_hash = _hash
        obj.user = user
        obj.slp_token = disbursement.token
        obj.amount = disbursement.amount
        obj.transaction_type = "Incoming"
        obj.operation = "telegram-faucet"
        obj.save()

    def disburse(self, disbursement):
        self.deduct_to_manager(disbursement)
        self.send_to_user(disbursement)        
        disbursement.date_completed = timezone.now()
        disbursement.save()


    def process_application(self):
        if self.address_valid() and self.within_amount_limit() and self.on_timing():
            if self.release(self.pre_release()):
                return 'success'
        return self.error_message