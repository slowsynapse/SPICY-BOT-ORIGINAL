from __future__ import absolute_import, unicode_literals
from subprocess import Popen, PIPE
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from celery.signals import task_failure
from bitcash import PrivateKey
from main.models import (
    Withdrawal,
    Media,
    Deposit,
    Content,
    FaucetDisbursement,
    User,
    Transaction,
    ErrorLog,
    TelegramGroup,
    WeeklyReport,
    Mute,
    SLPToken,
    Subscriber,
    Metric,
)
from main.utils.account import create_transaction, get_balance, swap_related_transactions
from main.utils.converter import convert_bch_to_slp_address
from main.utils.twitter import TwitterBot
from main.utils.reddit import RedditBot
from main.utils.aws import AWS
from main.utils import number_format
from main.utils.metrics import SpiceBotMetricHandler
from django.conf import settings
from django.utils import timezone
from operator import itemgetter
from random import random
from datetime import datetime, timedelta
from django.db.models import Sum, Q
from decouple import config as env
from PIL import Image
import requests
import logging
import traceback
import redis
import arrow
import celery
import os
import base64
import json
import traceback
import subprocess
from django.core.paginator import Paginator
from requests import *
import re
from django.db import IntegrityError
from django.conf import settings
from sseclient import SSEClient
logger = logging.getLogger(__name__)
from celery.task import Task

from constance import config
from django.db import transaction as trans



def post_slack_message(data):
    url = "https://slack.com/api"
    response = requests.post(
        f"{url}/chat.postMessage", data=data
    )

    rsp = None
    if response.status_code == 200:
        rsp = response.json()
        logger.info("============== Notification sent to slack ===============")

    return rsp
    
@task_failure.connect
def handle_task_failure(**kw):
    logger.error(traceback.format_exc())
    return traceback.format_exc()

@shared_task(rate_limit='20/s', queue='telegram')
def send_telegram_message(message, chat_id, update_id, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup, separators=(',', ':'))
        
    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
    )
    logger.info(response.text)
    if response.status_code == 200:
        if update_id:
            settings.REDISKV.sadd('telegram_msgs', update_id)
            if settings.REDISKV.scard('telegram_msgs') >= 10000:
                settings.REDISKV.spop('telegram_msgs')


@shared_task(queue='reddit')
def restart_supervisor():
    logger.info('Restarting')
    cmd = 'supervisorctl reload'
    r = subprocess.call(cmd, shell=True)

@shared_task(queue='twitter_dm')
def twitter_unreplied_post():
    bot = TwitterBot()
    bot.check_failed_reply()

@shared_task(queue='negative_balance')
def negative_balance():
    users_list=''
    chat_ids = [1148678934, 424063340, 845043679] #Reamon, Joemar, Jeth
    tokens = SLPToken.objects.all()
    trans = Transaction.objects.filter(running_balance__lt=0).distinct('user__id')
    users = trans.values('user__id') 
    spice_accounts = []
    honk_accounts = []
    drop_accounts  = []
    chili_accounts = []
    bch_accounts = []
    mist_accounts = []
    for account in users:
        for token in tokens:
            user = User.objects.get(id=account['user__id'])
            transaction = user.transactions.filter(slp_token__id=token.id).order_by('-date_created').first()
            if transaction:
                if round(transaction.running_balance, 4) < 0:
                    if token.token_id == '0f3f223902c44dc2bee6d3f77d565904d8501affba5ee0c56f7b32e8080ce14b':
                        drop_accounts.append(str(account['user__id']))
                    elif token.token_id == '4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf':
                        spice_accounts.append(str(account['user__id']))
                    elif token.token_id == '7f8889682d57369ed0e32336f8b7e0ffec625a35cca183f4e81fde4e71a538a1':
                        honk_accounts.append(str(account['user__id']))
                    elif token.token_id == 'f3af722ff99716db07f851af144eeaac433e8d5515f91bdd679d9a97edc49a24':
                        chili_accounts.append(str(account['user__id']))
                    elif token.token_id == 'd6876f0fce603be43f15d34348bb1de1a8d688e1152596543da033a060cff798':
                        mist_accounts.append(str(account['user__id']))
                    elif token.name.upper() == 'BCH':
                        bch_accounts.append(str(account['user__id']))

    spice_users = ','.join(spice_accounts)
    honk_users = ','.join(honk_accounts)
    drop_users = ','.join(drop_accounts)
    chili_users = ','.join(chili_accounts)
    mist_users = ','.join(mist_accounts)
    bch_users = ','.join(bch_accounts)

    message = "\U000026A0 NEGATIVE BALANCE FOUND \U000026A0\n"
    if spice_users:
        message += f"{len(spice_accounts)} user(s) have negative balance in SPICE: \n {spice_users} \n\n"
    if honk_users:
        message += f"{len(honk_accounts)} user(s) have negative balance in HONK: \n {honk_users} \n\n"
    if drop_users:
        message += f"{len(drop_accounts)} user(s) have negative balance in DROP: \n {drop_users} \n\n"
    if chili_users:
        message += f"{len(chili_accounts)} user(s) have negative balance in CHILI: \n {chili_users} \n\n"
    if mist_users:
        message += f"{len(mist_accounts)} user(s) have negative balance in MIST: \n {mist_users} \n\n"
    if bch_users:
        message += f"{len(bch_accounts)} user(s) have negative balance in BCH: \n {bch_users} \n\n"
    
    for chat_id in chat_ids:
        if spice_users is not '' or  honk_users is not '' or drop_users is not '' or chili_users is not '' or mist_users is not '' or bch_users is not '':
            send_telegram_message.delay(message, chat_id, None)
            data = {
                'token': settings.SLACK_TECHSUPPORT_BOT_TOKEN,
                'channel': settings.SLACK_TECHSUPPORT_CHANNEL_ID,
                'text': message,
            }
            post_slack_message(data)
            
@shared_task(queue='twitter')
def send_twitter_message(message, user_id):
    bot = TwitterBot()
    bot.send_direct_message(user_id, message)

def process_response_message(message, source):
    if source == 'twitter' or source == 'reddit':
        return re.sub('</?b>', '', message)
    return message

# admin feature for transferring of all token funds in telegram only
@shared_task(queue='transfer')
def transfer_telegram_funds(sender_id, recipient_id):
    sender_qs = User.objects.filter(id=sender_id)
    recipient_qs = User.objects.filter(id=recipient_id)

    if sender_qs.exists():
        if recipient_qs.exists():
            tokens = SLPToken.objects.all()

            for token in tokens:
                amount = get_balance(sender_id, token.token_id)

                if amount > 0:
                    # print(f'Amount: {amount}')

                    # transaction_hash = f"{sender_id}-{token.name}-{timezone.now().strftime('%D %T')}"
                    created, sender_thash = create_transaction(
                        sender_id,
                        amount,
                        'Outgoing',
                        token.id,
                        settings.TXN_OPERATION['TRANSFER']
                        # transaction_hash=transaction_hash
                    )

                    # transaction_hash = f"{recipient_id}-{token.name}-{timezone.now().strftime('%D %T')}"
                    created, recipient_thash = create_transaction(
                        recipient_id,
                        amount,
                        'Incoming',
                        token.id,
                        settings.TXN_OPERATION['TRANSFER']
                        # transaction_hash=transaction_hash
                    )

                    swap_related_transactions(sender_thash, recipient_thash)
                    print(f'Transferred: {amount} {token.name}')
                else:
                    print(f'Zero balance for {token.name}')

            return True
        else:
            print(f'User ID {recipient_id} does not exist!')
    else:
        print(f'User ID {sender_id} does not exist!')
    
    return False
        


@shared_task(queue='transfer')
def transfer_spice_to_another_acct(sender_id, recipient_id, amount):
    from main.models import Response, User

    sender_qs = User.objects.filter(id=sender_id)
    recipient_qs = User.objects.filter(id=recipient_id)
    if sender_qs.exists() and recipient_qs.exists():
        sender = sender_qs.first()
        recipient = recipient_qs.first()
        recipient_source = recipient.get_source
        sender_source = sender.get_source

        recipient_user_id = recipient_id
        sender_user_id = sender_id

        recipient_account_id = None
        sender_account_id = None

        if recipient_source == 'twitter':
            recipient_account_id = recipient.twitter_user_details['id']
        elif recipient_source == 'reddit':
            recipient_account_id = recipient.reddit_user_details['user_id']
        elif recipient_source == 'telegram':
            recipient_account_id = recipient.telegram_user_details['id']
        elif recipient_source == 'other':
            recipient_account_id = recipient.user_details['id']
            recipient_source = recipient.user_details['app_name']

        if sender_source == 'twitter':
            sender_account_id = sender.twitter_user_details['id']
        elif sender_source == 'reddit':
            sender_account_id = sender.reddit_user_details['user_id']
        elif sender_source == 'telegram':
            sender_account_id = sender.telegram_user_details['id']            
        elif sender_source == 'other':
            sender_account_id = sender.user_details['id']
            sender_source = sender.user_details['app_name']

        if get_balance(sender.id, settings.SPICE_TOKEN_ID) >= amount:
            token = SLPToken.objects.get(token_id=settings.SPICE_TOKEN_ID)
            # Create the outgoing transaction
            create_transaction(sender.id, amount, 'Outgoing', token.id, settings.TXN_OPERATION['TRANSFER'])
            # Create the incoming transaction
            create_transaction(recipient.id, amount, 'Incoming', token.id, settings.TXN_OPERATION['TRANSFER'])

            recipient_message = f'You have received a transfer amount of {amount} \U0001f336 SPICE \U0001f336 from the {sender_source} account: <b>{sender.get_username}</b>'
            recipient_message = process_response_message(recipient_message, recipient_source)

            if recipient_source == 'twitter':
                send_twitter_message(recipient_message, recipient_account_id)
            elif recipient_source == 'reddit':
                bot = RedditBot()
                subject = 'Successful Transfer'
                body = {
                    'message':recipient_message,
                    'subject':subject,
                    'sender':recipient.get_username
                }
                resp = Response(
                    response_type='direct_message',
                    body=body
                )
                resp.save()
                bot.send_message(recipient_message, subject, recipient.get_username, resp.id)
            elif recipient_source == 'telegram':
                send_telegram_message(recipient_message, recipient_account_id, None)

            sender_response_message = f'Successfully transferred \U0001f336 {amount} SPICE \U0001f336 to {recipient_source} account: <b>{recipient.get_username}</b>'
            return process_response_message(sender_response_message, sender_source)
        else:
            err_message = f"<b>@{sender.get_username}</b>, you don't have enough \U0001f336 SPICE \U0001f336!"
            return process_response_message(err_message, sender_source)

@shared_task(queue='reddit')
def send_reddit_message(message, username):
    from main.models import Response
    bot = RedditBot()
    subject = 'Successful Deposit'
    body = {
        'message':message,
        'subject':subject,
        'sender':username
    }
    resp = Response(
        response_type='direct_message',
        body=body
    )
    resp.save()
    bot.send_message(message, subject, username, resp.id)

@shared_task(queue='reddit')
def reddit_unreplied_post():
    bot = RedditBot()
    bot.check_failed_reply()


@shared_task(queue='logs')
def error_prompt(log=None, **kwargs):
    type_of_error = kwargs.get('type', None)
    if type_of_error is not None and log is not None:
        errors = ErrorLog.objects.filter(logs=log)
        notify = True
        if errors.exists():
            err = errors.first()
            diff = timezone.now() - err.last_notified
            if diff.seconds < 600:
                notify = False
                err.last_notified = timezone.now()
                err.save()
        else:
            err = ErrorLog(
                origin=type_of_error,
                logs=log
            )
            err.save()
        if notify:        
            text = f"*{type_of_error}*\n```{log}```"
            data = {
                'token': settings.SLACK_TECHSUPPORT_BOT_TOKEN,
                'channel': settings.SLACK_TECHSUPPORT_CHANNEL_ID,
                'text': text,
            }
            post_slack_message(data)
        # last_log = settings.REDISKV.get('last_error_log')
        # if not last_log:
        #     last_log = timezone.now().strftime('%D %T')
        #     settings.REDISKV.set('last_error_log',last_log)
        # else:
        #     last_log = str(last_log.decode())
        # last_dt = datetime.strptime(last_log, '%m/%d/%y %H:%M:%S')
        # current_dt = datetime.strptime(
        #     timezone.now().strftime('%D %T'),
        #     '%m/%d/%y %H:%M:%S'
        # )
        # diff = current_dt - last_dt
        # The bot will send a notification to the admins
        # every 10 minutes if errors still exist.
        # if diff.total_seconds() > 600:
        #     new_log = timezone.now().strftime('%D %T')
        #     settings.REDISKV.set('last_error_log',new_log)
        #     msg = 'Hey! An error was found. See error logs.'
        #     chat_ids = [1148678934, 424063340, 845043679] #Reamon, Joemar, Jeth
        #     for chat_ids in chat_ids:
        #         send_telegram_message.delay(msg, chat_id, None)
            
@shared_task(queue='telegram')
def stats_weekly_report():
    report = []
    groups = TelegramGroup.objects.all()
    threshold = timezone.now() - timedelta(days=7)

    for group in groups:
        data = {}
        data['group'] = group.title
        #telegram
        content = Content.objects.filter(source='telegram', details__message__chat__id__iexact=group.chat_id, date_created__gt=threshold)
        parent_content = content.filter(parent=None)
        data['total_weekly_contents'] = parent_content.count()
        data['total_tips'] = content.aggregate(Sum('tip_amount'))['tip_amount__sum']
        report.append(data)

    report = sorted(report, key=itemgetter('total_weekly_contents'))
    weekly_report = WeeklyReport(
        report = json.dumps(report)
    )
    weekly_report.save()
    url = '%s/api/weekly-report/%s' % (settings.DOMAIN, weekly_report.id)
    admins = [424063340, 367409363] # Joemar , Reamon
    message = 'Hello there. Here\'s our report of telegram groups\' weekly performance.\n\n%s' % url
    for admin_id in admins:
        send_telegram_message.delay(message, admin_id, None)
    logger.info('Report: %s', report)


@shared_task(rate_limit='20/s', queue='withdrawal', bind=True, max_retries=10)
def withdraw_spice_tokens(self, withdrawal_id, chat_id=None, update_id=None, user_id=None, bot='telegram'):
    withdrawal = Withdrawal.objects.get(id=withdrawal_id)

    logger.info(f'PROCESSING CHECKING WITHDRAWALS FOR {withdrawal.user.get_username}')
    if not withdrawal.date_started and not withdrawal.date_failed and withdrawal.slp_token:
        # Mark as started
        withdrawal.date_started = timezone.now()
        withdrawal.save()

        if 'bch' not in withdrawal.slp_token.name.lower():
            balance = get_balance(withdrawal.user.id, withdrawal.slp_token.token_id)
        else:
            balance = get_balance(withdrawal.user.id, 'bch')
        if bot != 'telegram':
            balance = int(balance)

        if balance < withdrawal.amount_with_fee:
            fee_percentage = withdrawal.slp_token.withdrawal_percentage_fee * 100
            if fee_percentage.is_integer():
                fee_percentage = int(fee_percentage)
            
            amount_fee = format(withdrawal.amount_with_fee, ",")
            fee = round(withdrawal.fee, 2)
            
            message = f"You don\'t have enough {withdrawal.slp_token.emoji} {withdrawal.slp_token.name} {withdrawal.slp_token.emoji}!"
            message += f"\n\nWithdrawals for {withdrawal.slp_token.name} require a fee that is {fee_percentage}% of the withdrawal amount"
            message += f" (fee = {fee} {withdrawal.slp_token.name})"
            message += f"\n\nYour total payment must be {amount_fee} {withdrawal.slp_token.name} {withdrawal.slp_token.emoji}"

            send_telegram_message.delay(message, chat_id, update_id)
            
            Withdrawal.objects.filter(id=withdrawal.id).delete()

        if balance >= withdrawal.amount_with_fee:

            username = withdrawal.user.telegram_display_name
            message = f"<b>@{username}</b>, your {withdrawal.slp_token.emoji} {withdrawal.slp_token.name} {withdrawal.slp_token.emoji} withdrawal request is being processed."
            send_telegram_message.delay(message, chat_id, update_id)

            status = ''

            if withdrawal.withdraw_all:
                if withdrawal.slp_token.token_id:
                    # If a user decided to withdraw all, we removed the decimal.
                    # This is only applicable for SLP Tokens.
                    withdrawable_amount = round(withdrawal.amount, 2)
            else:
                withdrawable_amount = withdrawal.amount

            spice_funding_wif = env('SPICE_FUNDING_WIF')
            funding_wif = base64.b64decode(spice_funding_wif.encode()).decode()

            pk = PrivateKey(funding_wif)
            if withdrawal.slp_token.name.lower() == 'bch':
                private_key = pk.to_hex()
                cmd = 'node /code/spiceslp/send-bch.js {0} {1} {2} {3}'.format(
                    withdrawal.address,
                    withdrawable_amount,
                    pk.address,
                    funding_wif
                )
            else:
                slp_address = convert_bch_to_slp_address(pk.address)
                cmd = 'node /code/spiceslp/send-tokens.js {0} {1} {2} {3} {4}'.format(
                    withdrawal.address,
                    withdrawable_amount,
                    withdrawal.slp_token.token_id,
                    slp_address,
                    funding_wif
                )
            try:
                p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
                stdout, _ = p.communicate()
                result = stdout.decode('utf8')
                logger.info(cmd)
                logger.info(f'{result}')
                status = result.splitlines()[-1].strip()
                logger.info(f'{status} - WITHDRAWAL')
            except Exception as exc:
                logger.error(exc)
                pass

            if status == 'success':
                # Update withdrawal completion and txid
                withdrawal.date_completed = timezone.now()
                txid = result.splitlines()[-2].split('/tx/')[-1]
                withdrawal.transaction_id = txid
                withdrawal.save()
            
                # Create the withdrawal transaction
                transaction_hash = f"{txid}-{user_id}-{withdrawal.slp_token.name}-{withdrawal.amount_with_fee}"
                created, w_hash_1 = create_transaction(
                    withdrawal.user.id,
                    withdrawal.amount_with_fee,
                    'Outgoing',
                    withdrawal.slp_token.id,
                    settings.TXN_OPERATION['WITHDRAW'],
                    transaction_hash=transaction_hash
                )

                # add fee to Tax Collector user
                transaction_hash = f"{txid}-{settings.TAX_COLLECTOR_USER_ID}-{withdrawal.slp_token.name}-{withdrawal.fee}"
                created, w_hash_2 = create_transaction(
                    settings.TAX_COLLECTOR_USER_ID,
                    withdrawal.fee,
                    'Incoming',
                    withdrawal.slp_token.id,
                    settings.TXN_OPERATION['WITHDRAW'],
                    transaction_hash=transaction_hash
                )

                swap_related_transactions(w_hash_1, w_hash_2)

                # Send notifications
                w_amount = number_format.round_sig(withdrawal.amount)
                message1 = f'Your withdrawal of {w_amount} {withdrawal.slp_token.name} tokens has been processed.'
                message1 += '\nhttps://explorer.bitcoin.com/bch/tx/' + txid
                if bot == 'telegram':
                    send_telegram_message.delay(message1, chat_id, update_id)
                elif bot == 'twitter':
                    send_twitter_message.delay(message1, user_id)
                elif bot == 'reddit':
                    send_reddit_message.delay(message1, user_id)
                
                balance2 = get_balance(withdrawal.user.id, withdrawal.slp_token.token_id)
                if bot != 'telegram':
                    balance2 = int(get_balance(withdrawal.user.id, withdrawal.slp_token.token_id))
                else:
                    balance2 = '{:0,.2f}'.format(balance2)

                message2 = f'Your updated balance is {balance2} {withdrawal.slp_token.emoji} {withdrawal.slp_token.name} {withdrawal.slp_token.emoji}'
                if bot == 'telegram':
                    send_telegram_message.delay(message2, chat_id, update_id)
                elif bot == 'twitter':
                    send_twitter_message.delay(message2, user_id)
                elif bot == 'reddit':
                    send_reddit_message.delay(message2, user_id)

            elif status == 'failure':
                logger.info('\nretry failed\n')
                withdrawal.date_failed = timezone.now()
                withdrawal.save()
                # message = 'Processing of your withdrawal request failed:'
                # message += '\n' + result.splitlines()[-2].strip()
                message = f'An error occured in sending {withdrawal.slp_token.name}. The dev team has been notified and will fix this very soon. Please try again later.'
                if bot == 'telegram':
                    send_telegram_message.delay(message, chat_id, update_id)
                elif bot == 'twitter':
                    send_twitter_message.delay(message, user_id)
                elif bot == 'reddit':
                    send_reddit_message.delay(message, user_id)
                # msg = 'No error found yet max retried exceeded.'
                msg = result
                error_prompt.delay(log=msg, **{'type': 'withdrawal'})
            else:
                error_prompt.delay(log=result, **{'type': 'withdrawal'})
                    
            
    

@shared_task(queue='slpnotify')
def slpnotify():	
    user = User.objects.filter(slpnotified=False).first()
    for acceptedtoken in SLPToken.objects.all():
        for tokenaddress in [user.simple_ledger_address, user.bitcoincash_address]:
            token = f"Token {settings.SLPNOTIFY_TOKEN}" # Subscription token from SLPNotify
            header = {"authorization": token}
            data = {
                "tokenid": acceptedtoken.token_id,
                "tokenname": acceptedtoken.name,
                "tokenAddress": tokenaddress, # BCH / SPLAddress
                "destinationAddress": f"{settings.DOMAIN}/slpnotify/" #Specialized view the receives notification from SLPNotify
            }
            url = settings.WATCHTOWER_SUBSCRIPTION_ENDPOINT
            resp = requests.post(url,headers=header,data=data)
            if resp.status_code != 200:
                raise Exception("SLPNotify wasn't able to complete the request")
    if user:
        user.slpnotified = True
        user.save()
        logger.info(f"user : {user} has been added to slpnotify")
    else:
        logger.info('All users had been recorded to slpnotify...')


@shared_task(queue='reddit')
def check_reddit_mentions(subreddit):
    bot = RedditBot()
    bot.process_subreddit_mentions(subreddit)

@shared_task(queue='subreddit')
def process_reddit_mentions():
    subreddits = ['testingground4bots']
    if settings.DEPLOYMENT_INSTANCE == 'prod':
        subreddits += ['btc', 'bitcoincash','hotsauce', 'HotPeppers']

    for subreddit in subreddits:
        check_reddit_mentions.delay(subreddit)

@shared_task(queue='reddit')
def check_reddit_messages():
    bot = RedditBot()
    bot.process_messages()

@shared_task(queue='twitter')
def check_twitter_mentions():
    bot = TwitterBot()
    bot.process_mentions()

@shared_task(queue='twitter')
def check_twitter_messages():
    bot = TwitterBot()
    bot.process_direct_messages()

def process_deposit(*args, **kwargs):
    logger.info('\n\n=========== PROCESSING A DEPOSIT ================\n')
    from main.models import User, Deposit
    from django.db import IntegrityError
    addr = kwargs['addr']
    txn_id = kwargs['txn_id']
    amt = kwargs['amt']
    source = kwargs['source']
    if addr.startswith('bitcoincash:'):
        user = User.objects.filter(bitcoincash_address=addr)
    else:
        user = User.objects.filter(simple_ledger_address=addr)
    qs = Deposit.objects.filter(transaction_id=txn_id, date_processed=None)
    if user.exists():
        if qs.exists():
            deposit = qs.first()
            usr = user.first()
            deposit.source = source
            deposit.date_processed=timezone.now()
            try:
                deposit.save()
                send_notif = True
                logger.info('<-!-!-!- via %s : New Deposit Found [%s] %s -!-!-!->' % (source, amt , txn_id))
            except IntegrityError as e:
                send_notif = False
            if send_notif:
                # Create the deposit transaction
                transaction_hash = f"{txn_id}-{usr.id}-{deposit.slp_token.name}-{deposit.amount}"
                created, recipient_thash = create_transaction(
                    usr.id,
                    deposit.amount,
                    'Incoming',
                    deposit.slp_token.id,
                    settings.TXN_OPERATION['DEPOSIT'],
                    transaction_hash=transaction_hash,
                    connected_transactions=[txn_id]
                )

                if created:
                    amount = number_format.round_sig(deposit.amount)
                    message1 = f'Your deposit transaction of {amount} {deposit.slp_token.emoji} {deposit.slp_token.name} has been credited to your account.'
                    chat_id = usr.telegram_id
                    message1 += '\nhttps://explorer.bitcoin.com/bch/tx/' + txn_id
                    if usr.telegram_id:
                        send_telegram_message.delay(message1, chat_id, str(random()).replace('0.', ''))
                    if usr.twitter_id:
                        send_twitter_message.delay(message1, usr.twitter_id)
                    if usr.reddit_id:
                        send_reddit_message.delay(message1, usr.reddit_username)
                    logger.info(f"Deposited {amt} {deposit.slp_token.name} to {addr}")


@shared_task(queue='deposit')
def check_deposit_confirmations():
    logger.info("===== CHECKING BIG DEPOSIT CONFIRMATIONS =====")
    deposits = settings.REDISKV.smembers('big_deposits')
    for key in deposits:
        args = key.decode().split('__')
        if len(args) == 3:
            txn_id, address, amount = args
            proceed = False
            try:
                if address.startswith('bitcoincash:'):
                    user = User.objects.get(
                        bitcoincash_address=address
                    )
                else:
                    user = User.objects.get(
                        simple_ledger_address=address
                    )
                proceed = True
            except User.DoesNotExist:
                pass
            if proceed:
                url = 'https://rest.bch.actorforth.org/v2/transaction/details/' + txn_id
                resp = requests.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data['confirmations'] >= 1:
                        qs = Deposit.objects.filter(transaction_id=txn_id)
                        if qs.exists():
                            deposit = qs.first()
                            if not deposit.date_processed:
                                kwargs = {
                                    'addr':address,
                                    'amt':amount,
                                    'txn_id':txn_id,
                                    'source': 'Spicebot-Big-Deposit'
                                }
                                process_deposit(**kwargs)
                                logger.info('Big deposit: %s, confirmed' % txn_id)
                        # Remove from set
                        settings.REDISKV.srem('big_deposits', key)
                    else:
                        logger.info('Big deposit: %s, waiting for confirmation' % txn_id)
            else:
                settings.REDISKV.srem('big_deposits', key)


def deposit_analyzer(*args, **kwargs):
    logger.info('\n\n============= deposit_analyzer ===============\n')
    txn_id = kwargs['txn_id']
    address = kwargs['addr']
    amt = kwargs['amt']
    token_id = kwargs['token_id']
    
    slp_token = SLPToken.objects.get(token_id=token_id)
    block = kwargs.get('block', None)
    if amt <= slp_token.big_deposit_threshold or block is not None:
        process_deposit(**kwargs)
    else:
        if block is None:
            key = txn_id + '__' + address + '__' + str(amt)
            if not settings.REDISKV.sismember('big_deposits', key):
                # Add txn_id to big deposits
                settings.REDISKV.sadd('big_deposits', key)
                if address.startswith('bitcoincash:'):
                    user_check = User.objects.filter(bitcoincash_address=address)
                else:
                    user_check = User.objects.filter(simple_ledger_address=address)
                if user_check.exists():
                    user = user_check.first()
                    amount = '{:0,.5f}'.format(float(amt))
                    threshold = '{:0,.5f}'.format(float(slp_token.big_deposit_threshold))

                    message1 = f'We detected your deposit of {amount} {slp_token.name}.'
                    message1 += f' For any amount greater than {threshold} {slp_token.name} we only credit it to your account after at least 1 confirmation.'
                    message1 += ' We will update you once your deposit is credited.'
                    if user.telegram_id:
                        chat_id = user.telegram_id
                        send_telegram_message.delay(message1, chat_id, str(random()).replace('0.', ''))
                    if user.twitter_id:
                        send_twitter_message.delay(message1, user.twitter_id)
                    if user.reddit_id:
                        send_reddit_message.delay(message1, user.reddit_username)
                    user.last_activity = timezone.now()
                    user.save()
                    Deposit.objects.filter(transaction_id=txn_id).update(source='waiting-for-confirmation')
                

def deposit_initial_save(**kwargs):
    #Note: added recording slp token used in saving deposit

    created = False
    amt = kwargs.get('amt')
    txn_id = kwargs.get('txn_id')
    address = kwargs.get('address')
    token_id = kwargs.get('token_id')
    spent_index = kwargs.get('spent_index')
    if address.startswith('bitcoincash:'):
        token = SLPToken.objects.filter(name='BCH')
        user_qs = User.objects.filter(bitcoincash_address=address)
    else:
        token = SLPToken.objects.filter(token_id=token_id)
        user_qs = User.objects.filter(simple_ledger_address=address)
    obj = None
    if user_qs.exists():
        user = user_qs.first()
        deposit_qs = Deposit.objects.filter(transaction_id=txn_id, user=user)
        if not deposit_qs.exists() and token.exists():
            obj, created = Deposit.objects.get_or_create(
                transaction_id=txn_id,
                amount=amt,
                user=user,
                slp_token=token.first(),
                spentIndex=spent_index
            )
        else:
            obj = deposit_qs.first()
    return obj, created


def filter_deposit_data(readable_dict, source):
    logger.info('\n\n=============== filter_deposit_data ==================\n')
    if len(readable_dict['data']) != 0:

        #Here <===============================================

        token_id = readable_dict['data'][0]['slp']['detail']['tokenIdHex']
        token = SLPToken.objects.filter(token_id=token_id) 

        if token.exists():
            if 'tx' in readable_dict['data'][0].keys():
                txn_id = readable_dict['data'][0]['tx']['h']
                slp_address= readable_dict['data'][0]['slp']['detail']['outputs'][0]['address']
                amt = float(readable_dict['data'][0]['slp']['detail']['outputs'][0]['amount'])
                obj, created = deposit_initial_save(**{'amt': amt, 'slp_address': slp_address, 'txn_id': txn_id, 'token_id': token_id})
                if created:
                    deposit_analyzer(**{ 'addr':slp_address, 'amt':amt, 'txn_id':txn_id, 'source': source, 'token_id': token_id})            

@shared_task(queue='deposit_socket')
def deposit_socket(url):
    logger.info('\n\n============== deposit_socket =================\n')
    source = url.split('://')[-1].split('/')[0]
    if source == 'slpsocket.fountainhead.cash':
        resp = requests.get(url, stream=True)
        logger.info('socket ready in : %s' % source)
        previous = ''
        for content in resp.iter_content(chunk_size=1024*1024):
            loaded_data = None
            try:
                content = content.decode('utf8')
                if '"tx":{"h":"' in previous:
                    data = previous + content
                    data = data.strip().split('data: ')[-1]
                    loaded_data = json.loads(data)
            except (ValueError, UnicodeDecodeError, TypeError) as exc:
                msg = traceback.format_exc()
                # error_prompt.delay(log=msg, **{'type': 'deposit'})
                pass
            previous = content
            if loaded_data is not None:
                if len(loaded_data['data']) > 0:
                    info = loaded_data['data'][0]
                    if 'slp' in info.keys():
                        if 'detail' in info['slp'].keys():
                            if 'tokenIdHex' in info['slp']['detail'].keys():

                                #Here <====================================

                                token_id = info['slp']['detail']['tokenIdHex']
                                token = SLPToken.objects.filter(token_id=token_id)

                                if token.exists():
                                    amt = float(info['slp']['detail']['outputs'][0]['amount'])
                                    slp_address = info['slp']['detail']['outputs'][0]['address']
                                    if 'tx' in info.keys():
                                        # There are transactions that don't have Id. Weird - Reamon
                                        txn_id = info['tx']['h']
                                        obj, created = deposit_initial_save(**{'amt': amt, 'slp_address': slp_address, 'txn_id': txn_id, 'token_id': token_id})
                                        if created:
                                            deposit_analyzer(**{ 'addr':slp_address, 'amt':amt, 'txn_id':txn_id, 'source': source, 'token_id': token_id})
                                        
    else:
        if source == 'slpsocket.bitcoin.com':
            resp = requests.get(url, stream=True)
            logger.info('socket ready in : %s' % source)
            for content in resp.iter_content(chunk_size=1024*1024):
                decoded_text = content.decode('utf8')
                if 'heartbeat' not in decoded_text:
                    data = decoded_text.strip().split('data: ')[-1]
                    loaded_data = json.loads(data)
                    filter_deposit_data(loaded_data, source)
        else:
            source = 'slpsocket.spice'
            messages = SSEClient(url)
            logger.info('socket ready in : %s' % source)
            for message in messages:
                if message.data:
                    loaded_data = json.loads(message.data)
                    filter_deposit_data(loaded_data, source) 

@shared_task(bind=True, queue='deposit_block', max_retries=10)
def block_height_checker(self, *args, **kwargs):
    logger.info('\n\n============= block_height_checker ==============\n')
    import requests
    import json
    from main.models import BitcoinBlockHeight
    url = 'https://rest.bch.actorforth.org/v2/blockchain/getBlockchainInfo'
    try:
        resp = requests.get(url)
        number = json.loads(resp.text)['blocks']
    except Exception as exc:
        self.retry(countdown=60)
    bheights = BitcoinBlockHeight.objects.filter(number=number)
    if bheights.count() > 1:
        keeper = bheights.first()
        bheights.exclude(number=keeper).delete()
    
    bheight = BitcoinBlockHeight.objects.filter(processed=False).order_by('-number').last()
    beginning = 0
    if bheight is not None:
        beginning = bheight.number
    last_instance, created = BitcoinBlockHeight.objects.get_or_create(number=number)
    if created:
        if beginning == 0:
            previous_number = last_instance.number
            beginning = previous_number
        kw = {
            'beginning': beginning,
            'ending': last_instance.number
        }
        unprocessed_deposits.delay(**kw)

@shared_task(queue='per_block_deposit_scanner')
def unprocessed_deposits(*args, **kwargs):
    logger.info(f'--> RUNNING UNPROCESSED DEPOSITS <--')
    from main.models import User, BitcoinBlockHeight
    from django.conf import settings
    import requests
    import json
    heightcount = BitcoinBlockHeight.objects.count()
    beg_number = kwargs['beginning']
    end_number = kwargs['ending']
    while end_number >= beg_number:
        instance, created = BitcoinBlockHeight.objects.get_or_create(number=end_number)
        sep = '===='
        heightnumber = instance.number
        url = 'https://rest.bch.actorforth.org/v2/block/detailsByHeight/%s' % heightnumber
        resp = requests.get(url)
        data = json.loads(resp.text)
        if 'error' not in data.keys():
            transactions = data['tx']
            for txn_id in transactions:
                logger.info(f'{sep} CHECKING BLOCK {instance.number} - TR : {txn_id} {sep}')
                temp_url = 'https://rest.bch.actorforth.org/v2/slp/txDetails/%s' % (txn_id)
                res = requests.get(temp_url)
                if res.status_code == 200:
                    this = json.loads(res.text)
                    if this['tokenInfo']['transactionType'].lower() == 'send':

                        #Here < ======================================

                        token_id = this['tokenInfo']['tokenIdHex']
                        token = SLPToken.objects.filter(token_id=token_id)

                        if token.exists():
                            amt = float(this['tokenInfo']['sendOutputs'][1]) / 100000000
                            legacy = this['retData']['vout'][1]['scriptPubKey']['addresses'][0]
                            url = 'https://rest.bch.actorforth.org/v2/address/details/%s' % legacy
                            resp = requests.get(url)
                            data = json.loads(resp.text)
                            if not 'error' in data.keys():
                                slp_address = data['slpAddress']
                                qs = User.objects.filter(simple_ledger_address=slp_address)
                                if qs.exists():
                                    user = qs.first()
                                    slp_address = user.simple_ledger_address
                                    obj, created = deposit_initial_save(**{'amt': amt, 'slp_address': slp_address, 'txn_id': txn_id, 'token_id': token_id})
                                    if obj:
                                        if not obj.date_processed:
                                            kwargs = {
                                                'addr':slp_address,
                                                'amt':amt,
                                                'txn_id':txn_id,
                                                'source': 'per-block-scanning'
                                            }
                                            process_deposit(**kwargs)
                                            logger.info('Per Block Scanning Deposit: %s, confirmed' % txn_id)
                
            instance.processed = True
            instance.save()
        end_number -= 1

@shared_task(queue='scan_user_deposits')
def kickstart_userscan():
    logger.info('\n\n================== kickstart_userscan =============\n')
    overallcount = User.objects.all().count()
    incrementby = 10000
    beg = 0
    end = incrementby
    while beg <= overallcount:
        users = list(User.objects.all().values_list('id', flat=True)[beg:end])
        for userid in users:
            user_scanner.delay(userid)
            beg += incrementby
            end += incrementby

@shared_task(queue='scan_user_deposits')
def user_scanner(id):
    logger.info('\n\n=========== user_scanner =============== \n')
    user = User.objects.filter(id=id)
    if user.exists():
        user = user.first()
        addr = user.simple_ledger_address

        #Here <=====================================

        url = f'https://rest.bch.actorforth.org/v2/slp/transactions/{settings.SPICE_TOKEN_ID}/{addr}'
        resp = requests.get(url)
        proceed = True
        data = []
        try:
            text = resp.text
            data = json.loads(text)
        except Exception as exc:
            proceed = False
        if proceed and len(data) != 0:
            try:
                for tr in data:
                    for output in tr['tokenDetails']['detail']['outputs']:
                        qs = Deposit.objects.filter(transaction_id=tr['txid'])
                        if output['address'] == addr and not qs.exists():
                            temp_url = 'https://rest.bch.actorforth.org/v2/slp/txDetails/%s' % (tr['txid'])
                            res = requests.get(temp_url)
                            if res.status_code == 200:
                                this = json.loads(res.text)
                                if this['tokenInfo']['transactionType'].lower() == 'send':

                                    #Here <=======================================

                                    token_id = this['tokenInfo']['tokenIdHex']
                                    token = SLPToken.objects.filter(token_id=token_id)

                                    if token.exists():
                                        amt = float(this['tokenInfo']['sendOutputs'][1]) / 100000000
                                        legacy = this['retData']['vout'][1]['scriptPubKey']['addresses'][0]
                                        url = 'https://rest.bch.actorforth.org/v2/address/details/%s' % legacy
                                        resp = requests.get(url)
                                        data = json.loads(resp.text)
                                        if not 'error' in data.keys():
                                            slp_address = data['slpAddress']
                                            qs = User.objects.filter(simple_ledger_address=slp_address)
                                            if qs.exists():
                                                user = qs.first()
                                                slp_address = user.simple_ledger_address
                                                obj, created = deposit_initial_save(**{'amt': amt, 'slp_address': slp_address, 'txn_id': tr['txid'], 'token_id': token_id})
                                                if obj:
                                                    if not obj.date_processed:
                                                        kwargs = {
                                                            'addr':slp_address,
                                                            'amt':amt,
                                                            'txn_id':tr['txid'],
                                                            'source': 'per-user-scanning'
                                                        }
                                                        process_deposit(**kwargs)
                                                        logger.info('Per User Scanning Deposit: %s, confirmed' % tr['txid'])
            except Exception as exc:
                msg = f'browse this url to check error existence : {exc}, URL: {url}'
                logger.error(msg)

@shared_task(bind=True, queue='media', max_retries=10, soft_time_limit=60)
def download_upload_file(self, file_id, file_type, content_id):
    if Content.objects.filter(id=content_id).exists():
        media_check = Media.objects.filter(file_id=file_id)
        if not media_check.count():
            # Get the download url
            bot_token = settings.TELEGRAM_BOT_TOKEN
            response = requests.get('https://api.telegram.org/bot' + bot_token + '/getFile?file_id=' + file_id)

            if response:
                file_path = response.json()['result']['file_path']
                download_url = 'https://api.telegram.org/file/bot' + bot_token + '/' + file_path

                if file_type in ['photo', 'sticker']:
                    if file_type == 'photo':
                        # Download photo
                        r = requests.get(download_url)
                        temp_name = '/tmp/' + file_id + '-temp' + '.jpg'
                        filename = '/tmp/' + file_id + '.jpg'
                        with open(temp_name, 'wb') as f:
                            f.write(r.content)
                        try:
                            im = Image.open(temp_name).convert("RGB")
                            im.save(filename,"jpeg")
                        except OSError as exc:
                            self.retry(countdown=5)
                        os.remove(temp_name)
                        fname = file_id + '.jpg'
                    if file_type == 'sticker':
                        try:
                            img = Image.open(requests.get(download_url, stream=True).raw)
                            img.save('/tmp/' + file_id + '.png', 'png')
                        except OSError as exc:
                            self.retry(countdown=5)
                        fname = file_id + '.png'
                elif file_type in ['animation', 'video', 'video_note']:
                    # Download video
                    r = requests.get(download_url)
                    with open('/tmp/' + file_id + '.mp4', 'wb') as f:
                        f.write(r.content)

                    fname = file_id + '.mp4'
                elif file_type in ['audio']:
                    # Download audio
                    ext = file_path.split('.')[-1]
                    r = requests.get(download_url)
                    with open('/tmp/' + file_id + '.' + ext, 'wb') as f:
                        f.write(r.content)
                    fname = file_id + '.' + ext

                # Upload media file to AWS
                aws = AWS()
                aws_url = aws.upload(fname)

                # After uploading delete the file
                os.remove('/tmp/' + fname)

                media = Media(
                    file_id=file_id,
                    content_id=content_id,
                    url='',
                    aws_url=aws_url
                )
                media.save()

@shared_task(queue='media')
def check_pending_media():
    media = Media.objects.last()
    if media:
        start_id = media.content.id
        contents = Content.objects.filter(id__gte=start_id, post_to_spicefeed=True).order_by('-id')
        file_type = ''
        file_id = ''

        for content in contents:
            data = content.details

            if content.source == 'telegram':
                if 'photo' in data['message']['reply_to_message'].keys():
                    file_type = 'photo'
                    file_id = data['message']['reply_to_message']['photo'][-1]['file_id']

                elif 'sticker' in data['message']['reply_to_message'].keys():
                    file_type = 'sticker'
                    file_id = data['message']['reply_to_message']['sticker']['file_id']

                elif 'animation' in data['message']['reply_to_message'].keys():
                    file_type = 'animation'
                    file_id = data['message']['reply_to_message']['animation']['file_id']

                elif 'video' in data['message']['reply_to_message'].keys():
                    file_type = 'animation'
                    file_id = data['message']['reply_to_message']['video']['file_id']

                elif 'video_note' in data['message']['reply_to_message'].keys():
                    file_type = 'animation'
                    file_id = data['message']['reply_to_message']['video_note']['file_id']
                    # download_upload_file.delay(file_id, file_type, content.id)

                elif 'voice' in data['message']['reply_to_message'].keys():
                    file_type = 'audio'
                    file_id = data['message']['reply_to_message']['voice']['file_id']

                elif 'document' in data['message']['reply_to_message'].keys():
                    file_type = data['message']['reply_to_message']['document']['mime_type']
                    if 'image' in file_type:
                        file_type = 'photo'
                    file_id = data['message']['reply_to_message']['document']['file_id']
                download_upload_file.delay(file_id, file_type, content.id)

@shared_task(queue='withdrawal')
def check_pending_withdrawals():
    pending_withdrawals = Withdrawal.objects.filter(
        Q(date_started__isnull=True) &
        Q(date_completed__isnull=True) &
        Q(date_failed__isnull=True)
    )
    if pending_withdrawals.exists():
        withdrawal = pending_withdrawals.last()
        withdraw_spice_tokens(
            withdrawal.id,
            chat_id=withdrawal.user.telegram_id
        )


@shared_task(queue='faucet')
def process_faucet_request(faucet_disbursement_id):
    faucet_tx = FaucetDisbursement.objects.get(
        id=faucet_disbursement_id
    )
    response = {'status': False}
    if not faucet_tx.date_completed:
        if faucet_tx.amount > 0:
            no_error = True
            try:
                cmd = 'node /code/spiceslp/send-tokens.js faucet {0} {1} {2}'.format(
                    faucet_tx.slp_address,
                    faucet_tx.amount,
                    faucet_tx.token.token_id
                )
                p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
                stdout, _ = p.communicate()
                result = stdout.decode('utf8')
                logger.info(result)
                status = result.splitlines()[-1].strip()
                response = {'status': status}
            except Exception as exc:
                no_error = False
                msg = traceback.format_exc()
                error_prompt.delay(log=msg, **{'type': 'faucet'})
            if no_error:
                if status == 'success':
                    txid = result.splitlines()[-2].split('/tx/')[-1]
                    faucet_tx.transaction_id = txid
                    faucet_tx.date_completed = timezone.now()
                    faucet_tx.save()
                    response['txid'] = txid
                if status == 'failure':
                    response['error'] = 'There was an error in processing your request'
                    error_prompt.delay(log=response['error'], **{'type': 'faucet'})
        else:
            faucet_tx.date_completed = timezone.now()
            faucet_tx.save()
    return response


@shared_task(queue='mute_expiration')
def check_mute_expiration():
    logger.info('============ Checking Mute Status ============')
    mutes = Mute.objects.filter(
        is_muted=True
    )

    for mute in mutes:
        expired = mute.date_started <= (timezone.now() - timedelta(minutes=mute.duration))
        if expired:
            restrict_user(mute.id, True, False)

def restrictChatMember(chat_id, user_id, permissions): 
    data = { 
        "chat_id": chat_id,
        "user_id": user_id, 
        "permissions": permissions 
    } 
    url = 'https://api.telegram.org/bot' 
    response = requests.post( 
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/restrictChatMember", json=data 
    ) 
    rsp = None 
    if response.status_code == 200: 
        rsp = response.json() 
    return rsp 


def restrict_user(mute_id, allow_permission, is_clear, is_user_set=False):
    # user set param is for determining if unmute is for a user queryset or not
    # allow_permission param is False if user will be muted, True otherwise
    
    mute = Mute.objects.get(id=mute_id)
    chat_id = mute.group.chat_id
    telegram_id = mute.target_user.telegram_id

    permissions = {
        "can_send_messages": allow_permission, 
        "can_send_media_messages": allow_permission, 
        "can_send_polls": allow_permission, 
        "can_send_other_messages": allow_permission, 
        "can_add_web_page_previews": allow_permission, 
        "can_change_info": allow_permission, 
        "can_invite_users": allow_permission, 
        "can_pin_messages": allow_permission 
    }       

    restrictChatMember(chat_id, telegram_id, permissions)

    if allow_permission:
        mute.contributors.set(User.objects.none())
        mute.duration = mute.group.pillory_time
        mute.is_muted = False
        mute.save()

        if not is_user_set:
            unmuted_username = mute.target_user.telegram_username
            if is_clear:
                message = f"😁  <b>Greetings fam!</b>  😁\n\n{unmuted_username} has been cleared from the pillory list!"
            else:
                message = f"😁  <b>Greetings fam!</b>  😁\n\n{unmuted_username} has now been freed from silence!"

            if mute.is_being_unmuted:
                mm_does_not_exist = False
                try:
                    subscriber = Subscriber.objects.get(username=settings.MUTE_MANAGER_USERNAME)   
                    if subscriber.token == settings.MUTE_MANAGER_TOKEN and subscriber.app_name == 'telegram':                         
                        mutemanager = User.objects.filter(telegram_id=subscriber.details['user_collector_id'])
                        if mutemanager.exists():
                            mutemanager = mutemanager.first()
                            # if not is_clear:
                            #     mute.count -= 1
                            #     mute.save()

                            rain_amount = 0

                            if is_clear:
                                rain_amount = mute.get_fee() - mute.remaining_fee
                            else:
                                mutefee = mute.get_fee() / 0.99
                                unmutefee = round(mutefee + (mutefee * settings.UNMUTE_INTEREST))
                                rain_amount = unmutefee - mute.remaining_unmute_fee

                            # if not is_clear:
                            #     mute.count += 1
                            mute.is_being_unmuted = False
                            mute.remaining_unmute_fee = 0
                            mute.remaining_fee = 0
                            mute.save()

                            rain_text = f"rain 20 people {rain_amount} spice"
                            
                            from main.utils.telegram import TelegramBotHandler
                            bot = TelegramBotHandler()
                            rain_response = bot.rain(mutemanager.id, rain_text, mute.group.id, True)
                            if is_clear:
                                 response_prefix = " Since this had an unfinished pillory collection, "
                            else:
                                response_prefix = "Since this had an unfinished unmute collection, "

                            if rain_response == "Nobody received any spice":
                                response_prefix = ""
                            message += f"\n\n{response_prefix}{rain_response}"
                        else:
                            mm_does_not_exist = True
                    else:
                        mm_does_not_exist = True
                except Subscriber.DoesNotExist as exc:
                    mm_does_not_exist = True

                if mm_does_not_exist:
                    logger.error("\n\n========== Mute manager does not exist yet. ==========\n\n")

            send_telegram_message.delay(message, mute.group.chat_id, None)
    else:
        mute.contributors.set(User.objects.none())
        mute.is_muted = True
        mute.count = mute.count + 1
        mute.date_started = timezone.now()
        mute.save()


@shared_task(queue='metrics')
def record_metrics():
    logger.info("========= SAVING METRICS =========")
    metrics_handler = SpiceBotMetricHandler()
    user_metrics = metrics_handler.get_user_metrics()
    group_metrics = metrics_handler.get_group_metrics()
    withdrawal_metrics = metrics_handler.get_withdrawal_metrics()
    deposit_metrics = metrics_handler.get_deposit_metrics()
    tip_metrics = metrics_handler.get_tip_metrics()
    rain_metrics = metrics_handler.get_rain_metrics()
    game_metrics = metrics_handler.get_game_metrics()

    metric = Metric(
        user_metrics=user_metrics,
        group_metrics=group_metrics,
        withdrawal_metrics=withdrawal_metrics,
        deposit_metrics=deposit_metrics,
        tip_metrics=tip_metrics,
        rain_metrics=rain_metrics,
        game_metrics=game_metrics
    )
    metric.save()
    
    # get field names of each metric dictionary and format for display in slack message
    headers = list(metric._meta.get_fields())
    headers.remove(headers[0])
    headers.remove(headers[-1])

    date_recorded = metric.date_recorded.strftime('%B %d %Y (%T) - %A')
    text = f'*SPICE Metrics* \U0001f336\nDate Recorded: _{date_recorded}_\n'

    count = 0
    emojis = ['\U0001f465', '\U0001f4ac', '\U0001f4b5', '\U0001f4b0', '\U0001f44d', '\U00002602\ufe0f', '\U0001f3b2']

    while count < len(headers):
        header = headers[count].name
        index = headers[count].name
        header = header.replace('_', ' ').capitalize()
        header = header.replace(' metrics', '')
        header = f'{header}s'

        text += f'\n\n*{header}:*  {emojis[count]}\n>'

        sub_fields = []
        if index == 'user_metrics':
            sub_fields = list(metric.user_metrics.keys())
        elif index == 'group_metrics':
            sub_fields = list(metric.group_metrics.keys())
        elif index == 'withdrawal_metrics':
            sub_fields = list(metric.withdrawal_metrics.keys())
        elif index == 'deposit_metrics':
            sub_fields = list(metric.deposit_metrics.keys())
        elif index == 'tip_metrics':
            sub_fields = list(metric.tip_metrics.keys())
        elif index == 'rain_metrics':
            sub_fields = list(metric.rain_metrics.keys())
        elif index == 'game_metrics':
            sub_fields = list(metric.game_metrics.keys())

        for field in sub_fields:
            temp = field.replace('_', ' ').capitalize()
            temp = temp.replace('avg', 'average')
            temp = temp.replace('Avg', 'Average')
            value = ''

            if index == 'user_metrics':
                value = metric.user_metrics[field]
            elif index == 'group_metrics':
                value = metric.group_metrics[field]
            elif index == 'withdrawal_metrics':
                value = metric.withdrawal_metrics[field]
            elif index == 'deposit_metrics':
                value = metric.deposit_metrics[field]
            elif index == 'tip_metrics':
                value = metric.tip_metrics[field]
            elif index == 'rain_metrics':
                value = metric.rain_metrics[field]
            elif index == 'game_metrics':
                value = metric.game_metrics[field]


            if type(value) is int or type(value) is float:
                value = format(value, ',')
                text += f'• _{temp}_ = `{value}`\n>'

            elif type(value) is dict:
                dict_keys = list(value.keys())
                dict_text = ''
                for key in dict_keys:
                    if key == 'day':
                        formatted_key = 'Today'
                    else:
                        formatted_key = f'This {key}'

                    if temp == 'Top ten active groups':
                        ctr = 1
                        empty_suffix = formatted_key.lower()
                        dict_header = formatted_key
                        connector = 'are'

                        if key == 'day':
                            groups_list = value[key]
                        elif key == 'week' or key == 'month':
                            connector = 'were'
                            groups_list = value[key]['value']
                            if not value[key]['is_new']:
                                empty_suffix = f'last {key}'
                                dict_header = f'Last {key}'

                        dict_text += f'\t- *_{dict_header}_*\n>'
                                
                        if not groups_list:
                            dict_text += f"\t`There {connector} no active groups {empty_suffix}.`"
                        else:
                            for group in groups_list:
                                dict_text += f"\t*`{ctr}.`*  *`{group['title']}`*\n>"
                                dict_text += f"\t_Users_ = `{group['users_count']}`  *|*  _Spicebot Operations_ = `{group['spicebot_transactions']}`  *|*  _Date Created_ = `{group['date_created']}`"
                                dict_text += '\n>'
                                ctr += 1
                    else:
                        if type(value[key]) is dict:
                            if value[key]['is_new']:
                                dict_text += f"\t- *_{formatted_key}_* = `{value[key]['value']}`"
                            else:
                                dict_text += f"\t- *_Last {key}_* = `{value[key]['value']}`"
                        else:
                            dict_text += f"\t- *_{formatted_key}_* = `{value[key]}`"

                    if key != dict_keys[len(dict_keys) - 1]:
                        dict_text += '\n>'
                    else: 
                        dict_text += '\n>'

                text += f'• _{temp}_:\n>{dict_text}'

        count += 1

    text += metrics_handler.compute_token_system_balance()
    data = {
        'token': settings.SLACK_BOT_USER_TOKEN,
        'channel': settings.SLACK_METRIC_CHANNEL,
        'text': text,
    }

    post_slack_message(data)


def mark_withdrawal_as_success(withdrawal_id, txid):
    withdrawal = Withdrawal.objects.get(id=withdrawal_id)
    # Update withdrawal completion and txid
    withdrawal.date_completed = timezone.now()
    withdrawal.date_failed = None
    withdrawal.transaction_id = txid
    withdrawal.save()

    # Create the withdrawal transaction
    transaction_hash = f"{txid}-{withdrawal.user.id}-{withdrawal.slp_token.name}-{withdrawal.amount_with_fee}"
    created, w_hash_1 = create_transaction(
        withdrawal.user.id,
        withdrawal.amount_with_fee,
        'Outgoing',
        withdrawal.slp_token.id,
        settings.TXN_OPERATION['WITHDRAW'],
        transaction_hash=transaction_hash
    )

    # add fee to Tax Collector user
    transaction_hash = f"{txid}-{settings.TAX_COLLECTOR_USER_ID}-{withdrawal.slp_token.name}-{withdrawal.fee}"
    created, w_hash_2 = create_transaction(
        settings.TAX_COLLECTOR_USER_ID,
        withdrawal.fee,
        'Incoming',
        withdrawal.slp_token.id,
        settings.TXN_OPERATION['WITHDRAW'],
        transaction_hash=transaction_hash
    )

    swap_related_transactions(w_hash_1, w_hash_2)
