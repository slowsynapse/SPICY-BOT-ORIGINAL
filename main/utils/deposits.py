from main.models import Deposit, User
from main.utils import number_format
from random import random
from main.tasks import (
    send_telegram_message,
    send_twitter_message,
    send_reddit_message
)
import traceback


def credit_deposit(slpaddress, txid, amount):
    user_check = User.objects.filter(
        simple_ledger_address=slpaddress
    )
    if user_check.exists():
        user = user_check.first()
        deposit_check = Deposit.objects.filter(
            transaction_id=txid
        )
        if deposit_check.exists():
            print('Deposit transaction ID already exists!')
        else:
            deposit = Deposit()
            deposit.amount = amount
            deposit.user = user
            deposit.transaction_id = txid
            try:
                deposit.save()
                send_notif = True
            except IntegrityError as e:
                send_notif = False
                msg = traceback.format_exc()
            if send_notif:
                amount = number_format.round_sig(deposit.amount)
                message1 = 'Your deposit transaction of %s SPICE has been credited to your account.' % amount
                chat_id = user.telegram_id
                message1 += '\nhttps://explorer.bitcoin.com/bch/tx/' + txid
                if user.telegram_id:
                    send_telegram_message.delay(message1, chat_id, str(random()).replace('0.', ''))
                if user.twitter_id:
                    send_twitter_message.delay(message1, user.twitter_id)
                if user.reddit_id:
                    send_reddit_message.delay(message1, user.reddit_username)
            print('Deposit has been credited!')
    else:
        print('SLP address does exist in our DB!')
