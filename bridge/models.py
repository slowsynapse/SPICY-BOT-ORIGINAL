from django.db import models
from django.utils import timezone
from main.models import User


class Token(models.Model):
    name = models.CharField(max_length=20)
    MODE_CHOICES = [
        ('one-way', 'One-Way'),
        ('two-way', 'Two-Way')
    ]
    mode = models.CharField(
        max_length=10,
        choices=MODE_CHOICES,
        default='two-way'
    )
    slp_token_id = models.CharField(max_length=70)
    slp_source_address = models.CharField(max_length=60)
    slp_decimals = models.IntegerField(null=True)
    slp_to_sep20_ratio = models.FloatField(default=1)
    slp_wallet_hash = models.TextField(blank=True)
    slp_wallet_xpub = models.TextField(blank=True)
    slp_minimum_amount = models.IntegerField(default=100)
    burn_slp = models.BooleanField(default=False)
    slp_balance = models.FloatField(default=0)
    sep20_contract = models.CharField(max_length=60)
    sep20_source_address = models.CharField(max_length=60)
    sep20_balance = models.FloatField(default=0)
    sep20_decimals = models.IntegerField(null=True)
    sep20_minimum_amount = models.IntegerField(default=100)

    def __str__(self):
        return self.name


class SwapRequest(models.Model):
    user = models.ForeignKey(
        User,
        related_name='swaps',
        on_delete=models.CASCADE
    )
    telegram_chat_id = models.CharField(max_length=50)
    from_address = models.CharField(max_length=60)
    to_address = models.CharField(max_length=60)
    token = models.ForeignKey(
        Token,
        related_name='swaps',
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    receive_transaction_hash = models.CharField(max_length=70)
    date_fulfilled = models.DateTimeField(null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)


class Fulfillment(models.Model):
    swap_request = models.OneToOneField(
        SwapRequest,
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    send_transaction_hash = models.CharField(max_length=70)
    slp_burn_transaction_hash = models.CharField(max_length=70)
    date_created = models.DateTimeField(default=timezone.now)
