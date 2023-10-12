import emoji
import requests
import logging
import random
import json
import redis
import os
import re
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, Q
from datetime import timedelta
from django.db import transaction as trans
from django.db.models.functions import Lower
from django.db.models.query import QuerySet

from main.models import (
    User,
    Content,
    Transaction,
    Withdrawal,
    TelegramGroup,
    Rain,
    Mute,
    Subscriber,
    LastTelegramMessage,
    SLPToken,
    LastGroupActivity
)
from main.tasks import (
    send_telegram_message,
    transfer_spice_to_another_acct,
    withdraw_spice_tokens,
    restrict_user
)

from main.utils.account import create_transaction, get_balance, swap_related_transactions
from main.utils.miscellaneous_pattern import Misc_Pattern
from main.utils.responses import (
    get_response, 
    get_maintenance_response,
    get_slp_token_list,
    get_pillory_faq,
    get_tip_response,
    get_rain_response,
    get_withdraw_response
)
from main.utils import exchange_stats
from django.db import IntegrityError
from constance import config
from .telegram_faucet import Faucet

from bridge.models import Token, SwapRequest
from bridge.utils.addresses import generate_slp_address

logger = logging.getLogger(__name__)


def get_chat_admins(chat_id):
    data = {
        "chat_id": chat_id
    }
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/getChatAdministrators", data=data
    )
    admins = []
    if response.status_code == 200:
        admins = [x['user']['id'] for x in response.json()['result']]
    return admins

def get_edited_message(chat_id, text, parse_mode):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/editMessageText", data=data
    )
    message = text
    if response.status_code == 200:
        message = response.json()['result']
    return message

def get_chat_members_count(chat_id):
    data = {
        "chat_id": chat_id
    }
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/getChatMembersCount", data=data
    )
    count = 0
    if response.status_code == 200:
        count = response.json()['result']
    return count

def get_chat_member(chat_id, user_id):
    data = {
        "chat_id": chat_id,
        "user_id": user_id
    }
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/getChatMember", data=data
    )
    rsp = None
    if response.status_code == 200:
        rsp = response.json()
    return rsp


def get_int_or_float(amount, check_zero=False):
    if type(amount) is float:
        if amount.is_integer():
            return int(amount)

    if check_zero:
        if round(amount) == 0:
            return 1
        else:
            return round(amount)
    return amount

def get_amount_str(amount):
    return format(amount, ",")

def get_formatted_time(minutes):
    time = minutes
    unit = 'minutes'

    if minutes >= 60 and minutes < 1440:
        time = minutes / 60
        unit = 'hours'
    elif minutes >= 1440:
        time = minutes / 1440
        unit = 'days'
    
    if time <= 1:
        unit = unit[:-1]
    time = get_int_or_float(time)
    time = get_amount_str(time)
    return time, unit


def sec_to_remaining_time(seconds):   
    day = seconds // (24 * 3600) 
    seconds = seconds % (24 * 3600) 
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    sec = seconds

    result = ''
    formatted_strings = [
        f"{day} day",
        f"{hour} hr",
        f"{minutes} min",
        f"{seconds} sec"
    ]

    for string in formatted_strings:
        time = int(string.split()[0])
        if time != 0:
            string += "s" if time > 1 else ""
            result += f"{string} "

    return result
        


class TelegramBotHandler(object):

    def __init__(self, data={}, **options):
        self.data = data
        self.token_name = options.get("token_name", "")
        self.tip_amount = options.get("tip_amount", 0)
        self.update_id = None
        self.message = ''
        self.reply_markup = None
        self.dest_id = None
        self.tip = False  
        self.rain_username_display_limit = 10
        
        self.tip_with_emoji =False
        self.final_amount_str = "0"
        self.other_private_patterns = [
            'buy\s+\d+\s+\w+',
            'yes'
        ]
        self.amt_with_commas_regex = '(((\d*[.]\d+)|(\d+))|((\d{1,3})(\,\d{3})+(\.\d+)?))'
        self.wallet_address = '(simpleledger:.*|bitcoincash:.*)'

        self.show_list_regex = '^((pillory|mute)\s+list)$'
        self.pillory_switch_regex = '^(pillory\s+(on|off))$'
        self.pillory_regex = f'^((pillory|unmute)\s+@[\w_]+\s+{self.amt_with_commas_regex}\s+spice)$'
        # self.set_pillory_time_regex = f'^(set\s+pillory\s+@[\w_]+\s+{self.amt_with_commas_regex}\s+(mins|min|hrs|hr|days|day))$'
        self.set_pillory_amt_regex = f'^(set\s+pillory\s+@[\w_]+\s+{self.amt_with_commas_regex}\s+spice)$'
        self.set_default_pillory_regex = f'^(default\s+pillory\s+{self.amt_with_commas_regex}\s+spice)$'
        self.set_default_pillory_time_regex = f'^(default\s+pillory\s+{self.amt_with_commas_regex}\s+(min|mins|hrs|hr|days|day))$'
        self.show_default_pillory_regex = '^(default\s+pillory\s+fee)$'
        self.show_default_pillory_time_regex = '^(default\s+pillory\s+time)$'
        self.pillory_emojis_regex = self.generate_pillory_emojis_regex()

        self.throw_pillory_regex = f'^(throw\s+{self.pillory_emojis_regex}\s*@[\w_]+)$'
        self.clear_pillory_regex = f'^(clear\s+pillory\s+@[\w_]+)$'

        self.unmute_regex = '^(unmute\s+@[\w_]+)$'
        self.UP_ARROW = '\U00002b06' # up arrow
        self.DOWN_ARROW = '\U00002b07' # down arrow

        self.mute = 'mute'
        self.unmute = 'unmute'
        self.prolong = 'prolong'
        self.lessen = 'lessen'
        self.slp_token_regex = self.generate_token_regex()
        self.switch_token_tipping_regex = f'^({self.slp_token_regex}\s+tipping\s+(on|off))$'
        self.reply_markup= {
            "inline_keyboard": [
                [
                    {'text': 'See full list', 'callback_data': ''}
                ]
            ]
        }

        self.faucet_regex = '^tap\s+faucet\s+\w+$'
        self.advertisement = False
        self.advertisement_message = config.AD_TEXT
        self.advertisement_frequency = config.AD_FREQUENCY
        self.for_delisting = []

    
    def generate_pillory_emojis_regex(self):
        pillory_emojis = list(settings.ALLOWED_PILLORY_EMOJIS.keys())
        unmute_emojis = list(settings.ALLOWED_UNMUTE_EMOJIS.keys())
        throw_emojis = pillory_emojis + unmute_emojis
        regex = ""

        for emoji in throw_emojis:
            if emoji == throw_emojis[0]:
                regex = emoji
            else:
                regex += f"|{emoji}"
        
        regex = f"({regex})"
        return regex

    def generate_token_regex(self):
        tokens = SLPToken.objects.filter(
            Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
        )
        
        token_names = [t.name.lower() for t in tokens]
        regex = f"({token_names[0]}"

        for token in token_names:
            if token != token_names[0]:
                regex += f"|{token}"
                
        return f"{regex})"

    @staticmethod
    def get_name(details):
        name = details['first_name']
        try:
            name += ' ' + details['last_name']
        except KeyError:
            pass
        if len(name) > 20:
            name = name[0:20]
        return name

    def validate_address(self, text):
        is_valid = False
        if len(text) == 55 and text.startswith('simpleledger:'):
            is_valid = True
        return is_valid

    def rain(self, user_id, text, group_id, rain_from_mute=False):
        if Rain.objects.filter(message_id=self.data['message']['message_id']).exists(): return ''

        user = User.objects.get(id=user_id)

        if user.frozen:
            return self.get_frozen_response(user.get_username, '', False)

        given = text.lower().strip(' ')

        total_users = 0
        total_amount = 0
        pof = 0
        each_users = False
        message = ''
        
        scenario_1 = re.compile(f'^(rain\s+\d+\s+people+\s+{self.amt_with_commas_regex}\s+{self.slp_token_regex}\s+each\s+pof\s+(?:[0-6]|0[0-6]|6)[\/](?:[1-5]|0[1-5]|5))$')
        scenario_2 = re.compile(f'^(rain\s+\d+\s+people+\s+{self.amt_with_commas_regex}\s+{self.slp_token_regex}\s+total\s+pof\s+(?:[0-6]|0[0-6]|6)[\/](?:[1-5]|0[1-5]|5))$')
        scenario_3 = re.compile(f'^(rain\s+\d+\s+people+\s+{self.amt_with_commas_regex}\s+{self.slp_token_regex}\s+each)$')
        scenario_4 = re.compile(f'^(rain\s+\d+\s+people+\s+{self.amt_with_commas_regex}\s+{self.slp_token_regex}\s+total)$')
        scenario_5 = re.compile(f'^(rain\s+\d+\s+people+\s+{self.amt_with_commas_regex}\s+{self.slp_token_regex})$')

        if not scenario_1.match(given) and not scenario_2.match(given) and not scenario_3.match(given) and not scenario_4.match(given) and not scenario_5.match(given):
            return message

        token_in_msg = given.split()[4]
        slp_token = SLPToken.objects.get(name__iexact=token_in_msg)
        if not slp_token.publish and user.telegram_id not in slp_token.allowed_devs:
            message = "Sorry this feature is not yet available."
            return message

        group = TelegramGroup.objects.get(id=group_id)
        users = group.last_group_activities.all()

        within_24hours = timezone.now() - timedelta(hours=24)
        users = users.filter(
            timestamp__gt=within_24hours,
            user__telegram_id__isnull=False,
            user__telegram_user_details__is_bot=False,
            user__frozen=False,
        ).exclude(user_id=user.id)

        # if users:            
        #     users = users.exclude(
        #         telegram_user_details__username=settings.MUTE_MANAGER_USERNAME
        #     )

        #     # include users that are active in the group in the past 24 hrs
        #     last_24_hrs = timezone.now() - timedelta(hours=24)
        #     users = users.filter(
        #         last_message__telegram_group=group,
        #         last_message__last_message_timestamp__gt=last_24_hrs
        #     )
        #     # exclude users that are currently muted
        #     users = users.exclude(
        #         mutes__group=group,
        #         mutes__is_muted=True
        #     )
            
        text_list = filter(None, given.split(' '))
        text_list = [x for x in text_list if x]

        try:
            total_users = text_list[text_list.index('people')-1]
            total_amount = text_list[text_list.index(token_in_msg)-1].replace(',', '')
        except ValueError:
            return message

        rain_max_people = 30
        if int(total_users) > rain_max_people:
            message = f"You can only rain {slp_token.emoji} {slp_token.name} {slp_token.emoji} to maximum of <b>{rain_max_people}</b> people"
            return message

        #check scenarios
        if scenario_1.match(given):
            pof = text_list[text_list.index('pof')+1][0]
            each_users = True

            #filter user
            users = users.filter(
                user__pof__pof_rating__gte=float(pof)
            )

            users = self.get_random_users(users, total_users)
        elif scenario_2.match(given):
            pof = text_list[text_list.index('pof')+1][0]
            #filter user
            users = users.filter(
                user__pof__pof_rating__gte=float(pof)
            )

            users = self.get_random_users(users, total_users)
        elif scenario_3.match(given):
            each_users = True
            #filter user
            users = self.get_random_users(users, total_users)
        elif scenario_4.match(given):
            #filter user
            users = self.get_random_users(users, total_users)
        elif scenario_5.match(given):
            #filter_user
            users = self.get_random_users(users, total_users)
        else:
            return ''

        if len(users) == 0:
            message = f'Nobody received any {slp_token.name}'
        else:
            

            if each_users:
                msg_total = float(total_amount) * float(total_users)
                amount_sent = float(total_amount) * len(users)
                amount_received = float(total_amount)
                temp = 'each'
            else:
                msg_total = float(total_amount)
                amount_sent = float(total_amount)
                amount_received = float(total_amount) / len(users)
                temp = 'in total'

            #check rain amount
            from_name = user.telegram_display_name or user.telegram_username
            balance = get_balance(user_id, slp_token.token_id)

            if balance < msg_total:
                message = f"<b>@{from_name}</b>, you don't have enough {slp_token.emoji} {slp_token.name} {slp_token.emoji}!"
                return message

            if msg_total < slp_token.min_rain_amount and not rain_from_mute:
                amt = get_int_or_float(slp_token.min_rain_amount)
                amt = get_amount_str(amt)
                message = f'Hi! The minimum amount needed to invoke rain is {amt} {slp_token.emoji} {slp_token.name} {slp_token.emoji}. Please try again.'
                return message
                            
            
            # Save rain
            rain = Rain(
                sender=user,
                rain_amount=amount_sent,
                message=text,
                message_id=self.data['message']['message_id'],
                slp_token=slp_token
            )
            rain.save()
            # Transactions
            transaction_hash = f"{user.id}-{rain.id}-{self.dest_id}-{slp_token.name}-{amount_sent}"
            created, sender_thash = create_transaction(
                user.id,
                amount_sent,
                'Outgoing',
                slp_token.id,
                settings.TXN_OPERATION['RAIN'],
                transaction_hash=transaction_hash,
                chat_id=self.dest_id
            )
            self.compute_POF(user)
            users_str = ''
            recipient_thashes = []
            first = True
            counter = 0
            diff = len(users) - self.rain_username_display_limit
            for u in users:
                transaction_hash = f"{u.id}-{rain.id}-{self.dest_id}-{slp_token.name}-{amount_received}"
                created, recipient_thash = create_transaction(
                    u.id,
                    amount_received,
                    'Incoming',
                    slp_token.id,
                    settings.TXN_OPERATION['RAIN'],
                    transaction_hash=transaction_hash,
                    connected_transactions=[sender_thash],
                    chat_id=self.dest_id
                )
                recipient_thashes.append(recipient_thash)
                rain.recepients.add(u)
                self.compute_POF(u)
                if counter < self.rain_username_display_limit:
                    if first:
                        users_str += u.telegram_display_name
                        first = False
                    else:
                        users_str += ', ' + u.telegram_display_name
                counter += 1

            if len(users) > self.rain_username_display_limit:
                self.reply_markup['inline_keyboard'][0][0]['callback_data'] = f"rain:{rain.id}"
            if diff > 1:
                users_str += f' and other {diff} users.'
            elif diff == 1:    
                users_str += f' and one more user.'


            t_qs = Transaction.objects.filter(transaction_hash=sender_thash)
            t_qs.update(connected_transactions=recipient_thashes)
            
            total_amount = float(total_amount)
            total_amount = get_int_or_float(total_amount)
            total_amount = get_amount_str(total_amount)


            if rain_from_mute:
                message = f"I have rained the collected <b>{total_amount}</b> {slp_token.emoji} <b>{slp_token.name}</b> {slp_token.emoji} to this group, specifically: <b>{users_str}</b>"
            else:
                message = f'<b>{user.telegram_display_name}</b> just rained {total_amount} {slp_token.emoji} {slp_token.name} {slp_token.emoji} {temp} to: <b>{users_str}</b>'


        return message


    def get_random_users(self, users, total_users):
        # users = users.order_by('-timestamp')[:int(total_users * 3)]  # get a sampling from this group
        # converted users queryset to list since sliced queryset cannot be ordered_by again, and we don't wanna use a loop for that
        users_list = [x.user for x in users]
        random.shuffle(users_list)
        return list(set(users_list[:int(total_users)]))


    def compute_POF(self, user):
        received = Content.objects.filter(recipient=user).aggregate(Sum('tip_amount'))
        tipped = Content.objects.filter(sender=user).aggregate(Sum('tip_amount'))

        received_amount_full = received['tip_amount__sum']
        tipped_amount = tipped['tip_amount__sum']
        if not received['tip_amount__sum']:
            received_amount_full = 1 # Set to 1 to avoid division by zero error
        if not tipped['tip_amount__sum']:
            tipped_amount = 0

        received_amount_half = received_amount_full / 2
        pof_percentage = (tipped_amount/received_amount_full)*100
        pof_rating = ((tipped_amount/received_amount_half)*100) / 20

        if pof_rating > 5:
            pof_rating = 6

        user.pof = {'pof_rating': pof_rating, 'pof_percentage': pof_percentage}
        user.save()
        
        if self.advertisement_message:
            self.advertisement = True
        
        return round(pof_percentage), round(pof_rating)

    def handle_tipping(self, message, text, with_pof=False):
        sender_telegram_id = message['from']['id']
        sender, created = User.objects.get_or_create(
            telegram_id=sender_telegram_id
        )
        group, _ = TelegramGroup.objects.get_or_create(chat_id=message["chat"]["id"])

        # if created or sender.telegram_user_details != message['from']:
        #     # Update user details, only when changes are made
        #     sender.telegram_user_details = message['from']
        #     sender.save()

        self.from_username = sender.telegram_display_name or sender.telegram_username
        self.to_username = None
        to_firstname = None

        recipient = None
        recipient_content_id = None
        content_id_json = None
        parent = None
        try:
            if not message['reply_to_message']['from']['is_bot']:
                self.recipient_telegram_id = message['reply_to_message']['from']['id']
                recipient, created = User.objects.get_or_create(
                    telegram_id=self.recipient_telegram_id
                )

                if created or recipient.telegram_user_details != message['reply_to_message']['from']:
                    recipient.telegram_user_details = message['reply_to_message']['from']
                    recipient.save()

                self.to_username = recipient.telegram_display_name or recipient.telegram_username
                group.users.add(recipient)
                group.save()

                if recipient.frozen:
                    self.message = self.get_frozen_response(recipient.get_username, 'tip')
                    self.recipient = None
                    self.tip = False
                    return

            to_firstname = message['reply_to_message']['from']['username']
        except KeyError:
            pass

        recipient_content_id = {
            'chat_id': message['chat']['id'],
            'message_id': message['reply_to_message']['message_id']
        }

        content_id_json = json.dumps(recipient_content_id)

        # Getting parent tipper
        content = Content.objects.filter(parent=None, recipient_content_id=content_id_json)
        if content.exists():
            content = content.first()
            # content = Content.objects.filter(parent=None, recipient_content_id=content_id_json).first()
            parent = content        

        self.sender = sender
        self.recipient = recipient
        self.parent = parent
        self.recipient_content_id = content_id_json
        try:
            
            # Check if to_username is not equal to None
            if  self.to_username and to_firstname != settings.TELEGRAM_BOT_USER and self.from_username != self.to_username:
                env = settings.DEPLOYMENT_INSTANCE.strip(' ').lower()

                slp_token = SLPToken.objects.filter(
                    Q(name__iexact=self.token_name),
                    Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                ) 
                if slp_token.exists():
                    slp_token = slp_token.first()
                else:
                    self.tip = False
                    return 
                if self.tip_amount == 0:
                    msc_pattern = Misc_Pattern()
                    self.message = msc_pattern.check_lightning(text)
                    self.tip = False
                # is_string = isinstance(self.tip_amount, str)
                # if is_string: 
                #     self.message = self.tip_amount
                #     self.tip_amount = 0
                                       
                                        
                one_satoshi = 0.00000001
                if self.tip_amount >= one_satoshi:
                    _proceed = True
                    try:
                        group.settings['token_tipping_status'][slp_token.name]
                    except KeyError as exc:
                        _proceed = False
                    
                    if _proceed and not group.settings['token_tipping_status'][slp_token.name]:
                        # Commented out the message below, it can be annoying
                        # self.message = f"{slp_token.name} {slp_token.emoji} tipping is currently disabled."
                        self.tip = False
                    else:
                        if not slp_token.publish and (str(sender.telegram_id) not in slp_token.allowed_devs):
                            self.message = f"{slp_token.name} {slp_token.emoji} tipping is currently unavailable."
                            self.tip = False
                        # Check if user has enough balance to give a tip
                        with trans.atomic():
                            balance = get_balance(sender.id, slp_token.token_id)
                            self.tip_fee = 0
                            
                            if self.tip_amount >= slp_token.tip_threshold and balance >= self.tip_amount:
                                self.tip_fee = round(slp_token.tip_percentage_fee * self.tip_amount, 8)
                                
                            if balance >= self.tip_amount + self.tip_fee:

                                if self.tip_amount > 1:
                                    amount = '{:,}'.format(round(self.tip_amount, 8))
                                else:
                                    amount = '{:,.8f}'.format(round(self.tip_amount, 8))
                                amount_str = str(amount)
                                if amount_str.endswith('.0'):
                                    amount_str = amount_str[:-2]
                                if '.' in amount_str:
                                    amount_str = amount_str.rstrip('0')
                                if amount_str.endswith('.'):
                                    amount_str = amount_str[:-1]
                                if 'e' in amount_str:
                                    amount_str = "{:,.8f}".format(float(amount_str))
                                self.final_amount_str = amount_str
                                #get pof
                                self.pct_sender, self.pof_sender = self.compute_POF(sender)
                                self.pct_receiver, self.pof_receiver = self.compute_POF(recipient)
                            else:
                                if not self.tip_with_emoji:
                                    self.message = f"<b>@{self.from_username}</b>, you don't have enough {slp_token.emoji} {slp_token.name} {slp_token.emoji}!"

                                    if self.tip_fee != 0:
                                        threshold = get_int_or_float(slp_token.tip_threshold)
                                        threshold = format(threshold, ",")
                                        total_payment = format(round(self.tip_amount + self.tip_fee, 8), ",")
                                        perc_fee = slp_token.tip_percentage_fee * 100
                                        perc_fee = get_int_or_float(perc_fee)

                                        self.message += f"\n\nTipping with {slp_token.name} with an amount greater or equal to <b>{threshold} {slp_token.name}</b>, "
                                        self.message += f"requires a fee equivalent to {perc_fee}% of the amount tipped.\n\n<b>Total payment needed for your tip = {total_payment} {slp_token.name} {slp_token.emoji}</b>"

                                self.tip = False
                else:
                    self.tip = False

            # Prevent users from sending tips to bot
            elif to_firstname == settings.TELEGRAM_BOT_USER:
                if message['chat']['type']  == 'private':
                    self.message = get_response('tip')
                self.tip = False
        except ValueError:
            pass

    def delisted(self, token):
        if token.date_delisted:
            if token.date_delisted < timezone.now():
                return True
        return False
    
    def custom_private_pattern(self, text):
        for pattern in self.other_private_patterns:
            if re.findall(pattern, text): return True
        return False

    def transfer_spice(self, text, sender_id):
        text = re.sub('\s+', ' ', text)
        words = text.split(' ')
        recipient_source = words[0]
        recipient_username = words[1].replace('@', '')
        transfer_amount = float(words[2].replace(',', ''))

        recipient = User.objects.none()
        if recipient_source == 'twitter':
            recipient = User.objects.filter(twitter_user_details__screen_name=recipient_username)
        elif recipient_source == 'reddit':
            recipient = User.objects.filter(reddit_user_details__username=recipient_username)


        if recipient.exists():
            recipient = recipient.first()
            self.message = transfer_spice_to_another_acct(sender_id, recipient.id, transfer_amount)
        else:
            self.message = 'Oops! The account you want to transfer to does not exist! Try another username.'

    def process_data(self):
        self.text = ''
        amount = None
        addr = None
        t_message = {}
        entities = []
        rained = False
        mentioned_bot = False
        
        if 'message' in self.data.keys():
            logger.info(f"Data: {self.data}")
            self.update_id = self.data['update_id']
            t_message = self.data["message"]
            self.dest_id = t_message["chat"]["id"]
            chat_type = t_message['chat']['type']
            from_id = t_message['from']['id']

            try:
                self.text = t_message['text']
            except KeyError:
                pass

            user, created = User.objects.get_or_create(
                telegram_id=from_id
            )
            # only save user details when changes are made
            if created or user.telegram_user_details != t_message['from']:
                user.telegram_user_details = t_message['from']
            # track user's last private message to bot
            if chat_type == 'private':
                user.last_private_message = timezone.now()

            # Record user last activity
            user.last_activity = timezone.now()
            user.save()

            # Create chat/group if doesn't exist yet
            if chat_type != 'private':
                try:
                    group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                    group.users.add(user)
                    group.save()
                except IntegrityError as exc:
                    groups = TelegramGroup.objects.filter(chat_id=t_message["chat"]["id"])
                    group_id = groups.first().id
                    group = TelegramGroup.objects.get(id=group_id)
                    group.users.add(user)
                    group.save()
                    if groups.count > 1:
                        TelegramGroup.objects.exclude(id=group_id).delete()
                    else:
                        raise IntegrityError(exc)
                except TelegramGroup.DoesNotExist:
                    group, created = TelegramGroup.objects.get_or_create(
                        chat_id=t_message["chat"]["id"]
                    )
                    if created:
                        group.title = t_message["chat"]["title"]
                        group.chat_type = t_message["chat"]["type"]
                        group.save()

                    else:
                        TelegramGroup.objects.filter(id=group.id).update(
                            title=t_message["chat"]["title"],
                            chat_type = t_message["chat"]["type"]
                        )
                    group.users.add(user)
                    group.save()

                # Record user last group activity
                group_activity, created = LastGroupActivity.objects.get_or_create(
                    group=group,
                    user=user
                )
                group_activity.timestamp = timezone.now()
                group_activity.save()

                # save group settings (pillory enable/disable, token_tipping status, etc.)
                all_tokens = SLPToken.objects.filter(
                    Q(publish=True),
                    Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                )
                save = False

                try:
                    tipping_status = group.settings['token_tipping_status']
                except KeyError:                    
                    tipping_status = {}
                    save = True
                try:
                    pillory_status = group.settings['pillory_status']
                except KeyError:
                    pillory_status = True
                    save = True
                
                for token in all_tokens:
                    try:
                        temp = group.settings['token_tipping_status'][token.name]
                    except KeyError:
                        tipping_status[token.name] = True
                        save = True

                if save:                                           
                    group.settings['token_tipping_status'] = tipping_status
                    group.settings['pillory_status'] = pillory_status
                    group.save()

                    
                # update last message
                try:
                    ltm, _ = LastTelegramMessage.objects.get_or_create(
                        user=user,
                        telegram_group=group                    
                    )
                except LastTelegramMessage.MultipleObjectsReturned:
                    ltm = LastTelegramMessage.objects.filter(
                        user=user,
                        telegram_group=group    
                    ).first()
                ltm.last_message_timestamp=timezone.now()
                ltm.save()

                if 'left_chat_member' in t_message.keys():
                    try:
                        kicked_user = User.objects.get(telegram_id=t_message['left_chat_member']['id'])
                        group.users.remove(kicked_user)
                        group.save()
                    except User.DoesNotExist:
                        pass
                    logger.info('%s left the group' % t_message['left_chat_member']['first_name'])

                # check if bot is mentioned
                if (self.text == '@' + settings.TELEGRAM_BOT_USER) or (self.text == 'help') or (self.text == '/help'):
                    logger.info('inside')
                    if not settings.REDISKV.sismember('telegram_msgs', self.update_id):
                        try:
                            # telegram_bot_id = settings.TELEGRAM_BOT_TOKEN.split(':')[0]
                            # bot_url = 'tg://user?id=' + telegram_bot_id
                            bot_url = 'https://t.me/' + settings.TELEGRAM_BOT_USER
                            messages = array = [
                                'Sup, if you want to learn how to push my buttons <a href="%s">DM me</a> homie.' % bot_url,
                                'I can show you how to play with my doodads, but you have to <a href="%s">private message</a> me first.' % bot_url,
                                'Yo! I heard you wanted to see me. Well here I am homeslice. \n\n<a href="%s">DM Me</a>, Let\'s talk.' % bot_url,
                                'What\'s up? <a href="%s">Message Me</a>. Let\'s talk.' % bot_url,
                                'We frens. <a href="%s">Message Me</a> so the normies aren\'t all up in our business.' % bot_url,
                                'You Rang? Lets get spicy! <a href="%s">Message me</a> to learn the fun things we can do together!' % bot_url
                            ]
                            self.message = random.choice(messages)
                            mentioned_bot = True
                        except KeyError:
                            pass

                # rain feature here
                if self.text and not mentioned_bot:
                    # group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                    # sender_telegram_id = t_message['from']['id']
                    # sender, created = User.objects.get_or_create(
                    #     telegram_id=sender_telegram_id
                    # )

                    # if created or sender.telegram_user_details != t_message['from']:
                    #     # Update user details, ONLY when there are changes
                    #     sender.telegram_user_details = t_message['from']
                    #     sender.save()

                    if self.text.startswith('/sprice'):
                        token = 'spice'
                        msg = exchange_stats.get_stats(token)
                        self.message = msg
                        if len(self.text.lower().split(' ')) > 1:
                            token = self.text.lower().split(' ')[1]
                            msg = exchange_stats.get_stats(token)
                            if msg:
                                self.message = msg

                    if self.text.startswith('/price ') and len(self.text.lower().split(' ')) == 2:
                        token = self.text.lower().split(' ')[1]
                        msg = exchange_stats.get_stats(token)
                        if msg:
                            self.message = msg

                    if self.text.lower().startswith('rain'):
                        if self.is_feat_disabled('rain'):
                            msg = get_maintenance_response('rain')
                        else:
                            with trans.atomic():    
                                # redis = settings.REDISKV
                                # message_ids = redis.lrange('telegram_message_ids', 0, -1)
                                # msg_id = str(self.data['message']['message_id']).encode()
                                # if msg_id not in message_ids:
                                #     redis.lpush('telegram_message_ids', msg_id)
                                msg = self.rain(user.id, self.text, group.id)
                                if msg is not '':
                                    if self.advertisement and random.choices([True, False],[config.AD_FREQUENCY, 100-config.AD_FREQUENCY])[0]:
                                        msg += "\n\n%s" % self.advertisement_message
                                    if self.reply_markup['inline_keyboard'][0][0]['callback_data'] is not '':
                                        if self.reply_markup['inline_keyboard'][0][0]['callback_data'].startswith('rain:'):
                                            send_telegram_message.delay(msg, self.dest_id, self.update_id,reply_markup=self.reply_markup)
                                    else:
                                        send_telegram_message.delay(msg, self.dest_id, self.update_id)
                                    rained = True

            if self.text and not rained:
                try:
                    entities = t_message['entities']
                    for entity in entities:
                        if entity['type'] == 'mention':
                            if entity['offset'] == 0:
                                mention = self.text[:entity['length']]
                                self.text = self.text.replace(mention, '').strip()
                                break
                        elif entity['type'] == 'bot_command':
                            if self.text.startswith('/'):
                                bot_user = '@' + settings.TELEGRAM_BOT_USER
                                self.text = self.text.replace(bot_user, '').strip()
                except KeyError:
                    pass


                if not mentioned_bot:
                    transfer_text = self.text.lstrip('/').strip()
                    usernames = re.findall("@[\w_]+", self.text)
                    self.text = self.text.lower().lstrip('/').strip()

                    if usernames:
                        self.text = self.replace_usernames(usernames)

                    self.text = ' '.join(self.text.split())

                    # user, created = User.objects.get_or_create(
                    #     telegram_id=t_message['from']['id']
                    # )

                    # if created or user.telegram_user_details != t_message['from']:
                    #     # Update user details, only when changes are made
                    #     user.telegram_user_details = t_message['from']
                    #     user.save()

                    qs_user = User.objects.filter(id=user.id)

                    username = ''
                    try:
                        username = user.telegram_user_details['username']
                    except KeyError as exc:
                        username = ''

                    # get list of valid tokens
                    tokens = SLPToken.objects.filter(
                        Q(publish=True),
                        Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                    )
                    token_names = [t.name for t in tokens]

                    # if-else blocks for commands in private messages only
                    if chat_type == 'private':
                        if self.custom_private_pattern(self.text):return
                        
                        elif self.text == 'rain':
                            if self.is_feat_disabled('rain'):
                                self.message = get_maintenance_response('rain')
                            else:
                                self.message = get_rain_response()

                        elif self.text == 'twitter':
                            if self.is_feat_disabled('transfer'):
                                self.message = get_maintenance_response('transfer')
                            else:
                                self.message = get_response('twitter')

                        elif self.text == 'reddit':
                            if self.is_feat_disabled('transfer'):
                                self.message = get_maintenance_response('transfer')
                            else:
                                self.message = get_response('reddit')
                        
                        elif self.text == 'tipswitch':
                            self.message = get_response('tip_token_switch')

                        elif self.text == 'pillory':
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillory') # set to 'pillorie' instead of 'pillory' for response purposes
                            else:
                                self.message = get_pillory_faq()

                        elif self.text == 'anonymousname':
                            self.message = 'Hi! Your anonymous username is: \n\n<b>%s</b>' % user.anon_name

                        elif self.text == 'spicefeednameon':
                            qs_user.update(display_username=True)
                            self.message = 'Ok spicefeed will show your actual username.. privacy rekt!'

                        elif self.text == 'spicefeednameoff':
                            qs_user.update(display_username=False)
                            self.message = 'Ok spicefeed will now hide your username and replace it with one we have "very" carefully made up for you..'

                        # TWITTER TRANSFER
                        elif self.text.startswith('twitter '):
                            if self.is_feat_disabled('transfer'):
                                self.message = get_maintenance_response('transfer')
                            else:
                                if re.match(f'^twitter\s+@[\w_]+\s+{self.amt_with_commas_regex}$', self.text):
                                    self.transfer_spice(transfer_text, user.id)
                                else:
                                    self.message = get_response('twitter')

                        # REDDIT TRANSFER
                        elif self.text.startswith('reddit '):
                            if self.is_feat_disabled('transfer'):
                                self.message = get_maintenance_response('transfer')
                            else:
                                if re.match(f'^reddit\s+[\w_]+\s+{self.amt_with_commas_regex}$', self.text):
                                    self.transfer_spice(transfer_text, user.id)
                                else:
                                    self.message = get_response('reddit')

                        elif self.text.strip() == 'deposit':
                            if self.is_feat_disabled('deposit'):
                                self.message = get_maintenance_response('deposit')
                            else:
                                self.message = get_response('deposit')

                        elif self.text.startswith('deposit') and not self.text.lower() == 'deposit':
                            token_name = self.text.split('deposit')[-1].strip(' ').upper()
                            deposit_address = user.simple_ledger_address
                            slp_token = SLPToken.objects.filter(
                                Q(name__iexact=token_name),
                                Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                            )
                            
                            if token_name == 'BCH':
                                deposit_address = user.bitcoincash_address
                            if slp_token.exists():
                                if user.frozen:
                                    self.message = self.get_frozen_response(user.get_username, '', False)
                                elif self.is_feat_disabled('deposit'):
                                    self.message = get_maintenance_response('deposit')
                                else:
                                    token = slp_token.first()
                                    if not token.announce_delisting:
                                        message1 = f"\U000026A0 Send deposit <b> not below {token.min_deposit} </b> to this address \U000026A0"
                                        message2 = '%s' % (deposit_address)
                                        send_telegram_message.delay(message1, self.dest_id, self.update_id)
                                        send_telegram_message.delay(message2, self.dest_id, self.update_id)
                                    else:
                                        message = f"⚠️ {token.name} has been scheduled for delisting ⚠️"
                                        message += "\nMoreover, deposits for this token have been suspended."
                                        send_telegram_message.delay(message, self.dest_id, self.update_id)

                        # Check balance using "/balance" or "/balance@..."
                        elif self.text.startswith('balance') or self.text.startswith('balance@', 0):
                            if chat_type == 'private':
                                proceed = True
                                if len(self.text.split()) == 2:
                                    token_name = self.text.split()[1].upper()
                                elif len(self.text.split()) == 1 and self.text.split()[0] == 'balance':
                                    # default balance token
                                    token_name = 'all'
                                else:
                                    proceed = False
                                    self.message = "<b>Invalid balance command.</b> Here is the correct way to check your balance:  "
                                    self.message += "<b><i>balance (token)</i></b>"
                                    self.message += "\n\nNot specifying token defaults to listing the balance of all tokens."

                                if proceed:
                                    slp_token = SLPToken.objects.filter(
                                        Q(name__iexact=token_name),
                                        Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                                    )
                                    user_name = user.telegram_display_name                                       
                                    #list all balance
                                    if token_name.lower() == 'all':
                                        slp_token_balances = self.get_balance_str(user.id, SLPToken.objects.get(name__iexact='spice').token_id)
                                        self.message = f"<b>@{user_name}</b>, your balance for each tokens are as follows: \n\n<b>SPICE</b>  =  {slp_token_balances} \U0001f336\n"
                                        
                                        slps = SLPToken.objects.filter(
                                            ~Q(name__iexact='spice'),
                                            Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                                        )
                                        for slp in slps:
                                            if slp.publish or (not slp.publish and user.telegram_id in slp.allowed_devs):

                                                if get_balance(user.id, slp.token_id) > 0 and slp.announce_delisting:
                                                    if slp.announce_delisting < timezone.now() < slp.date_delisted:
                                                        self.for_delisting.append(slp.name)
                                                    else:
                                                        continue

                                                balance_str = self.get_balance_str(user.id, slp.token_id)
                                                self.message+=f"<b>{slp.name}</b>  =  {balance_str} {slp.emoji}\n"

                                    # balance for a specific token
                                    elif slp_token.exists(): 
                                        token = slp_token.first()
                                        if token.publish or (not token.publish and user.telegram_id in token.allowed_devs):
                                            balance_str = self.get_balance_str(user.id, token.token_id)

                                            if token.announce_delisting:
                                                if token.announce_delisting < timezone.now() < slp.date_delisted:
                                                    if get_balance(user.id, slp.token_id) > 0:
                                                        self.for_delisting.append(token.name)
                                                    
                                            self.message = f"<b>@{user_name}</b>, you have {balance_str} {token.emoji} {token.name} {token.emoji}!"
                
                                    else:
                                        self.message = f'Sorry, we don\'t support <b>{token_name}</b> token as of yet.'
                                    # Update last activity
                                    user.last_activity = timezone.now()
                                    user.save()

                        elif self.text == 'tokens':
                            self.message = get_slp_token_list(user)

                        elif self.text.strip() == 'withdraw':
                            if self.is_feat_disabled('withdrawal'):
                                self.message = get_maintenance_response('withdrawal')
                            else:
                                self.message = get_withdraw_response()
                        
                        elif re.findall(self.faucet_regex, self.text):
                            token = self.text.split(' ')[-1].upper()
                            if SLPToken.objects.filter(
                                Q(name=token),
                                Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                            ).exists():
                                obj = Faucet(slp_address=user.simple_ledger_address, token=token)
                                resp = obj.process_application()
                                if resp != "success":
                                    self.message = resp
                                else:
                                    self.message = f"{obj.token.emoji} Congratulations! You received {obj.amount} {obj.token.name.upper()}. {obj.token.emoji}"
                            else:
                                self.message = "Invalid. Please indicate a registered token name."
                        
                        elif self.text.startswith('withdraw '):
                            if user.frozen:
                                self.message = self.get_frozen_response(user.get_username, '', False)
                            elif self.is_feat_disabled('withdrawal'):
                                self.message = get_maintenance_response('withdrawal')
                            else:
                                amount = None
                                addr = None
                                token = None
                                invalid = False
                                withdraw_all = False

                                try:
                                    # validate amount
                                    amount_temp = self.text.split()[1].strip()
                                    try:
                                        if not re.match(f'^{self.amt_with_commas_regex}$', amount_temp):
                                            raise ValueError('')
                                        amount = amount_temp.replace(',', '').strip()
                                        amount = amount.replace("'", '').replace('"', '')
                                        if 'e' in amount:
                                            amount = None
                                            raise ValueError('')
                                        else:
                                            amount = float(amount)
                                    except ValueError:
                                        amount_temp = amount_temp.lower()
                                        if amount_temp == "all":
                                            withdraw_all = True
                                        else:
                                            self.message = "<b>You have entered an invalid amount!</b>  🚫"


                                    # validate token
                                    if re.findall(f'^withdraw\s+{self.amt_with_commas_regex}\s+simpleledger:.*$', self.text):
                                        token = SLPToken.objects.get(token_id=settings.SPICE_TOKEN_ID)
                                    else:
                                        token_temp = self.text.split()[2].upper().strip()
                                        token = SLPToken.objects.filter(
                                            Q(name__iexact=token_temp),
                                            Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                                        )
                                        if token.exists():
                                            token = token.first()
                                        else:
                                            self.message = f"Sorry, we don\'t support <b>{token_temp}</b> token as of now."
                                            self.message += "\n\nCurrently supported SLP Tokens:\n"
                                            slp_tokens = SLPToken.objects.filter(
                                                Q(publish=True),
                                                Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                                            )
                                            counter = 1
                                            for slp_token in slp_tokens:
                                                self.message += f"\n{counter}. <b>{slp_token.name}</b>"
                                                counter = counter + 1

                                    # Consider this condition during token delisting
                                    if token and isinstance(token, QuerySet):
                                        token = token.first()
                                    if withdraw_all and token.announce_delisting:
                                        if token.announce_delisting < timezone.now() < token.date_delisted:
                                            amount = get_balance(user.id, token.token_id)
                                                                                        

                                    # validate slp or bch address
                                    index = 3
                                    if re.findall(f'^withdraw\s+{self.amt_with_commas_regex}\s+{self.wallet_address}$', self.text):
                                        index = 2
                                    
                                    
                                    addr_temp = self.text.split()[index].strip()
                                    
                                    
                                    if addr_temp.startswith('simpleledger') and len(addr_temp) == 55:
                                        # Encountered bug here : fixed (Aug 4, 2020 by Jet)
                                        if token:
                                            if token.name.lower() != 'bch':
                                                addr = addr_temp.strip()
                                            else:
                                                self.message+= '\nPlease enter your <b>BCH address</b> to withdraw <b>BCH</b>.\n\nExample:'
                                                self.message+= '\nwithdraw 1 bch bitcoincash:qrry9hqfzhmkxlzf5m3f45y92l9gk5msgyustqp7vh'
                                        
                                    elif addr_temp.startswith('bitcoincash') and len(addr_temp) == 54:
                                        # Encountered bug here : Aug 1, 2020 by Reamon
                                        if token:
                                            if token.name.lower() == 'bch':
                                                addr = addr_temp.strip()
                                            else:
                                                self.message += '\nPlease enter your <b>SLP address</b> to withdraw <b> token</b>.\n\nExample:'
                                                self.message += '\n withdraw 1000 honk simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer'

                                    elif addr_temp.startswith('simpleledger') and not len(addr_temp) == 55:
                                        self.message = "<b>You have entered an invalid SLP address!</b>  🚫"
                                    
                                    elif addr_temp.startswith('bitcoincash') and not len(addr_temp) == 54:
                                        self.message = "<b>You have entered an invalid BCH address!</b>  🚫"
                                    else:
                                        self.message = "<b>You have entered an invalid address!</b>  🚫"



                                except IndexError:
                                    invalid = True

                                if addr and amount and token:
                                    if isinstance(amount, str):
                                        amount = amount.replace("'", '').replace('"', '')
                                    balance = get_balance(user.id, token.token_id)
                                    try:
                                        if amount <= balance:
                                            # Limit withdrawals to 1 withdrawal per hour per user
                                            withdraw_limit = False
                                            latest_withdrawal = None
                                            try:
                                                latest_withdrawal = Withdrawal.objects.filter(
                                                    user=user,
                                                    date_failed__isnull=True                                        
                                                ).latest('date_created')
                                            except Withdrawal.DoesNotExist:
                                                pass
                                            if latest_withdrawal:
                                                last_withdraw_time = latest_withdrawal.date_created
                                                time_now = datetime.now(timezone.utc)
                                                tdiff = time_now - last_withdraw_time
                                                withdraw_time_limit = tdiff.total_seconds()
                                                if withdraw_time_limit < 600:  # 1 withdrawal allowed every 10 minutes
                                                    withdraw_limit = True
                                                    username = self.get_name(t_message['from'])
                                                    self.message = f"<b>@{username}</b>, you have reached your hourly withdrawal limit!"

                                            if not withdraw_limit:
                                                token_withdrawal_limit = token.withdrawal_limit
                                                if token.announce_delisting:
                                                    token_withdrawal_limit = 0
                                                    
                                                if amount >= token_withdrawal_limit:

                                                    user = User.objects.get(telegram_id=t_message['from']['id'])
                                                    if token.name.lower() != 'bch':
                                                        if not withdraw_all:
                                                            amount = float(str(amount).split('.')[0])

                                                    if token.publish or (not token.publish and user.telegram_id in token.allowed_devs):
                                                        withdrawal = Withdrawal(
                                                            user=user,
                                                            address=addr,
                                                            amount=amount,
                                                            slp_token=token,
                                                            withdraw_all=withdraw_all
                                                        )
                                                        withdrawal.save()
                                                    else:
                                                        invalid = True
                                                else:
                                                    # username = self.get_name(t_message['from'])
                                                    limit = get_int_or_float(token.withdrawal_limit)
                                                    limit = get_amount_str(limit)
                                                    self.message = f"We can’t process your withdrawal request because it is below minimum. The minimum amount allowed is {limit} {token.emoji} {token.name} {token.emoji}."
                                        else:
                                            username = self.get_name(t_message['from'])
                                            self.message = f"<b>@{username}</b>, you don't have enough {token.emoji} {token.name} {token.emoji} to withdraw!"
                                    except TypeError:
                                        amount = None

                                if (not addr and not amount and not token) or invalid:
                                    self.message = """
                                    \nWithdrawal can be done by running the following command:
                                    \n<b>/withdraw (amount) (token) (simpleledger address)</b>
                                    \n\n<b>Example</b>:
                                    \n/withdraw 1000 SPICE simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
                                    \n/withdraw 5,000 DROP simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
                                        """
                        
                        # Catch SEP20 bridge commands
                        elif self.text.startswith('bridge '):
                            if ' swap ' in self.text:
                                try:
                                    params = self.text.strip().split(' swap ')[-1].split()
                                    swap_amount, swap_token, sep20_recipient = params
                                    swap_token_check = Token.objects.filter(name__iexact=swap_token.lower())
                                    if swap_token_check.exists():
                                        swap_token_obj = swap_token_check.last()
                                        if sep20_recipient.startswith('0x'):
                                            if float(swap_amount) >= swap_token_obj.slp_minimum_amount:
                                                swap_request = SwapRequest(
                                                    user=user,
                                                    telegram_chat_id=self.dest_id,
                                                    amount=swap_amount,
                                                    token=swap_token_obj,
                                                    to_address=sep20_recipient
                                                )
                                                swap_request.save()
                                                
                                                xpub_key = swap_token_obj.slp_wallet_xpub
                                                wallet_hash = swap_token_obj.slp_wallet_hash
                                                swap_from_address = generate_slp_address(int(swap_request.id), xpub=xpub_key, wallet_hash=wallet_hash)
                                                swap_request.from_address = swap_from_address
                                                swap_request.save()
                                                
                                                amount =  float(swap_request.amount) / swap_token_obj.slp_to_sep20_ratio
                                                amount = round(amount, swap_token_obj.sep20_decimals)
                                                if swap_token_obj.slp_to_sep20_ratio < 1:
                                                    ratio_x = 1
                                                    ratio_y = int(1 / swap_token_obj.slp_to_sep20_ratio)
                                                else:
                                                    ratio_x = int(swap_token_obj.slp_to_sep20_ratio)
                                                    ratio_y = 1
                                                self.message = f"Deposit {swap_amount} SLP {swap_token.upper()} tokens to the following address:\n\n{swap_from_address}\n\n{swap_token.upper()} swaps are done at {ratio_x}:{ratio_y} ratio. So, you will be receiving {amount} SEP20 {swap_token.upper()} tokens."
                                            else:
                                                self.message = f"The minimum amount to swap is {swap_token_obj.slp_minimum_amount} {swap_token.upper()} tokens."
                                        else:
                                            self.message = "You entered an invalid SEP20 destination address."
                                    else:
                                        self.message = f"This bridge does not support swapping of {swap_token.upper()} tokens."
                                except (IndexError, ValueError):
                                    self.message = 'Command syntax error! The syntax for sep20 swap is:\n\nbridge swap <amount> <token> <sep20_address>\nExample: sep20 swap 1000 spice 0x3af08fAe1819B463dBBb0Ace20531D48A47f712e'
                            else:
                                self.message = 'SLP-SEP20 Bridge commands:\n\n-------\n\nbridge swap <amount> <token> <sep20_address>\nExample: sep20 swap 1000 spice 0x3af08fAe1819B463dBBb0Ace20531D48A47f712e'
                        else:
                            if 'tip' in self.text:
                                if self.is_feat_disabled('tipping'):
                                    self.message = get_maintenance_response('tip')
                                else:
                                    self.message = get_tip_response()
                            else:
                                self.message = get_response('commands')
                    
                    # commands for public chat
                    else:
                        if self.text == 'greet':
                            user = self.get_name(t_message['from'])
                            msg = f"Wassup {user}?"
                            self.message = msg
                            
                        # turn pillory on/off (for admins only)
                        elif re.findall(self.pillory_switch_regex, self.text):
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                if self.is_admin(None, self.dest_id, False, "spicebot"):
                                    self.switch_pillory(user.id, group.id)

                        # throw emoji to prolong/lessen mute duration of a user
                        elif re.findall(self.throw_pillory_regex, self.text):
                            if user.frozen:
                                self.message = self.get_frozen_response(user.get_username, '', False)
                            elif self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                if self.is_admin(None, self.dest_id, True, "spicebot"):
                                    self.throw_pillory(user.id, group.id)

                        # clear pillories (admins only)
                        elif re.findall(self.clear_pillory_regex, self.text):
                            if user.frozen:
                                self.message = self.get_frozen_response(user.get_username, '', False)
                            elif self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                self.clear_pillory(user.id, group.id)

                        # unmute user override (for admins only)
                        elif re.findall(self.unmute_regex, self.text):
                            if user.frozen:
                                self.message = self.get_frozen_response(user.get_username, '', False)
                            elif self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                if self.is_admin(None, self.dest_id, True, "spicebot"):                    
                                    username = user.telegram_user_details['username']
                                    if self.is_admin(user.telegram_id, self.dest_id, True):
                                        splitted_text = self.text.split()
                                        target_username = splitted_text[1].replace('@', '')
                                        self.unmute_user(user.id, group.id, target_username)
                                    else:
                                        self.message = f"@{username}, you must be an admin of this group to unmute users!"

                        # show list of on-going pillories
                        elif re.findall(self.show_list_regex, self.text):
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                if self.is_admin(None, self.dest_id, True, "spicebot"):
                                    prefix = self.text.split()[0]
                                    self.message = self.get_list(group.id, prefix)

                        # set global pillory default amount (for admins only)
                        elif re.findall(self.set_default_pillory_regex, self.text):
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                self.set_default_pillory(user.id, group.id)
                                
                        # set group pillory time (for admins only)
                        elif re.findall(self.set_default_pillory_time_regex, self.text):
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                self.set_default_pillory_time(user.id, group.id)

                        # show default global pillory cost
                        elif re.findall(self.show_default_pillory_regex, self.text):
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                self.get_group_pillory_fee(user.id, group.id, self.mute)

                        # show default global pillory time
                        elif re.findall(self.show_default_pillory_time_regex, self.text):
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                if self.is_admin(None, self.dest_id, True, "spicebot"):
                                    time, unit = get_formatted_time(group.pillory_time)
                                    self.message = f'Default pillory time for this group is:\n\n🕒  {time} {unit}  🕒'

                        # set pillory amount
                        elif re.findall(self.set_pillory_amt_regex, self.text):
                            if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
                                self.message = get_maintenance_response('pillorie')
                            else:
                                if self.is_admin(None, self.dest_id, True, "spicebot"):
                                    splitted_text = self.text.split()
                                    amt = float(splitted_text[3].replace(',', ''))
                                    target_username = splitted_text[2].replace('@', '')
                                    username = user.telegram_user_details['username']

                                    if self.is_admin(user.telegram_id, self.dest_id, True):
                                        if target_username == settings.TELEGRAM_BOT_USER:
                                            self.message = f"Wait a sec @{username}, you are not allowed to set my threshold!"
                                        else:
                                            target_user = self.target_user_exists_and_in_group(target_username, group)
                                            if target_user:
                                                if target_user.id == user.id:
                                                    self.message = f"@{username}, you can't set your own threshold! That's unfair!"
                                                else:
                                                    if self.is_admin(target_user.telegram_id, self.dest_id, True):
                                                        self.message = f"Hey @{username}, you are not allowed to do any mute operations to any admin!"
                                                    else:
                                                        if amt >= 1:
                                                            mute = Mute.objects.filter(
                                                                target_user=target_user,
                                                                group=group
                                                            )
                                                            if mute.exists():  
                                                                mute = mute.first()
                                                                self.set_pillory_amount(username, mute.id, amt)
                                                            else:
                                                                base_fee = group.pillory_fee
                                                                pillory_time = group.pillory_time

                                                                new_mute = Mute(
                                                                    target_user=target_user,
                                                                    group=group,
                                                                    base_fee=base_fee,
                                                                    remaining_fee=0.0,
                                                                    duration=pillory_time
                                                                )
                                                                new_mute.save()
                                                                self.set_pillory_amount(username, new_mute.id, amt)
                                                        else:
                                                            self.message = f"@{username}, you can't set someone's threshold lower than 1 \U0001f336 SPICE \U0001f336! That's too harsh!"
                                    else:
                                        self.message = f"@{username}, you must be an admin of this group to set other user's thresholds!"

                        # mute or unmute a user
                        elif re.findall(self.pillory_regex, self.text):
                            operation = self.text.split()[0]
                            proceed = True

                            if user.frozen:
                                self.message = self.get_frozen_response(user.get_username, '', False)
                                proceed = False
                            else:
                                if operation == 'pillory':
                                    operation = self.mute
                                elif operation == 'unmute':
                                    operation = self.unmute
                                else:
                                    proceed = False
                            
                            if proceed:
                                self.contribute_function(user.id, group.id, operation)

                        # switch for tipping on different tokens
                        elif re.findall(self.switch_token_tipping_regex, self.text):
                            if not self.is_feat_disabled('tipping'):
                                if self.is_admin(user.telegram_id, group.chat_id, True):
                                    token = self.text.split()[0]
                                    operation = self.text.split()[2]
                                    self.message = self.switch_token_tip_status(token, operation, group.id)
                                else:
                                    self.message = f"Hold on {user.telegram_display_name}, you must be an admin to enable/disable token tippings!"
                            else:
                                self.message = get_maintenance_response('tip')

                        elif 'tip ' in self.text or any(token_name.lower() in self.text for token_name in token_names):
                            try:
                                temp = self.data['message']['reply_to_message']
                                self.tip = True
                            except KeyError:
                                pass

                        elif ' spice' in self.text or ' spices' in self.text:
                            try:
                                temp = self.data['message']['reply_to_message']
                                self.tip = True
                            except KeyError:
                                pass

                        elif self.text == 'spicefeedon':
                            logger.error(f"\n\n\n\nWENT IN THERE on\n\n\n\n")
                            admins = get_chat_admins(t_message["chat"]["id"])
                            if from_id in admins:
                                group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                                group.post_to_spicefeed = True
                                user = User.objects.get(telegram_id=t_message['from']['id'])
                                group.privacy_set_by = user
                                group.last_privacy_setting = timezone.now()
                                group.save()
                                self.message = 'SpiceFeed enabled\nhttps://spice.network'

                        elif self.text == 'spicefeedoff':
                            logger.error(f"\n\n\n\nWENT IN THERE off\n\n\n\n")
                            admins = get_chat_admins(t_message["chat"]["id"])
                            if from_id in admins:
                                group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                                group.post_to_spicefeed = False
                                user = User.objects.get(telegram_id=t_message['from']['id'])
                                group.privacy_set_by = user
                                group.last_privacy_setting = timezone.now()
                                group.save()
                                self.message = 'SpiceFeed disabled'

                        elif self.text == 'spicefeedstatus':
                            logger.error(f"\n\n\n\nWENT IN THERE status\n\n\n\n")
                            group = TelegramGroup.objects.get(chat_id=t_message["chat"]["id"])
                            if group.post_to_spicefeed:
                                self.message = 'SpiceFeed is enabled\nhttps://spice.network'
                            else:
                                self.message = 'SpiceFeed is disabled'

                        else:
                            for char in self.text:
                                if char in emoji.UNICODE_EMOJI or char == "+":
                                    self.tip = True
                                    self.tip_with_emoji = True
                            

                        if self.tip:
                            # group,_ = TelegramGroup.objects.get_or_create(chat_id=t_message["chat"]["id"])
                            # if group.disable_tipping:
                            #     self.message = get_maintenance_response('tipping')
                            #     self.tip = False
                            if user.frozen:
                                self.message = self.get_frozen_response(user.get_username, '', False)
                                self.tip = False
                            else:
                                if 'reply_to_message' in t_message.keys():
                                    with_pof = self.text.strip().lower().endswith('pof')

                                    # handle_tip = True
                                    # try:
                                    #     if not t_message['reply_to_message']['from']['is_bot']:
                                    #         rcpt_telegram_id = t_message['reply_to_message']['from']['id']
                                    #         rcpt, _ = User.objects.get_or_create(
                                    #             telegram_id=rcpt_telegram_id
                                    #         )
                                    #         if rcpt.telegram_username == settings.MUTE_MANAGER_USERNAME:
                                    #             handle_tip = False
                                    # except KeyError:
                                    #     pass

                                    # if handle_tip:
                                    if not self.is_feat_disabled('tipping'):
                                        self.handle_tipping(t_message, self.text, with_pof=with_pof)
                                    else:
                                        self.message = get_maintenance_response('tip')
        if 'callback_query' in self.data.keys():
            callback = self.data['callback_query']
            if 'data' in callback.keys():
                rain_id = callback['data'].split(':')[-1] if callback['data'].startswith('rain:') else ''
                if rain_id:
                    self.message = callback['message']['text']
                    self.message += "\n\n <b> 🌧️ Here's the full list 🌧️ </b> \n\n"
                    self.update_id = str(callback['from']['id'])
                    rain = Rain.objects.get(id=rain_id)
                    users = rain.recepients.all()
                    first = True
                    for user in users:
                        display_name = user.telegram_display_name
                        if user.telegram_id == self.update_id:
                            self.message += "<b>"
                        if first:
                            self.message += display_name
                            first = False
                        else:
                            self.message += '\n' + display_name
                        if user.telegram_id == self.update_id:
                            self.message += "</b>"
                    send_telegram_message.delay(self.message, self.update_id, None)

        info = {
            'text': self.text,
            'entities': entities,
            'message': self.message,
            'data_keys': list(self.data.keys())
        }

        logger.info(f"\n\n\ninfo: {info}\n\n\n")
        
        # remove chat_id in redis
        redis = settings.REDISKV
        chat_ids = redis.lrange('telegram_chat_ids', 0, -1)
        
        if len(chat_ids) > 20:
            chat_id = redis.lindex('telegram_chat_ids', -1)
            redis.lrem('telegram_chat_ids', -1, chat_id)        

        return info

    def get_frozen_response(self, frozen_username, operation, is_recipient=True):
        if is_recipient:
            message = f"Could not {operation} {frozen_username}.\n\nThe user's account is currently  ❄️  frozen  ❄️\n"
            message += "It will not be able to send/receive any transactions at the moment."
        else:
            message = f"Greetings {frozen_username}!\n\nYour account has been  ❄️  frozen  ❄\n"
            message += "You are temporarily unable to do any spicebot operations at the moment."

        return message

    def get_balance_str(self, user_id, token_id):
        balance = get_balance(user_id, token_id)                        
        balance = '{:,}'.format(round(balance, 8))
        balance_str = str(balance)

        if 'e' in balance_str:
            balance_str = "{:,.8f}".format(float(balance_str))
        if balance_str.endswith('.0'):
            balance_str = balance_str[:-2]                                         

        return balance_str

    def is_feat_disabled(self, feature):
        if feature == 'withdrawal':
            status = config.DEACTIVATE_WITHDRAWAL
        if feature == 'deposit':
            status = config.DEACTIVATE_DEPOSIT
        if feature == 'transfer':
            status = config.DEACTIVATE_TRANSFER
        if feature == 'tipping':
            status = config.DEACTIVATE_TIPPING
        if feature == 'rain':
            status = config.DEACTIVATE_RAIN
        if feature == 'pillory':
            status = config.DEACTIVATE_PILLORY

        # excludes disabling on scibiz telegram groups
        scibiz_group_ids = [-1001292019824, -307949816] # [staging, prod]
        scibiz_group = self.dest_id in scibiz_group_ids

        return status and not scibiz_group

    def respond(self):
        final_amount_str = self.final_amount_str.replace(',','')
        if (float(final_amount_str) > 0) or (self.message and self.dest_id):
            try:
                if self.tip and self.recipient:
                    token = SLPToken.objects.filter(
                        Q(name__iexact=self.token_name),
                        Q(date_delisted=None) | ( Q(date_delisted__gt=timezone.now()) & Q(announce_delisting__lt=timezone.now()) )
                    ).first()

                    created = False
                    with trans.atomic():
                        if get_balance(self.sender.id, token.token_id) >= (self.tip_amount + self.tip_fee):                            
                            group = TelegramGroup.objects.get(chat_id=self.dest_id)
                            content = Content(
                                tip_amount=self.tip_amount,
                                sender=self.sender,
                                recipient=self.recipient,
                                details=self.data,
                                post_to_spicefeed=group.post_to_spicefeed,
                                parent=self.parent,
                                recipient_content_id=self.recipient_content_id,
                                slp_token=token
                            )
                            content.save()
                            
                            # Sender outgoing transaction
                            transaction_hash = f"{self.sender.id}-{self.data['message']['message_id']}-{self.dest_id}-{token.name}-{self.tip_amount}"
                            created, sender_thash = create_transaction(
                                self.sender.id,
                                self.tip_amount,
                                'Outgoing',
                                token.id,
                                settings.TXN_OPERATION['TIP'],
                                transaction_hash=transaction_hash,
                                chat_id=self.dest_id
                            )

                            # Recipient incoming transaction
                            transaction_hash = f"{self.recipient.id}-{self.data['message']['message_id']}-{self.dest_id}-{token.name}-{self.tip_amount}"
                            created, recipient_thash = create_transaction(
                                self.recipient.id,
                                self.tip_amount,
                                'Incoming',
                                token.id,
                                settings.TXN_OPERATION['TIP'],
                                transaction_hash=transaction_hash,
                                chat_id=self.dest_id
                            )

                            # swap_related_transactions(sender_thash, recipient_thash)

                            if self.tip_fee != 0:
                                # Deduct tip fee from user
                                transaction_hash = f"{self.sender.id}-{self.data['message']['message_id']}-{self.dest_id}-{token.name}-{self.tip_fee}"
                                created, sender_thash = create_transaction(
                                    self.sender.id,
                                    self.tip_fee,
                                    'Outgoing',
                                    token.id,
                                    settings.TXN_OPERATION['TIP'],
                                    transaction_hash=transaction_hash,
                                    chat_id=self.dest_id
                                )

                                # Add tip fee to tax collector
                                transaction_hash = f"{settings.TAX_COLLECTOR_USER_ID}-{self.data['message']['message_id']}-{self.dest_id}-{token.name}-{self.tip_fee}"
                                created, recipient_thash = create_transaction(
                                    settings.TAX_COLLECTOR_USER_ID,
                                    self.tip_fee,
                                    'Incoming',
                                    token.id,
                                    settings.TXN_OPERATION['TIP'],
                                    transaction_hash=transaction_hash,
                                    chat_id=self.dest_id
                                )

                                # swap_related_transactions(sender_thash, recipient_thash)

                         
                            env = settings.DEPLOYMENT_INSTANCE.strip(' ').lower()
                            
                            if created:
                                #set of replies
                                if self.text.count(' pof %') or self.text.count('pof % '):
                                    if env == 'prod':
                                        self.message = f"<b>{self.from_username}</b> (PoF <b>{self.pct_sender}</b>% {settings.POF_SYMBOLS[self.pof_sender]}) tipped {self.final_amount_str} {token.emoji} {token.name} {token.emoji} to <b>{self.to_username}</b> (PoF <b>{self.pct_receiver}</b>% {settings.POF_SYMBOLS[self.pof_receiver]})"
                                    else:
                                        self.message = f"<b>{self.from_username}</b> (PoF <b>{self.pct_sender}</b>% {settings.POF_SYMBOLS[self.pof_sender]}) tipped {self.final_amount_str} {token.emoji} {token.name} {token.emoji} to <b>{self.to_username}</b> (PoF <b>{self.pct_receiver}</b>% {settings.POF_SYMBOLS[self.pof_receiver]})"
                                elif self.text.count(' pof') or self.text.count('pof '):
                                    if env == 'prod':
                                        self.message = f"<b>{self.from_username}</b> (PoF <b>{self.pof_sender}/5 {settings.POF_SYMBOLS[self.pof_sender]}</b>) tipped {self.final_amount_str} {token.emoji} {token.name} {token.emoji} to <b>{self.to_username}</b> (PoF <b>{self.pof_receiver}/5 {settings.POF_SYMBOLS[self.pof_receiver]}</b>)"
                                    else:
                                        self.message = f"<b>{self.from_username}</b> (PoF <b>{self.pof_sender}/5 {settings.POF_SYMBOLS[self.pof_sender]}</b>) tipped {self.final_amount_str} {token.emoji} {token.name} {token.emoji} to <b>{self.to_username}</b> (PoF <b>{self.pof_receiver}/5 {settings.POF_SYMBOLS[self.pof_receiver]}</b>)"
                                else:
                                    if env == 'prod':
                                        self.message = f"<b>{self.from_username}</b> tipped {self.final_amount_str} {token.emoji} {token.name} {token.emoji} to <b>{self.to_username}</b>"
                                    else:
                                        self.message = f"<b>{self.from_username}</b> tipped {self.final_amount_str} {token.emoji} {token.name} {token.emoji} to <b>{self.to_username}</b>"
                        else:
                            self.message = f"<b>@{self.from_username}</b>, you don't have enough {token.emoji} {token.name} {token.emoji}!"
                if self.advertisement and random.choices([True, False],[config.AD_FREQUENCY, 100-config.AD_FREQUENCY])[0]:
                    self.message += "\n\n%s" % self.advertisement_message
                
                send_telegram_message.delay(self.message, self.dest_id, self.update_id)

                if self.for_delisting:
                    if len(self.for_delisting) > 1:
                        message = f"ℹ️ These tokens have been scheduled for delisting: ℹ️"
                        for token in self.for_delisting:
                            message += f'\n{token}'
                        subject = "these tokens"
                    else:
                        token = self.for_delisting[0]
                        message = f"ℹ️ <b>{token}</b> has been scheduled for delisting. ℹ️"
                        subject = "this token"
                    message += f"\n\nWe encourage you to withdraw any remaining funds you have of {subject}."

                    message += f"\n\nFor delisted tokens, you have the option to withdraw all balance using this command:\n/withdraw all <b>(token name) (simpleledger address) </b>"
                    send_telegram_message.delay(message, self.dest_id, self.update_id)

            except AttributeError as exc:
                logger.error(exc)
                send_telegram_message.delay(self.message, self.dest_id, self.update_id, self.reply_markup)
            
        else:
            logger.info(f"No response")


    def target_user_exists_and_in_group(self, target_username, group):
        try:
            target_user = User.objects.get(telegram_user_details__username=target_username)

            if target_user not in group.users.all():
                self.message = f"Hmm... I don't know anyone named {target_username} in this group."
                return None

            return target_user
        except User.DoesNotExist as exc:
            self.message = f"There's no one named {target_username} yet, as far as my memories tell me."
            return None


    def is_admin(self, telegram_id, chat_id, is_pillory, user_type="regular"):
        admin_ids = get_chat_admins(chat_id)
        
        if user_type == "spicebot":
            group = TelegramGroup.objects.get(chat_id=chat_id)
            if group.chat_type == "supergroup":
                # return True
                if settings.DEPLOYMENT_INSTANCE == "staging" or settings.DEPLOYMENT_INSTANCE == "dev":
                    bot_telegram_id = 984045388 # spicebot-staging
                else:
                    bot_telegram_id = 867909677 # spicebot-prod

                if bot_telegram_id in admin_ids:
                    if is_pillory:
                        if not group.settings['pillory_status']:
                            self.message = "Pillory currently disabled for this group  🚫"
                            return False
                    return True
                else:
                    self.message = "You have to honor me as an admin of this group to perform pillory operations!"
            else:
                self.message = "Pillory feature only works within supergroups."

        elif user_type == "regular":
            return int(telegram_id) in admin_ids
        
        return False

    def process_pillory(self, user_id, mute_id, amount, operation, is_new_mute=False):
        user = User.objects.get(id=user_id)
        username = user.telegram_user_details['username']
        mute = Mute.objects.get(id=mute_id)
        target_username = mute.target_user.telegram_user_details['username']

        basis = mute.remaining_fee
        if operation == self.unmute:
            basis = mute.remaining_unmute_fee

        diff = get_int_or_float(basis - amount)
        amount = get_int_or_float(amount)

        if diff < 0:
            r_fee = get_int_or_float(basis)
            r_fee = get_amount_str(r_fee)
            if mute.get_fee() == mute.remaining_fee:
                mute.remaining_fee = 0
                mute.save()
            self.message = f"@{username}, that's too much contribution needed to <code>{operation}</code> {target_username}\n\n{r_fee} \U0001f336 SPICE \U0001f336 left"
        else:
            # to check if the contributor is only one user and does an ALL-IN payment for pillory
            ctbrs_count = mute.contributors.count()
            logger.error(f"CTBRS: {mute.contributors.all()}")
            if ctbrs_count == 0 and diff == 0:
                orig_amount = amount
                amount_percentage = amount * 0.75
                amount = get_int_or_float(amount_percentage, True)

                if amount == orig_amount:
                    amount = round(amount_percentage, 2)

                amount_str = get_amount_str(amount)
                diff = get_int_or_float(basis - amount)
                self.message = f"@{username}, you can't pillory a user by yourself! It needs to be of common agreement of at least two   ✌️  users in this group"
                self.message += f"\n\nDue to that reason, I will only allow 75% ({amount_str} SPICE \U0001f336) of the total mute fee of {target_username}"
                send_telegram_message.delay(self.message, self.dest_id, self.update_id)
                # mute.contributors.add(user)
                # mute.save()
            else:
                if mute.contributors.filter(id=user.id).exists():
                    self.message = f"@{username}, you already have contributed! Contributions can only be done once  ℹ️"
                    return
        # else:
            mute.contributors.add(user)
            mute.save()

            response = self.collect_spice(user_id, mute_id, operation, amount)                                                
            if response == "OK":
                amount_str = get_amount_str(amount)
                self.message = f"+{amount_str} \U0001f336 SPICE \U0001f336 added to bucket by @{username}\n\n"
                if diff == 0:
                    mm_does_not_exist = False
                    try:
                        subscriber = Subscriber.objects.get(username=settings.MUTE_MANAGER_USERNAME)   
                        if subscriber.token == settings.MUTE_MANAGER_TOKEN and subscriber.app_name == 'telegram':                         
                            mutemanager = User.objects.filter(telegram_id=subscriber.details['user_collector_id'])
                            if mutemanager.exists():
                                mutemanager = mutemanager.first()

                                allow_permissions = False
                                fee = get_int_or_float(mute.get_fee())

                                if operation == self.unmute:
                                    mute = Mute.objects.get(id=mute_id)
                                    # mute.count -= 1
                                    # mute.save()
                                    # fee = get_int_or_float(mute.unmute_fee)
                                    mutefee = mute.get_fee() / 0.99
                                    mutefee += mutefee * settings.UNMUTE_INTEREST
                                    fee = get_int_or_float(mutefee, True)
                                    mute.is_being_unmuted = False
                                    # mute.count += 1
                                    # mute.save()
                                    allow_permissions = True

                                rain_text = f"rain 20 people {fee} spice"
                                restrict_user(mute.id, allow_permissions, False, allow_permissions)
                                
                                self.message += "<b>⚠️  ATTENTION EVERYONE  ⚠️</b>"

                                if operation == self.mute:
                                    f_time, f_unit = get_formatted_time(mute.duration)
                                    self.message += f"\n\n<b>{target_username} has been pilloried! Check back in {f_time} {f_unit}!</b>"
                                else:
                                    self.message += f"\n\n<b>Thanks to your collected efforts, I have unmuted {target_username}!  🎉</b>"

                                rain_response = self.rain(mutemanager.id, rain_text, mute.group.id, True)
                                self.message += f"\n\n{rain_response}"
                            else:
                                mm_does_not_exist = True
                        else:
                            mm_does_not_exist = True
                    except Subscriber.DoesNotExist as exc:
                        mm_does_not_exist = True

                    if mm_does_not_exist:
                        logger.error("\n\n========== Mute manager does not exist yet. ==========\n\n")
                        if is_new_mute:
                            mute.delete()
                else:
                    r_fee = get_int_or_float(mute.get_fee())
                    if operation == self.unmute:
                        r_fee = get_int_or_float(mute.remaining_unmute_fee)
                        mute = Mute.objects.get(id=mute_id)
                        if not mute.is_being_unmuted:
                            mute.is_being_unmuted = True
                            mute.save()

                    r_fee = get_amount_str(r_fee)
                    diff_str = get_amount_str(diff)
                    self.message += f"Only <b>{diff_str}</b> out of <b>{r_fee}</b> SPICE remaining to <code>{operation}</code> {target_username}!"
            elif response == "insufficient balance":
                if is_new_mute:
                    mute.delete()
                self.message = f"@{username}, you don't have enough \U0001f336 SPICE \U0001f336!"
            else:
                if is_new_mute:
                    mute.delete()
                logger.error(f"\n============= Problem: {response} ==============\n")


    def replace_usernames(self, usernames):
        text = self.text
        for name in usernames:
            text = text.replace(name.lower(), name)
        return text

    
    def unmute_user(self, user_id, group_id, target_username, is_user_set=False):
        user = User.objects.get(id=user_id)
        username = user.telegram_user_details['username']

        if target_username == settings.TELEGRAM_BOT_USER:
            self.message = f"Wait a sec @{username}, I can never be unmuted... or muted!"
        else:
            group = TelegramGroup.objects.get(id=group_id)
            target_user = self.target_user_exists_and_in_group(target_username, group)

            if target_user:
                if target_user.id == user.id:
                    self.message = f"@{username}, you can't unmute yourself!"
                else:
                    if self.is_admin(target_user.telegram_id, self.dest_id, True):
                        self.message = f"Hey @{username}, you are not allowed to do any mute operations to any admin!"
                    else:
                        mute = Mute.objects.filter(
                            target_user=target_user,
                            group=group,
                            is_muted=True
                        )

                        if mute:
                            mute = mute.first()
                            restrict_user(mute.id, True, False, is_user_set)
                        else:
                            self.message = f"Yo @{username}, {target_username} is currently <code>{self.unmute}d</code>  😄"


    def set_pillory_amount(self, username, mute_id, amount):
        mute = Mute.objects.get(id=mute_id)
        mute.next_fee = amount
        mute.fee_changed = True
        mute.save()

        target_username = mute.target_user.telegram_username
        amount_str = get_int_or_float(amount)
        amount_str = get_amount_str(amount_str)

        if mute.base_fee >= amount:
            change = "decreased"
        else:
            change = "increased"

        self.message = f"Dear <b>{target_username}</b>,"
        self.message += f" your threshold in this group has been {change} to:"
        self.message += f"\n\n{amount_str} \U0001f336 SPICE \U0001f336"
        self.message += "\n\nThis will take effect next pillory."
        self.message += f"\n\n- <b>{username}</b> (admin)"


    def get_list(self, group_id, list_type):
        message = ""
        is_muted = False

        if list_type == "pillory":
            message = "It seems there is no one currently under pillory  ℹ️"
        elif list_type == "mute":
            message = "No one is muted at the moment  ℹ️"
            is_muted = True

        mutes = Mute.objects.filter(
            group__id=group_id,
            is_muted=is_muted
        )

        if mutes:
            if list_type == "pillory":
                mutes = mutes.exclude(remaining_fee=0)
            if mutes:
                counter = 1
                if list_type == "pillory":
                    message = "✏️  <b>ON-GOING PILLORIES:</b>  ✏️\n"
                elif list_type == "mute":
                    message = "📌  <b>SILENCED USERS:</b>  📌\n"
                    
                for mute in mutes:
                    target_username = mute.target_user.telegram_user_details['username']
                    
                    if list_type == "pillory":
                        remaining_fee = get_int_or_float(mute.remaining_fee)
                        remaining_fee = get_amount_str(remaining_fee)
                        message += f"\n{counter}. {target_username} - <code>{remaining_fee} SPICE left</code>"
                    elif list_type == "mute":
                        remaining_time = (timedelta(minutes=mute.duration) + mute.date_started) - timezone.now()

                        if remaining_time.days == -1:
                            remaining_time = "unmuting..."
                        else:
                            total_seconds = remaining_time.seconds + (remaining_time.days * 86400)
                            remaining_time = sec_to_remaining_time(total_seconds)

                        spaces = '   '
                        if counter >= 10:
                            spaces += ' '
                        if counter >= 100:
                            spaces += ' '
                        
                        unmute_fee_remaining = get_int_or_float(mute.remaining_unmute_fee)
                        unmute_fee_remaining = get_amount_str(unmute_fee_remaining)

                        suffix = "left"
                        if remaining_time == 'unmuting...':
                            suffix = ""

                        message += f"\n{counter}. {target_username}  -  <code>{remaining_time}{suffix}</code>"
                        message += f"\n{spaces}(unmute fee: {unmute_fee_remaining} SPICE \U0001f336 left)"

                    counter = counter + 1

        return message


    def collect_spice(self, user_id, mute_id, operation, amount):
        try:
            subscriber = Subscriber.objects.get(username=settings.MUTE_MANAGER_USERNAME)
            proceed = True
        except Subscriber.DoesNotExist:
            response = 'Mutemanager does not exist'
            logger.error("\n\n========== Mute manager does not exist yet. ==========\n\n")
            return response
            
        if proceed and subscriber.token == settings.MUTE_MANAGER_TOKEN:
            app_name = subscriber.app_name
            if app_name == 'telegram':
                mutemanager = User.objects.filter(telegram_id=subscriber.details['user_collector_id'])
                if mutemanager.exists():
                    mutemanager = mutemanager.first()
                    with trans.atomic():
                        # usr = User.objects.get(id=user_id)
                        balance = 0
                        if get_balance(user_id, settings.SPICE_TOKEN_ID) >= amount:
                            transaction_hash = f"{user_id}-{self.data['message']['message_id']}-{self.dest_id}-spice-{amount}"
                            token = SLPToken.objects.get(token_id=settings.SPICE_TOKEN_ID)
                            created, sender_thash = create_transaction(
                                user_id,
                                amount,
                                'Outgoing',
                                token.id,
                                settings.TXN_OPERATION['PILLORY'],
                                transaction_hash=transaction_hash,
                                chat_id=self.dest_id
                            )
                            transaction_hash = f"{mutemanager.id}-{self.data['message']['message_id']}-{self.dest_id}-spice-{amount}"
                            created, recipient_thash = create_transaction(
                                mutemanager.id,
                                amount,
                                'Incoming',
                                token.id,
                                settings.TXN_OPERATION['PILLORY'],
                                transaction_hash=transaction_hash,
                                chat_id=self.dest_id
                            )

                            swap_related_transactions(sender_thash, recipient_thash)

                            mute = Mute.objects.get(id=mute_id)

                            if operation == self.mute:
                                mute.remaining_fee -= amount
                            elif operation == self.unmute:
                                mute.remaining_unmute_fee -= amount

                            mute.save()

                            return "OK"
                        else:
                            return "insufficient balance"
        else:
            return "Invalid token!"


    def get_group_pillory_fee(self, user_id, group_id, fee_type):
        if self.is_admin(None, self.dest_id, True, "spicebot"):
            user = User.objects.get(id=user_id)
            group = TelegramGroup.objects.get(id=group_id)
            username = user.telegram_user_details['username']
            
            base_fee = group.pillory_fee
            base_fee = get_int_or_float(base_fee)
            base_fee = get_amount_str(base_fee)
            self.message = f"The default pillory cost for this group is:  {base_fee} \U0001f336 SPICE \U0001f336"


    def set_default_pillory_time(self, user_id, group_id):
        if self.is_admin(None, self.dest_id, True, "spicebot"):
            user = User.objects.get(id=user_id)
            group = TelegramGroup.objects.get(id=group_id)
            username = user.telegram_user_details['username']

            if self.is_admin(user.telegram_id, self.dest_id, True):
                time = float(self.text.split()[2].replace(',', ''))
                converted_time = time
                unit = self.text.split()[3]
                proceed = True

                if unit == 'mins' or unit == 'min':
                    if time < 5:
                        self.message = f'Uhmm.. @{username}, the minimum duration for minutes is <b>5</b>.'
                        proceed = False
                else:
                    if time < 1:
                        self.message = f'For your info @{username}, the minimum duration for hours and days is <b>1</b>.'
                        proceed = False
                    else:
                        if unit == 'hr' or unit == 'hrs':
                            converted_time = time * 60
                        elif unit == 'days' or unit == 'day':
                            converted_time = time * 1440

                if proceed:
                    group.pillory_time = converted_time
                    group.save()
                    time, unit = get_formatted_time(converted_time)
                    self.message = f'Group pillory time changed to  🕒  <b>{time} {unit}</b>  🕒  by {username}.'
            else:
                self.message = f'@{username}, you need to be an admin to set the pillory time of this group!'


    def set_default_pillory(self, user_id, group_id):
        if self.is_admin(None, self.dest_id, True, "spicebot"):
            user = User.objects.get(id=user_id)
            group = TelegramGroup.objects.get(id=group_id)
            username = user.telegram_user_details['username']
            
            if self.is_admin(user.telegram_id, self.dest_id, True):
                amt = float(self.text.split()[2].replace(',', ''))
                if amt < 1:
                    self.message = f"Minimum pillory cost is 1 \U0001f336 SPICE \U0001f336! Below that is just too harsh."
                else:                    
                    change = 'increased'
                    emoji = self.UP_ARROW
                    # basis = settings.INITIAL_MUTE_PRICE
                    basis = group.pillory_fee
                    group.pillory_fee = amt
                    group.save()

                    mute_obj_in_group = Mute.objects.filter(
                        group=group,
                        fee_changed=False
                    )

                    if mute_obj_in_group.exists():
                        mute_obj_in_group.update(
                            next_fee=amt
                        )

                    if basis > amt:
                        change = 'decreased'
                        emoji = self.DOWN_ARROW

                    amt = get_int_or_float(amt)
                    amt_str = get_amount_str(amt)
                    self.message = f"Admin @{username} has {change} the default pillory cost to:"
                    self.message += f"\n\n{emoji}  {amt_str} \U0001f336 SPICE \U0001f336  {emoji}"
            else:
                self.message = f"@{username}, you must be an admin of this group to set the default pillory cost!"


    def contribute_function(self, user_id, group_id, operation):
        if self.is_feat_disabled('rain') or self.is_feat_disabled('pillory'):
            self.message = get_maintenance_response('pillorie')
        else:
            if self.is_admin(None, self.dest_id, True, "spicebot"):
                splitted_text = self.text.split()
                target_username = splitted_text[1].replace('@', '')
                amount = float(splitted_text[2].replace(',', ''))
                user = User.objects.get(id=user_id)
                group = TelegramGroup.objects.get(id=group_id)
                username = user.telegram_user_details['username']
            
                if target_username == settings.TELEGRAM_BOT_USER:
                    self.message = f"Wait a sec @{username}, you are not allowed to {operation} me!"
                else:
                    target_user = self.target_user_exists_and_in_group(target_username, group)
                    if target_user:
                        if target_user.id == user.id:
                            self.message = f"@{username}, you can't {operation} yourself!"
                        else:
                            if self.is_admin(target_user.telegram_id, self.dest_id, True):
                                self.message = f"Hey @{username}, you are not allowed to do any {operation} operations to any admin!"
                            else:
                                if amount <= get_balance(user.id, settings.SPICE_TOKEN_ID):
                                    if amount > 0:
                                        mute = Mute.objects.filter(
                                            target_user=target_user,
                                            group=group
                                        )
                                        if mute.exists():
                                            mute = mute.first()
                                            if mute.is_muted:
                                                if operation == self.mute:
                                                    self.message = f"@{username}, user {target_username} is currently <code>{self.mute}d</code>  🤐"
                                                else:
                                                    self.process_pillory(user.id, mute.id, amount, self.unmute)
                                            else:
                                                if operation == self.mute:
                                                    if mute.remaining_fee == 0:
                                                        if mute.next_fee != 0:
                                                            mute.base_fee = mute.next_fee
                                                            mute.next_fee = 0
                                                            mute.save()

                                                        mute = Mute.objects.get(id=mute.id)
                                                        mute.duration = mute.group.pillory_time
                                                        mute.remaining_unmute_fee = mute.unmute_fee
                                                        mute.remaining_fee = mute.get_fee()
                                                        mute.save()

                                                    self.process_pillory(user.id, mute.id, amount, self.mute)
                                                else:
                                                    self.message = f"@{username}, user {target_username} is currently <code>{self.unmute}d</code>  😄"
                                        else:
                                            if operation == self.mute:
                                                base_fee = group.pillory_fee
                                                pillory_time = group.pillory_time

                                                if amount > base_fee:
                                                    init_mute_price = get_int_or_float(base_fee)
                                                    init_mute_price = get_amount_str(init_mute_price)
                                                    self.message = f"@{username}, the initial price for muting is {init_mute_price} \U0001f336 SPICE \U0001f336"
                                                else:
                                                    new_mute = Mute(
                                                        target_user=target_user,
                                                        group=group,
                                                        base_fee=base_fee,
                                                        remaining_fee=base_fee,
                                                        duration=pillory_time
                                                    )
                                                    new_mute.save()
                                                    self.process_pillory(user.id, new_mute.id, amount, self.mute, True)
                                            else:
                                                self.message = f"@{username}, user {target_username} is currently <code>{self.unmute}d</code>  😄"
                                    else:
                                        self.message = f"@{username}, contributing 0 \U0001f336 SPICE \U0001f336?\n\nNice try mate, but that ain't gonna work."
                                else:
                                    self.message = f"@{username}, you don't have enough \U0001f336 SPICE \U0001f336!"

    
    def switch_token_tip_status(self, token, operation, group_id):
        group = TelegramGroup.objects.get(id=group_id)
        token = token.upper()
        slp_token = SLPToken.objects.get(name=token)
        operation = operation.upper()
        status = operation == 'ON'

        if group.settings['token_tipping_status'][token] == status:
            return f"{token} {slp_token.emoji} tipping is already turned <b>{operation}</b>"
        else:
            group.settings['token_tipping_status'][token] = status
            group.save()
            return f"{token} {slp_token.emoji} tipping has been turned <b>{operation}</b>"
    

    def switch_pillory(self, user_id, group_id):
        user = User.objects.get(id=user_id)
        username = user.telegram_user_details['username']
        group = TelegramGroup.objects.get(id=group_id)

        if self.is_admin(user.telegram_id, self.dest_id, True):
            operation = self.text.split()[1].lower()
            change = "disabled"
            emoji = "❌"

            if operation == 'on':
                change = "enabled"
                emoji = "✅"
                

            group.settings['pillory_status'] = operation == 'on'
            group.save()

            self.message = f"Pillory feature {change} for this group  {emoji}"
        else:
            self.message = f"Stop right there @{username}, you need to be admin to enable or disable pillory feature!"


    def throw_pillory(self, user_id, group_id):
        user = User.objects.get(id=user_id)
        username = user.telegram_user_details['username']
        splitted_text = self.text.split()

        if len(splitted_text) == 2:
            emoji = splitted_text[1].split('@')[0]
            target_username = splitted_text[1].split('@')[1]
        else:
            emoji = splitted_text[1]
            target_username = splitted_text[2].replace('@', '')

        if target_username == settings.TELEGRAM_BOT_USER:
            self.message = f"Hold up @{username}. You can't do any mute operations on me."
        else:
            group = TelegramGroup.objects.get(id=group_id)
            target_user = self.target_user_exists_and_in_group(target_username, group)

            if target_user:
                if target_user.id == user.id:
                    self.message = f"@{username}, you can't throw pillory at thy self!"
                else:
                    if self.is_admin(target_user.telegram_id, self.dest_id, True):
                        self.message = f"Hey @{username}, you are not allowed to throw pillory to any admin!"
                    else:
                        mute = Mute.objects.filter(
                            is_muted=True,
                            target_user=target_user,
                            group=group
                        )

                        if mute.exists():
                            mute = mute.first()

                            # mute.count -= 1
                            # mute.save()
                            fee = mute.get_fee() / 0.99
                            # mute.count += 1
                            # mute.save()
                            
                            throw_price = 0
                            throw_operation = ''
                            default_mute_time = settings.DEFAULT_MUTE_TIME

                            if emoji in settings.ALLOWED_PILLORY_EMOJIS:
                                duration = settings.ALLOWED_PILLORY_EMOJIS[emoji]
                                throw_price = get_int_or_float((fee / default_mute_time) * duration, True)
                                throw_operation = self.prolong
                            elif emoji in settings.ALLOWED_UNMUTE_EMOJIS:
                                duration = settings.ALLOWED_UNMUTE_EMOJIS[emoji]
                                throw_price = (fee / default_mute_time) * duration
                                throw_price += throw_price * settings.UNMUTE_INTEREST
                                throw_price = get_int_or_float(throw_price, True)
                                throw_operation = self.lessen
                            else:
                                self.message = f"@{username}, thy emoji {emoji} used in throwing is invalid."
                                return
                            
                            if throw_price <= get_balance(user.id, settings.SPICE_TOKEN_ID):
                                response = self.collect_spice(user.id, mute.id, throw_operation, throw_price)
                                if response == "OK":
                                    if throw_operation == self.prolong:
                                        change = "+"
                                        mute.duration += duration
                                        mute.remaining_unmute_fee += throw_price
                                        mute.save()
                                    elif throw_operation == self.lessen:
                                        change = "-"
                                        temp_mute_duration = mute.duration - duration
                                        if temp_mute_duration < 0:
                                            temp_mute_duration = 0

                                        if mute.date_started <= (timezone.now() - timedelta(minutes=temp_mute_duration)):
                                            self.unmute_user(user.id, group.id, target_username)
                                        else:
                                            mute.duration -= duration
                                            mute.save()

                                    time, unit = get_formatted_time(duration)
                                    #self.message = f"<b>{username}</b> just spent {throw_price} \U0001f336 SPICE \U0001f336 to throw a {emoji} to <b>{target_username}</b>!"
                                    #self.message += f"\n\n{change}{time} {unit}  \U0001f552 to <b>{target_username}</b>'s mute duration"

                                    price_str = get_int_or_float(throw_price)
                                    price_str = get_amount_str(price_str)

                                    #time_str = f"{duration} minutes"
                                    #if emoji == "\U0001f987":
                                        #time_str = "1 week"

                                    self.message = f"<b>{username}</b> just spent {price_str} \U0001f336 SPICE \U0001f336 to throw a {emoji} to <b>{target_username}</b>!"
                                    self.message += f"\n\n{change}{time} {unit}  \U0001f552  to <b>{target_username}</b>'s mute duration"

                                elif response == "insufficient balance":
                                    self.message = f"@{username}, you don't have enough \U0001f336 SPICE \U0001f336!" 
                                else:
                                    logger.error(f"=========== PROBLEM: {response} ============")
                            else:
                                self.message = f"@{username}, you don't have enough \U0001f336 SPICE \U0001f336!" 
                        else:
                            self.message = f"@{username}, user {target_username} is currently <code>{self.unmute}d</code>  🤐"


    def clear_pillory(self, user_id, group_id):
        if self.is_admin(None, self.dest_id, True, "spicebot"):
            user = User.objects.get(id=user_id)
            group = TelegramGroup.objects.get(id=group_id)
            username = user.telegram_user_details['username']
            splitted_text = self.text.split()
            target_username = splitted_text[2].replace('@', '')
            
            if self.is_admin(user.telegram_id, self.dest_id, True):
                if target_username == settings.TELEGRAM_BOT_USER:
                    self.message = f"Wait a sec @{username}, I was not even pilloried in the first place, and never will be!"
                else:
                    target_user = self.target_user_exists_and_in_group(target_username, group)
                    if target_user:
                        if target_user.id == user.id:
                            self.message = f"@{username}, you can't clear your own pillory!"
                        else:
                            if self.is_admin(target_user.telegram_id, self.dest_id, True):
                                self.message = f"Hey @{username}, you are not allowed to do any mute operations to any admin!"
                            else:
                                mute = Mute.objects.filter(
                                    group=group,
                                    target_user=target_user
                                )

                                if mute.exists():
                                    mute = mute.first()
                                    if mute.is_muted:
                                        self.message = f"Woah, {target_username} is currently muted  🤐"
                                    else:
                                        if mute.remaining_fee == 0:
                                            self.message = f"It seems that {target_username} is currently unpilloried  😃"
                                        else:
                                            mute.is_being_unmuted = True
                                            mute.save()
                                            restrict_user(mute.id, True, True)
                                else:
                                    self.message = f"It seems that {target_username} is currently unpilloried  😃"
            else:
                self.message = f'@{username}, you must be an admin to clear pillories!'

    # def set_user_pillory_time(self, user_id, group_id):
    #     user = User.objects.get(id=user_id)
    #     username = user.telegram_user_details['username']
    #     group = TelegramGroup.objects.get(id=group_id)

    #     if self.is_admin(user.telegram_id, self.dest_id, True):
    #         splitted_text = self.text.split()
    #         target_username = splitted_text[2].replace('@', '')
    #         time = float(splitted_text[3].replace(',', ''))
    #         unit = splitted_text[4].lower()
        
    #         if target_username == settings.TELEGRAM_BOT_USER:
    #             self.message = f"Wait a sec @{username}, you are not allowed to {operation} me!"
    #         else:
    #             target_user = self.target_user_exists_and_in_group(target_username, group)
    #             if target_user:
    #                 if target_user.id == user.id:
    #                     self.message = f"@{username}, you can't set your own pillory time!"
    #                 else:
    #                     if self.is_admin(target_user.telegram_id, self.dest_id, True):
    #                         self.message = f"Hey @{username}, admins are immune to any pillory operations!"
    #                     else:
    #                         proceed = True
    #                         if unit == 'mins' or unit == 'min':
    #                             if time < 5:
    #                                 self.message = f"For your info @{username}, the minimum pillory time for mins is <b>5</b>  ℹ️"
    #                                 proceed = False
    #                         else:
    #                             if time < 1:
    #                                 self.message = f"For your info @{username}, the minimum pillory time for {unit} is <b>1</b>  ℹ️"
    #                                 proceed = False

    #                         if time <= 0:
    #                             self.message = f"Nice try @{username}, but setting a user's pillory time to {time} {unit} is a big no no!"
    #                             proceed = False


    #                         if proceed:
    #                             mute = Mute.objects.filter(
    #                                 target_user=target_user,
    #                                 group=group
    #                             )
    #                             if mute.exists():
    #                                 mute = mute.first()
    #                                 if not mute.is_muted and mute.remaining_fee == 0:
    #                                     mute.duration = self.to_minutes(time, unit)
    #                                 mute.static_duration = self.to_minutes(time, unit)
    #                                 mute.save()
    #                             else:
    #                                 group_mute_fee = Fee.objects.filter(
    #                                     group=group,
    #                                     fee_type=self.mute
    #                                 )

    #                                 base_fee = settings.INITIAL_MUTE_PRICE
    #                                 if group_mute_fee.exists():
    #                                     group_mute_fee = group_mute_fee.first()
    #                                     base_fee = group_mute_fee.amount

    #                                 new_mute = Mute(
    #                                     target_user=target_user,
    #                                     group=group,
    #                                     base_fee=base_fee,
    #                                     remaining_fee=0,
    #                                     duration=self.to_minutes(time, unit),
    #                                     static_duration=self.to_minutes(time, unit)
    #                                 )
    #                                 new_mute.save()

    #                             time_str = get_int_or_float(time)
    #                             time_str = get_amount_str(time_str)
    #                             self.message = f"{target_username}'s time adjusted to ⌛  {time_str} {unit}  ⌛\n\nThis will take effect next pillory."
    #     else:
    #         self.message = f"Sorry @{username}, setting other user's pillory time is for admins only."
        

    # def to_minutes(self, time, unit):
    #     if unit == 'mins' or unit == 'min':
    #         return time
    #     elif time == 'hrs' or unit == 'hr':
    #         return time * 60
    #     elif time == 'days' or unit == 'day':
    #         return time * 1440
