from django.db import models
from django.contrib.auth.models import User as usr
from django.utils import timezone
from datetime import timedelta, datetime
from django.contrib.postgres.fields import JSONField, ArrayField
from bitcash import Key
from subprocess import Popen, PIPE
from django.conf import settings
import re
from django.db.models import Sum
import logging
from django.contrib.auth.models import User as djUser
from django.db import transaction as trans

logger = logging.getLogger(__name__)


class Account(usr):
    email_addr = models.CharField(max_length=60)
    confirmation = JSONField(default=None, null=True, unique=True)

    class Meta:
        verbose_name = 'Account'
        verbose_name_plural = 'Accounts'

class Subscriber(models.Model):
    username = models.CharField(max_length=50, unique=True)
    app_name = models.CharField(max_length=50, default=None, null=True)
    details = JSONField(default=None, null=True, blank=True)
    token = models.CharField(max_length=16, unique=True)
    email = models.CharField(max_length=60, unique=True)
    password = models.CharField(max_length=30)
    payment = models.BooleanField(default=False)


class User(models.Model):
    reddit_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    reddit_user_details = JSONField(default=dict, blank=True)
    twitter_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    twitter_user_details = JSONField(default=dict, blank=True)
    telegram_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    telegram_user_details = JSONField(default=dict, blank=True)
    user_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    user_details = JSONField(default=dict, blank=True)
    post_to_spicefeed = models.BooleanField(default=True)
    simple_ledger_address = models.CharField(max_length=200, null=True, blank=True)
    bitcoincash_address = models.CharField(max_length=200, null=True, blank=True)
    last_activity = models.DateTimeField(default=timezone.now, null=True, blank=True)
    last_private_message = models.DateTimeField(default=None, null=True, blank=True)
    pof = JSONField(default=dict)
    date_created = models.DateTimeField(default=timezone.now, null=True)
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT)
    ban = models.BooleanField(default=False)
    anon_name = models.CharField(max_length=50 ,null=True, unique=True)
    display_username = models.BooleanField(default=True)
    transferred = models.BooleanField(default=False)
    frozen = models.BooleanField(default=False)
    slpnotified = models.BooleanField(default=False)
    subscribed_to_watchtower = models.BooleanField(default=False)
    
    class Meta:
        indexes = [
            models.Index(fields=['telegram_id']),
            models.Index(fields=['last_activity']),
            models.Index(fields=['frozen'])
        ]

    def serialize_hook(self, hook):
        # optional, there are serialization defaults
        # we recommend always sending the Hook
        # metadata along for the ride as well
        data = {
            'hook': hook.dict(),
            'data': {
                'reddit_id': self.reddit_id,
                'reddit_user_details': self.reddit_user_details,
                'twitter_id': self.twitter_id,
                'twitter_user_details': self.twitter_user_details,
                'telegram_id': self.telegram_id,
                'telegram_user_details': self.telegram_user_details,
                'user_id': self.user_id,
                'user_details': self.user_details,
                'last_activity': self.last_activity,
                'pof': self.pof,
                'account': self.account,
                'ban': self.ban,
                'anon_name': self.anon_name,
                'display_username': self.display_username
            }
        }
        self.transferred = True
        return data

    def clean(self):
        self.transferred = True

    @property
    def pof_display(self):
        symbols = settings.POF_SYMBOLS
        if type(self.pof) == dict:
            if "pof_rating" in self.pof.keys():
                val = int(self.pof['pof_rating'])
                return '%s/5 %s' % (val, symbols[val])
        if type(self.pof) == float:
            return None

        return '0/5 %s' % symbols[0]

    @property    
    def get_user_id(self):
        if self.telegram_id:
            return {'source': 'telegram','id': self.telegram_id}
        elif self.twitter_id:
            return {'source': 'twitter','id': self.twitter_id}
        elif self.reddit_id:
            return {'source': 'reddit','id': self.reddit_id}
        elif self.user_id:
            return {'source': 'other','id': self.user_id}

    @property
    def balance(self, token_id):
        user_txns = self.transactions.filter(
            slp_token__token_id=token_id
        )

        if user_txns.exists():
            user_txns = user_txns.order_by('date_created')
            return user_txns.last().running_balance
        else:
            return 0

        # incoming_trans = self.transactions.filter(
        #     transaction_type__icontains="Incoming",
        #     slp_token__token_id=token_id
        # )
        # outgoing_trans = self.transactions.filter(
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

    @property
    def telegram_display_name(self):
        display_name = ''
        if self.telegram_user_details:
            try:
                display_name = self.telegram_user_details['first_name']
                lastname = self.telegram_user_details['last_name']
                display_name = display_name + ' ' + lastname
            except KeyError:
                pass
            # Remove non-latin characters
            display_name = re.sub('[^a-zA-Z\d\s:]', '', display_name).strip()
            if len(display_name) > 20:
                display_name = display_name[0:20]
        return display_name

    @property
    def telegram_username(self):
        try:
            username = self.telegram_user_details['username']
        except KeyError:
            username = ''
        return username

    @property
    def user_username(self):
        try:
            username = self.user_details['username']
        except KeyError:
            username = ''
        return username
    

    @property
    def twitter_screen_name(self):
        screen_name = ''
        if self.twitter_user_details:
            screen_name = self.twitter_user_details['screen_name']
        return screen_name

    @property
    def twitter_user_id(self):
        if self.twitter_user_details:
            return self.twitter_user_details['id']

    @property
    def reddit_username(self):
        username = ''
        if self.reddit_user_details:
            username = self.reddit_user_details['username']
        return username

    # def rain(self, text, group_id, balance):
    #     pass

    @property
    def get_username(self):
        return self.telegram_display_name or self.telegram_username or self.twitter_screen_name or self.reddit_username or self.user_username

    @property
    def get_source(self):
        if self.twitter_id:
            return 'twitter'
        elif self.reddit_id:
            return 'reddit'
        elif self.telegram_id:
            return 'telegram'
        else:
            return 'other'

        

    def __str__(self):
        if self.twitter_user_details:
            return self.twitter_user_details['screen_name']
        if self.telegram_user_details:
            return self.telegram_user_details['first_name']
        if self.reddit_user_details:
            return self.reddit_user_details['username']
        if 'username' in self.user_details.keys():
            return self.user_details['username']
        else:
            if self.telegram_id:
                return self.telegram_id
            if self.twitter_id:
                return self.twitter_id
            if self.user_id:
                return self.user_id
            else:
                return self.reddit_id

    def save(self, *args, **kwargs):
        user = djUser.objects.first()
        if user is not None:
            self.user = user
        super(User, self).save(*args, **kwargs)


class SLPToken(models.Model):
    name = models.CharField(max_length=60)
    token_id = models.CharField(max_length=70)
    emoji = models.CharField(max_length=10, default='\U0001F4B0')
    color = models.CharField(max_length=30, default='#F5B7B1')
    withdrawal_limit = models.FloatField(default=settings.WITHDRAWAL_LIMIT)
    withdrawal_percentage_fee = models.FloatField(default=0.0)
    tip_percentage_fee = models.FloatField(default=0.0)
    tip_threshold = models.FloatField(default=0.0)
    tip_emojis = JSONField(default=dict, blank=True)
    big_deposit_threshold = models.FloatField(default=settings.BIG_DEPOSIT_THRESHOLD)
    min_deposit = models.FloatField(default=1)
    min_rain_amount = models.FloatField(default=settings.MINIMUM_RAIN_AMOUNT)
    publish = models.BooleanField(default=False)
    allowed_devs = JSONField(default=list)
    faucet_amount_min = models.FloatField(default=1)
    faucet_amount_max = models.FloatField(default=10)
    faucet_interval = models.IntegerField(default=24)
    faucet_daily_allotment = models.FloatField(default=1000)
    faucet_telegram_manager = models.CharField(max_length=100, blank=True)
    faucet_period_hours = models.IntegerField(default=24)
    verbose_names = JSONField(default=list)
    announce_delisting = models.DateTimeField(null=True, blank=True)
    date_delisted = models.DateTimeField(null=True, blank=True)
    max_bet_for_sphere = models.FloatField(default=10000)
    min_bet_for_sphere = models.FloatField(default=50)
    sphere_manager = models.CharField(max_length=50, null=True, blank=True)
    sphere_percentage_fee = models.FloatField(default=0.0)
    token_exchange = JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name

    def serialize_hook(self, hook):
        # optional, there are serialization defaults
        # we recommend always sending the Hook
        # metadata along for the ride as well
        data = {
            'hook': hook.dict(),
            'data': {
                'name': self.name,
                'token_id': self.token_id,
                'emoji': self.emoji
            }
        }
        
        self.transferred =True
        return data

    def save(self, *args, **kwargs):
        if not self.pk and self.tip_emojis is not {}:
            tokens = SLPToken.objects.all()
            existing_emojis = []
            for token in tokens:
                existing_emojis += [ e for e in token.tip_emojis.keys()]
            for new_emoji in self.tip_emojis.keys():
                if new_emoji in existing_emojis:
                    assert True, f"This emoji {new_emoji} already used by other token. Try again!"
        user = djUser.objects.first()
        if user is not None:
            self.user = user
        
        if self.announce_delisting and not self.date_delisted:
            self.date_delisted = self.announce_delisting
            
        super(SLPToken, self).save(*args, **kwargs)
                    
class Withdrawal(models.Model):
    user = models.ForeignKey(
        User,
        related_name='withdrawals',
        on_delete=models.PROTECT
    )
    slp_token = models.ForeignKey(
        SLPToken,
        related_name='withdrawals',
        on_delete=models.PROTECT,
        null=True
    )
    address = models.CharField(max_length=60)
    transaction_id = models.CharField(max_length=70, blank=True)
    amount = models.FloatField()
    date_created = models.DateTimeField(default=timezone.now)
    date_started = models.DateTimeField(null=True, blank=True)
    date_completed = models.DateTimeField(null=True, blank=True)
    date_failed = models.DateTimeField(null=True, blank=True)
    withdraw_all = models.BooleanField(default=False)

    @property
    def amount_with_fee(self):
        if self.withdraw_all:
            percentage_fee = 0
        else:
            percentage_fee = self.slp_token.withdrawal_percentage_fee
        return self.amount + (self.amount * percentage_fee)

    @property
    def fee(self):
        if self.withdraw_all:
            percentage_fee = 0
        else:
            percentage_fee = self.slp_token.withdrawal_percentage_fee
        return self.amount * percentage_fee


class TelegramGroup(models.Model):
    chat_id = models.CharField(max_length=50, unique=True)
    chat_type = models.CharField(max_length=20)
    title = models.CharField(max_length=70)
    post_to_spicefeed = models.BooleanField(default=True)
    disable_tipping = models.BooleanField(default=False)
    last_privacy_setting = models.DateTimeField(
        default=timezone.now
    )
    privacy_set_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True
    )
    users = models.ManyToManyField(
        User,
        related_name='telegramgroups'
    )
    date_created = models.DateTimeField(default=timezone.now, null=True)
    transferred = models.BooleanField(default=False)
    pillory_time = models.FloatField(default=settings.DEFAULT_MUTE_TIME)
    pillory_fee = models.FloatField(default=settings.INITIAL_MUTE_PRICE)
    settings = JSONField(default=dict)
    profile_pic_url = models.CharField(max_length=500, null=True, default="")
    aws_profile_pic_url = models.CharField(max_length=500, null=True, default="")
    profile_pic_file_id = models.CharField(max_length=60, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['chat_id'])
        ]

    def serialize_hook(self, hook):
        # optional, there are serialization defaults
        # we recommend always sending the Hook
        # metadata along for the ride as well
        data = {
            'hook': hook.dict(),
            'data': {
                'chat_id': self.chat_id,
                'chat_type': self.chat_type,
                'title': self.title,                                
                'post_to_spicefeed': self.post_to_spicefeed,
                'users': self.get_user_list()
            }
        }
        
        self.transferred =True
        return data

    def get_user_list(self):
        users = self.users.all()
        response = []

        for user in users:
            response.append(user.get_user_id)

        return response


    def clean(self):
        self.transferred = True

    def save(self, *args, **kwargs):
        user = djUser.objects.first()
        if user is not None:
            self.user = user
        super(TelegramGroup, self).save(*args, **kwargs)


class LastGroupActivity(models.Model):
    group = models.ForeignKey(
        TelegramGroup,
        related_name='last_group_activities',
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        User,
        related_name='last_group_activities',
        on_delete=models.CASCADE
    )
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [['group', 'user']]


class Content(models.Model):
    source = models.CharField(max_length=20, default='telegram')
    tip_amount = models.FloatField()
    sender = models.ForeignKey(
        User,
        related_name='tips_sent',
        on_delete=models.PROTECT
    )
    recipient = models.ForeignKey(
        User,
        related_name='tips_received',
        on_delete=models.PROTECT
    )
    details = JSONField(default=dict)
    post_to_spicefeed = models.BooleanField(default=True)
    date_created = models.DateTimeField(default=timezone.now)
    recipient_content_id = JSONField(default=dict, null=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        related_name='children',
        on_delete=models.PROTECT,
        default=None,
        blank=True
    )

    total_tips = models.FloatField(default=0, null=True)
    last_activity = models.DateTimeField(default=timezone.now)
    transferred = models.BooleanField(default=False)
    slp_token = models.ForeignKey(
        SLPToken,        
        on_delete=models.PROTECT,
        null=True
    )

    class Meta:
        indexes = [
            models.Index(fields=['tip_amount'])
        ]

    def serialize_hook(self, hook):        
        if self.parent:
            parent_id = self.parent.id
        else:
            parent_id = None
        if self.slp_token:
            slp = {
                'name': self.slp_token.name,
                'token_id': self.slp_token.token_id,
                'emoji': self.slp_token.emoji
            }
        else:
            # This is for Contents with no SLP Token
            slptoken = SLPToken.objects.first()
            slp = {
                'name': slptoken.name,
                'token_id': slptoken.token_id,
                'emoji': slptoken.emoji
            }
        data = {
            'hook': hook.dict(),
            'data': {
                'content_id': self.id,
                'parentid': parent_id,
                'source': self.source,
                'tip_amount': self.tip_amount,
                'sender': self.sender.get_user_id,
                'recipient': self.recipient.get_user_id,
                'details': self.details,
                'date_created': self.date_created,
                'last_activity': self.last_activity,
                'recipient_content_id': self.recipient_content_id,
                'total_tips': self.total_tips,
                'post_to_spicefeed': self.post_to_spicefeed,
                'slp': slp
            }
        }
        self.transferred = True
        return data

    def get_media_url(self):
        media_url = None
        if self.source == 'telegram':
            file_id = None
            msg_keys = self.details['message']['reply_to_message'].keys()
            media_types = ('photo', 'sticker', 'animation', 'video', 'video_note', 'voice', 'document')
            for name in media_types:
                if name in msg_keys:
                    if name == 'photo':
                        file_id = self.details['message']['reply_to_message']['photo'][-1]['file_id']
                    else:
                        try:
                            file_id = self.details['message']['reply_to_message'][name]['file_id']
                        except KeyError:
                            file_id = None
                    break
            try:
                if file_id:
                    qs = Media.objects.filter(file_id=file_id)
                    if qs.exists():
                        media_obj = qs.first()
                        media_url = media_obj.url
                        if qs.count() > 1:
                            msg = 'Duplicated media! -- check this file id : %s' % file_id
                            logger.info(msg)
            except Media.DoesNotExist:
                pass
        elif self.source == 'twitter':
            try:
                media_url = self.details['replied_to']['media'][0]['media_url']
            except KeyError:
                pass
        return media_url

    def clean(self):
        self.transferred = True

    def save(self, *args, **kwargs):
        user = djUser.objects.first()
        if user is not None:
            self.user = user
        super(Content, self).save(*args, **kwargs)



class Response(models.Model):
    response_type= models.CharField(max_length=50)
    content = models.ForeignKey(
        Content,
        related_name='messages',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    body = JSONField(default=dict, unique=True)
    date_created = models.DateTimeField(default=timezone.now)
    botReplied = models.BooleanField(default=False)

class Transaction(models.Model):
    transaction_hash = models.CharField(max_length=200, unique=True)
    user = models.ForeignKey(
        User,
        related_name='transactions',
        on_delete=models.PROTECT
    )
    # only gets populated when transaction is not a private spicebot command
    group = models.ForeignKey(
        TelegramGroup,
        related_name='transactions',
        on_delete=models.PROTECT,
        null=True
    )
    slp_token = models.ForeignKey(
        SLPToken,
        related_name='transactions',
        on_delete=models.PROTECT,
        null=True
    )
    amount = models.FloatField()
    transaction_type = models.CharField(max_length=50)
    operation = models.CharField(max_length=50, default='')
    date_created = models.DateTimeField(default=timezone.now)
    running_balance = models.FloatField(default=0)
    remark = models.TextField()
    connected_transactions = ArrayField(
        models.CharField(max_length=200),
        default=list
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['transaction_hash']),
            models.Index(fields=['transaction_type'])
        ]

    def save(self, *args, **kwargs):
        with trans.atomic():
            user_txns = Transaction.objects.select_for_update().filter(
                user=self.user,
                slp_token=self.slp_token
            )
            balance = 0
            if user_txns.exists():
                user_txns = user_txns.order_by('date_created')
                balance = user_txns.last().running_balance

            if self.transaction_type == 'Incoming':
                balance += self.amount
            elif self.transaction_type == 'Outgoing':
                balance -= self.amount
            self.running_balance = balance

        super(Transaction, self).save(*args, **kwargs)


class Deposit(models.Model):
    user = models.ForeignKey(
        User,
        related_name='deposits',
        on_delete=models.PROTECT
    )
    slp_token = models.ForeignKey(
        SLPToken,        
        related_name='deposits',
        on_delete=models.PROTECT,
        null=True
    )
    transaction_id = models.CharField(max_length=64, null=True, blank=True)
    spentIndex = models.IntegerField(default=0)
    amount = models.FloatField()
    notes = models.TextField(blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    date_swept = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=100, null=True, blank=True)
    date_processed = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'transaction_id', 'spentIndex')

    def __str__(self):
        return 'Deposit: %s SPICE' % self.amount

class BitcoinBlockHeight(models.Model):
    number = models.IntegerField()
    processed = models.BooleanField(default=False)


class Media(models.Model):
    content = models.ForeignKey(
        Content,
        on_delete=models.CASCADE,
        related_name='media',
        null=True
    )
    file_id = models.CharField(max_length=500)
    url = models.CharField(max_length=500)
    aws_url = models.CharField(max_length=500)
    transferred = models.BooleanField(default=False)

    def serialize_hook(self, hook):
        # optional, there are serialization defaults
        # we recommend always sending the Hook
        # metadata along for the ride as well
        if self.content:
            content = self.content.recipient_content_id
        else:
            content = None
            
        data = {
            'hook': hook.dict(),
            'data': {
                'recipient_content_id': content, 
                'file_id': self.file_id,
                'url': self.aws_url                
            }
        }     
        logger.info(data)
        self.transferred = True
        return data   

    class Meta:
        verbose_name_plural = 'Media'

    def clean(self):
        self.transferred = True

    def save(self, *args, **kwargs):
        user = djUser.objects.first()
        if user is not None:
            self.user = user
        super(Media, self).save(*args, **kwargs)

class FaucetDisbursement(models.Model):

    ip_address = models.CharField(max_length=30)
    ga_cookie = models.CharField(max_length=50, null=True, blank=True)
    slp_address = models.CharField(max_length=60)
    transaction_id = models.CharField(max_length=70, blank=True)
    amount = models.FloatField()
    date_created = models.DateTimeField(default=timezone.now)
    date_completed = models.DateTimeField(null=True)
    token = models.ForeignKey(SLPToken, null=True, related_name="faucet_disbursement", on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = SLPToken.objects.get(name='SPICE')
        super(FaucetDisbursement,self).save(*args, **kwargs)

class Rain(models.Model):
    sender = models.ForeignKey(
        User,
        related_name='sender',
        on_delete=models.PROTECT
    )
    slp_token = models.ForeignKey(
        SLPToken,
        related_name='rains',
        on_delete=models.PROTECT,
        null=True
    )
    recepients = models.ManyToManyField('User')
    rain_amount = models.FloatField()
    date_created = models.DateTimeField(default=timezone.now)
    message = models.TextField()
    message_id = models.CharField(max_length=50, null=True)

    def get_recipients(self):
        return "\n".join([r.telegram_display_name for r in self.recepients.all()])


class ErrorLog(models.Model):
    logs = JSONField()
    origin = models.CharField(max_length=50)
    datetime = models.DateTimeField(default=timezone.now)
    last_notified = models.DateTimeField(default=timezone.now)

class WeeklyReport(models.Model):
    date_generated = models.DateTimeField(default=timezone.now)
    report = JSONField(default=None)
    

class Mute(models.Model):
    target_user = models.ForeignKey(
        User,
        related_name='mutes',
        on_delete=models.PROTECT
    )
    group = models.ForeignKey(
        TelegramGroup,
        related_name='mutes',
        on_delete=models.PROTECT
    )
    remaining_unmute_fee = models.FloatField(default=0.0)
    remaining_fee = models.FloatField(default=settings.INITIAL_MUTE_PRICE)
    base_fee = models.FloatField(default=settings.INITIAL_MUTE_PRICE)
    next_fee = models.FloatField(default=0.0)
    count = models.IntegerField(default=0)
    is_muted = models.BooleanField(default=False)
    is_being_unmuted = models.BooleanField(default=False)
    date_started = models.DateTimeField(default=None, null=True, blank=True)
    duration = models.FloatField(default=settings.DEFAULT_MUTE_TIME)
    # static_duration = models.FloatField(default=0.0)
    fee_changed = models.BooleanField(default=False)
    contributors = models.ManyToManyField(
        User,
        related_name='mutes_contributed'
    )

    def get_fee(self):
        count = self.count
        price = self.base_fee
        while count > 0:
            price = price - (price * settings.MUTE_DIMINISHING_RATE)
            count = count - 1

        price = round(price)
        if price < 1:
            price = 1

        return price

    @property
    def unmute_fee(self):
        price = self.get_fee()
        price += price * settings.UNMUTE_INTEREST
        price = round(price)
        return price


class LastTelegramMessage(models.Model):
    user = models.ForeignKey(
        User,
        related_name='last_message',
        on_delete=models.PROTECT
    )
    telegram_group = models.ForeignKey(
        TelegramGroup,
        on_delete=models.PROTECT
    )
    last_message_timestamp = models.DateTimeField(default=timezone.now, null=True, blank=True)    


class Metric(models.Model):
    user_metrics = JSONField(default=dict)
    # total_users = models.IntegerField()
    # total_active_users = models.IntegerField()
    # total_new_users = JSONField()
    group_metrics = JSONField(default=dict)
    # total_groups = models.IntegerField()
    # total_active_groups = models.IntegerField()
    # top_ten_active_groups = JSONField()
    # total_new_groups = JSONField()
    withdrawal_metrics = JSONField(default=dict)
    # total_withdrawals_count = models.IntegerField()
    # total_withdrawals_amount = models.FloatField()
    # avg_withdrawals_amount = models.FloatField()
    # total_successful_withdrawals = models.IntegerField()
    # total_failed_withdrawals = models.IntegerField()
    # earnings = JSONField()
    deposit_metrics = JSONField(default=dict)
    # total_deposits_count = models.IntegerField()
    # total_deposits_amount = models.FloatField()
    # avg_deposits_amount = models.FloatField()
    # total_big_deposits_count = models.IntegerField()
    # total_big_deposits_amount = models.FloatField()
    # avg_big_deposits_amount = models.FloatField()
    tip_metrics = JSONField(default=dict)
    # total_tips_count = models.IntegerField()
    # total_tips_amount = models.FloatField()
    # avg_tips_amount = models.FloatField()
    # earnings = JSONField()
    rain_metrics = JSONField(default=dict)
    # total_rains_count = models.IntegerField()
    # total_rains_amount = models.FloatField()
    # avg_rains_amount = models.FloatField()
    game_metrics = JSONField(default=dict)
    # jankenbot_avg_bet = models.FloatField()
    # jankenbot_earnings = JSONField()
    # jankenbot_bets_count = JSONField()
    # wagerbot_avg_bet = models.FloatField()
    # wagerbot_earnings = models.FloatField()
    # wagerbot_bets_count = JSONField()
    # house_remaining_spice = models.FloatField()
    date_recorded = models.DateTimeField(default=timezone.now, null=True, blank=True)

    

