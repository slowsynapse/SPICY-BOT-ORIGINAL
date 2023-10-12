from django.db import models
from django.utils import timezone
from django.contrib.postgres.fields import JSONField

class SLPToken(models.Model):
    name = models.CharField(max_length=60)
    token_id = models.CharField(max_length=70)
    emoji = models.CharField(max_length=10, default='\U0001F4B0')

    def __str__(self):
        return self.name
        
class Exchange(models.Model):
    buyer_id = models.CharField(max_length=100)
    seller_id = models.CharField(max_length=50)
    payment_token = models.ForeignKey(SLPToken, related_name='payment', on_delete=models.CASCADE, null=True)
    payment_amount = models.FloatField(default=0.0)
    exchange_token = models.ForeignKey(SLPToken, related_name='exchange', on_delete=models.CASCADE, null=True) 
    exchange_amount = models.FloatField(default=0.0) 
    date_created = models.DateTimeField(default=timezone.now)
    date_processed = models.DateTimeField(null=True)

class Challenge(models.Model):
    chat_id = models.CharField(max_length=100)
    message_id = models.CharField(max_length=100)
    challenger_id = models.CharField(max_length=50, null=True, blank=True)
    challenger_username = models.CharField(max_length=50, null=True, blank=True)
    challenger_token = models.CharField(max_length=50, null=True, blank=True)
    contender_id = models.CharField(max_length=50, null=True, blank=True)
    contender_username = models.CharField(max_length=50, null=True, blank=True)
    contender_token = models.CharField(max_length=50, null=True, blank=True)
    bet_amount = models.FloatField(default=0)
    result = JSONField(null=True, blank=True)
    accepted = models.BooleanField(default=False)
    cancelled = models.BooleanField(default=False)
    started = models.BooleanField(default=False)
    ended = models.BooleanField(default=False)
    cancelled_by = models.CharField(max_length=200)
    date_created = models.DateTimeField(default=timezone.now)
    slptoken = models.ForeignKey(SLPToken, related_name='sphere_challenges', on_delete=models.CASCADE, null=True)
    manager = models.CharField(max_length=50)
    percentage_fee = models.FloatField(default=0.0)
    

    



