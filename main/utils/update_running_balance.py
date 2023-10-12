from django.db.models import Sum
from main.utils.account import get_balance
from main.models import (
    User,
    SLPToken,
    Transaction,
    TelegramGroup
)

def update_running_balance(start, end, scibiz=False):
    tokens = SLPToken.objects.all()

    if not scibiz:
        users = User.objects.all()[start:end]
    else:
        users = TelegramGroup.objects.get(title="SciBiz Informatics").users.all()
    
    user_count = 1

    # print('Updating all transaction running balance to 0...')
    # transactions = Transaction.objects.all()
    # transactions.update(running_balance=0.0)

    print("Updating every user's latest transaction running_balance per token...")
    for user in users:
        for token in tokens:
            user_transactions = user.transactions.filter(
                slp_token=token
            )

            if user_transactions.exists():
                user_transactions = user_transactions.order_by('date_created')

                # run old balance inquiry for saving last token transaction's running balance
                incoming_trans = Transaction.objects.filter(
                    user=user,
                    transaction_type__icontains="Incoming",
                    slp_token=token
                )
                outgoing_trans = Transaction.objects.filter(
                    user=user,
                    transaction_type__icontains="Outgoing",
                    slp_token=token
                )
                incoming_trans_sum = 0
                outgoing_trans_sum = 0
                if incoming_trans.exists():
                    incoming_trans_sum = incoming_trans.aggregate(Sum('amount'))['amount__sum']
                if outgoing_trans.exists():
                    outgoing_trans_sum = outgoing_trans.aggregate(Sum('amount'))['amount__sum']

                balance = float(incoming_trans_sum) - float(outgoing_trans_sum)

                # update running balance of last transaction of that token
                last_token_transaction_id = user_transactions.last().id
                last_token_transaction = Transaction.objects.filter(id=last_token_transaction_id)
                last_token_transaction.update(running_balance=balance)

        print(f"{user_count} out of {users.count()} users updated.")
        user_count += 1


def compare_balance(start, end):
    users = User.objects.all()[start:end]
    tokens = SLPToken.objects.all()

    old_balance = 0
    new_balance = 0
    user_count = 1
    matched = 0
    unmatched = 0

    for user in users:
        for token in tokens:
            incoming_trans = Transaction.objects.filter(
                user=user,
                transaction_type__icontains="Incoming",
                slp_token=token
            )
            outgoing_trans = Transaction.objects.filter(
                user=user,
                transaction_type__icontains="Outgoing",
                slp_token=token
            )
            incoming_trans_sum = 0
            outgoing_trans_sum = 0
            if incoming_trans.exists():
                incoming_trans_sum = incoming_trans.aggregate(Sum('amount'))['amount__sum']
            if outgoing_trans.exists():
                outgoing_trans_sum = outgoing_trans.aggregate(Sum('amount'))['amount__sum']

            old_balance = float(incoming_trans_sum) - float(outgoing_trans_sum)
            new_balance = get_balance(user.id, token.token_id)
            same = round(old_balance) == round(new_balance)

            if same:
                matched += 1
            else:
                unmatched += 1
                print(f"Old balance: {old_balance} New balance: {new_balance}  Token: {token.name}")



        print(f"{user_count} out of {users.count()}")
        user_count += 1
    
    print(f"\nRESULT:\nMatched: {matched}\nUnmatched: {unmatched}")
