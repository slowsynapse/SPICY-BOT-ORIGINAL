from main.models import Transaction
from uuid import uuid4
from hashlib import sha256

def script():
    transactions = Transaction.objects.filter(transaction_hash='')
    total_count = transactions.count()
    count = 1
    for transaction in transactions:
        str_id = str(transaction.id)
        generated_transaction_hash = sha256(str_id.encode()).hexdigest()
        qs = Transaction.objects.filter(id=transaction.id)
        qs.update(transaction_hash=generated_transaction_hash)
        print(f"{count} out of {total_count}")
        count += 1