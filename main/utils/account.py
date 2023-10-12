from main.models import (
    Transaction, 
    SLPToken, 
    User,
    TelegramGroup
)
from django.db import IntegrityError
from django.db.transaction import TransactionManagementError
from django.conf import settings
from django.db.models import Sum
from hashlib import sha256
import logging
import time

logger = logging.getLogger(__name__)

#Updated saving transaction
def create_transaction(user_id, amount, transaction_type, token_id, operation, chat_id=None, transaction_hash=None, connected_transactions=[], retry=5):
    try:
        user = User.objects.get(id=user_id)
        token = SLPToken.objects.filter(id=token_id)
        group = None

        if chat_id is not None:
            group = TelegramGroup.objects.get(chat_id=chat_id)

        if token.exists() and user:
            if transaction_hash is None:
                txn = Transaction(
                    user=user,
                    amount=amount,
                    operation=operation,
                    slp_token=token.first(),
                    group=group,
                    # transaction_hash=transaction_hash,
                    transaction_type=transaction_type,
                    connected_transactions=connected_transactions
                )
                txn.save()

                if operation == settings.TXN_OPERATION['TRANSFER']:
                    transaction_hash = f'{user_id}-{token.first().name}-{txn.id}'
                    transaction_hash = sha256(transaction_hash.encode()).hexdigest()
                    txn_qs = Transaction.objects.filter(id=txn.id)
                    txn_qs.update(transaction_hash=transaction_hash)
                
                return True, transaction_hash
            else:
                transaction_hash = sha256(transaction_hash.encode()).hexdigest()
                Transaction(
                    user=user,
                    amount=amount,
                    operation=operation,
                    slp_token=token.first(),
                    transaction_type=transaction_type,
                    transaction_hash=transaction_hash,
                    connected_transactions=connected_transactions,
                    group=group
                ).save()

                return True, transaction_hash
    except IntegrityError as exc:
        logger.info(f'\n\nTRACK UNIQUE---------{exc}--------\n\n')
        pass
    except TransactionManagementError as exc:
        if retry:
            time.sleep(1)
            retries_count = retry - 1
            create_transaction(
                user_id=user_id,
                amount=amount,
                transaction_type=transaction_type,
                token_id=token_id,
                operation=operation,
                chat_id=chat_id,
                transaction_hash=transaction_hash,
                connected_transactions=connected_transactions,
                retry=retries_count
            )

    return False, transaction_hash


def swap_related_transactions(h1, h2):
    try:
        q1 = Transaction.objects.filter(transaction_hash=h1)
        q2 = Transaction.objects.filter(transaction_hash=h2)

        q1.update(connected_transactions=[h2])
        q2.update(connected_transactions=[h1])
    except (IntegrityError, TransactionManagementError) as exc:
        pass


# def get_hash(string):
#     return sha256(string.encode()).hexdigest()


#get balance of the specified token
def get_balance(user_id, token):
    if 'bch' in token:
        token = "-"
    user_txns = Transaction.objects.filter(
        user__id=user_id,
        slp_token__token_id=token
    )

    if user_txns.exists():
        user_txns = user_txns.order_by('date_created')
        return user_txns.last().running_balance
    else:
        return 0


# def old_balance_inquiry(user_id, token_id):
    # user = User.objects.get(id=user_id)
    # incoming_trans = Transaction.objects.filter(
    #     user=user,
    #     transaction_type__icontains="Incoming",
    #     slp_token__token_id=token_id
    # )
    # outgoing_trans = Transaction.objects.filter(
    #     user=user,
    #     transaction_type__icontains="Outgoing",
    #     slp_token__token_id=token_id
    # )
    # incoming_trans_sum = 0
    # outgoing_trans_sum = 0
    # if incoming_trans.exists():
    #     incoming_trans_sum = incoming_trans.aggregate(Sum('amount'))['amount__sum']
    # if outgoing_trans.exists():
    #     outgoing_trans_sum = outgoing_trans.aggregate(Sum('amount'))['amount__sum']

    # balance = float(incoming_trans_sum) - float(outgoing_trans_sum)

    # return balance
