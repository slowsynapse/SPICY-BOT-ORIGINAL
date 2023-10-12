from django.conf import settings
from django.utils import timezone
from main.utils.responses import get_response
from main.models import User, Content, Transaction, Withdrawal, Response
from celery import current_app
from main.utils.miscellaneous_pattern import Misc_Pattern
from main.utils.account import create_transaction, get_balance
from django.db.models import Sum
import emoji
import twitter
import logging
import time
import redis
import json
import random
import re


logger = logging.getLogger(__name__)

class TwitterBot(object):

    def __init__(self):
        self.authenticate()
        self.amt_with_commas_regex = '(((\d*[.]\d+)|(\d+))|((\d{1,3})(\,\d{3})+(\.\d+)?))'


    def authenticate(self):
        self.api = twitter.Api(
            consumer_key=settings.TWITTER_CONSUMER_KEY,
            consumer_secret=settings.TWITTER_CONSUMER_SECRET,
            access_token_key=settings.TWITTER_ACCESS_KEY,
            access_token_secret=settings.TWITTER_ACCESS_SECRET
        )

        if settings.DEPLOYMENT_INSTANCE == 'staging' or settings.DEPLOYMENT_INSTANCE == 'dev':
            self.withdrawal_api = self.api
        else:
            self.withdrawal_api = twitter.Api(
                consumer_key=settings.TWITTER_WITHDRAWAL_CONSUMER_KEY,
                consumer_secret=settings.TWITTER_WITHDRAWAL_CONSUMER_SECRET,
                access_token_key=settings.TWITTER_WITHDRAWAL_ACCESS_KEY,
                access_token_secret=settings.TWITTER_WITHDRAWAL_ACCESS_SECRET
            )


    def compute_POF(self, user_id, text):
        user = User.objects.get(id=user_id)
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

        return round(pof_percentage), round(pof_rating)

    def handle_tipping(self, amount, sender_id, recipient_id, data):
        sender = User.objects.get(id=sender_id)
        recipient = User.objects.get(id=recipient_id)
        success = False
        content_check = Content.objects.filter(source='twitter',details__reply__id=data['id'])

        proceed = False
        if not content_check.count():
            one_satoshi = 0.00000001
            if amount >= one_satoshi:
                balance = get_balance(sender.id, settings.SPICE_TOKEN_ID)
                if balance >= amount:
                    proceed = True
                else:
                    try:
                        self.send_direct_message(
                            sender.twitter_id,
                            'Hi! You tried to tip but your SPICE balance is insufficient.',
                            data['id']
                        )
                        success = True
                    except twitter.error.TwitterError as exc:
                        logger.error(repr(exc))

        if proceed:
            parent = None
            recipient_content_id = None
            content_id_json = None

            original_status = self.api.GetStatus(data['in_reply_to_status_id'], trim_user=True)
            content_details = {
                'reply': data,
                'replied_to': original_status.AsDict()
            }
            # Getting parent tipper
            recipient_content_id = {
                'status_id': content_details['reply']['in_reply_to_status_id']
            }

            content_id_json = json.dumps(recipient_content_id)

            if Content.objects.filter(recipient_content_id=content_id_json).exists():
                parent = Content.objects.get(parent=None, recipient_content_id=content_id_json)

            # Save content to database
            content = Content(
                source='twitter',
                sender_id=sender.id,
                recipient=recipient,
                tip_amount=amount,
                details=content_details,
                post_to_spicefeed=sender.post_to_spicefeed,
                parent=parent,
                recipient_content_id=content_id_json
            )
            content.save()

            # Sender outgoing transaction
            create_transaction(sender.id, amount, 'Outgoing', settings.SPICE_TOKEN_ID)

            # Recipient incoming transaction
            create_transaction(recipient.id, amount, 'Incoming', settings.SPICE_TOKEN_ID)

            if amount > 1:
                amount = '{:,}'.format(round(amount, 8))
            else:
                amount = '{:,.8f}'.format(round(amount, 8))
            amount_str = str(amount)
            if amount_str.endswith('.0'):
                amount_str = amount_str[:-2]
            if '.' in amount_str:
                amount_str = amount_str.rstrip('0')
            if amount_str.endswith('.'):
                amount_str = amount_str[:-1]

            # Post update about the tipping
            args = (amount_str, recipient.twitter_screen_name)
            status = 'I have transferred your tip of %s \U0001f336 SPICE \U0001f336 to %s' % args
            # status += '\n\nMessage me for usage instructions: https://twitter.com/messages/compose?recipient_id='
            status += '\n\nhttps://twitter.com/spicetokens/status/1162246727136497664'
            # status += f'\n\n<a href="https://spice.network/details/{content.id}">view tip on SpiceFeed</a>'
            env = settings.DEPLOYMENT_INSTANCE.strip(' ').lower()
            if env == 'prod':
                status += f'\n\nView Tip on SpiceFeed here:\nhttps://spice.network/details/{content.id}'
            elif env == 'staging':
                status += f'\n\nView Tip on SpiceFeed here:\nhttps://spicefeed-staging.scibizinformatics.com/details/{content.id}'
            else:
                status += f'\n\nView Tip on SpiceFeed here:\nhttps://spicefeed-dev.scibizinformatics.com/details/{content.id}'
            # pof_receiver = self.compute_POF(recipient.id, data['text'])
            # pof_sender = self.compute_POF(sender.id, data['text'])
            body = {
                'response': status,
                'in_reply_to_status_id': int(data['id']),
                'auto_populate_reply_metadata': True
            }
            if not Response.objects.filter(body=body).exists():
                try:
                    self.api.PostUpdate(
                        body['response'],
                        in_reply_to_status_id=body['in_reply_to_status_id'],
                        auto_populate_reply_metadata=body['auto_populate_reply_metadata']
                    )
                    success = True
                except twitter.error.TwitterError as exc:
                    logger.error(repr(exc))
                
                response = Response(
                    response_type='post',
                    content=content,
                    body=body,
                    botReplied=success
                )
                response.save()

        return success

    def check_failed_reply(self):
        responses = Response.objects.filter(response_type='post')
        responses = responses.filter(botReplied=False)
        for response in responses:
            body = response.body
            if body['response']:
                try:
                    self.withdrawal_api.PostUpdate(
                        body['response'],
                        in_reply_to_status_id=body['in_reply_to_status_id'],
                        auto_populate_reply_metadata=body['auto_populate_reply_metadata']
                    )
                    response.botReplied = True
                    response.save()
                except twitter.error.TwitterError as exc:
                    logger.error(repr(exc))

    def process_mentions(self, last_id=None):
        # Fetch the mentions
        mentions = self.api.GetMentions(
            count=200,
            trim_user=True
        )

        mention_ids = [x.id for x in mentions]

        old_mentions = []
        content_check = Content.objects.filter(
            source='twitter',
            details__reply__id__in=mention_ids
        )
        if content_check.count():
            old_mentions = content_check.values_list('details__reply__id', flat=True)
        fresh_mentions = [x for x in mentions if x.id not in old_mentions]
        
        response_check = Response.objects.filter(body__message_id__in=mention_ids)
        if response_check.count():
            old_mentions = response_check.values_list('body__message_id', flat=True)
            fresh_mentions = [x for x in fresh_mentions if x.id not in old_mentions] 
        for mention in fresh_mentions:
            data = mention.AsDict()
            proceed = True
            if 'in_reply_to_screen_name' in data.keys():
                # if data['in_reply_to_screen_name'] == settings.TWITTER_BOT_NAME:
                #     proceed = False
                if data['user']['id'] == data['in_reply_to_user_id']:
                    proceed = False

            if 'in_reply_to_status_id' in data.keys() and proceed:
                botname = f'@{settings.TWITTER_BOT_NAME}'
                proceed = False
                try:
                    tipped_status = self.api.GetStatus(data['in_reply_to_status_id'], trim_user=True)
                    proceed = True
                except twitter.error.TwitterError as exc:
                    logger.error(repr(exc))
                if proceed:
                    # ts_mentions = tipped_status.AsDict()['user_mentions']
                    tipped_status_text = tipped_status.text
                    ts_botname_count = tipped_status_text.count(botname)
                    message_text = ''
                    if ts_botname_count != 0:
                        message_text = data['text'].replace(botname, '', 1)
                    else:
                        message_text = data['text']

                    # pattern_calc = Pattern()
                    # tip_amount = pattern_calc.tip_getter(**{
                    #     'type': 'by_mention',
                    #     'text': message_text,
                    #     'action': 'tip',
                    #     'env': settings.DEPLOYMENT_INSTANCE
                    # })                    

                    # This is just temporary | Dec 5, 2020
                    tip_amount = 0

                    #lightning                    
                    if tip_amount == 0:
                        message_text= pattern_calc.remove_twitter_handles(message_text).strip(' ')

                        msc_pattern = Misc_Pattern()
                        message = msc_pattern.check_lightning(message_text)
                        #self.send_direct_message(data['user']['id_str'], message, data['id'] )
                        #send message
                        success = False
                        if message:
                            body = {
                                'response': message,
                                'in_reply_to_status_id': int(data['id']),
                                'auto_populate_reply_metadata': True
                            }
                            if not Response.objects.filter(body=body).exists():
                                try:
                                    self.api.PostUpdate(
                                        body['response'],
                                        in_reply_to_status_id=body['in_reply_to_status_id'],
                                        auto_populate_reply_metadata=body['auto_populate_reply_metadata']
                                    )
                                    success = True
                                except twitter.error.TwitterError as exc:
                                    logger.error(repr(exc))
                                    
                                response = Response(
                                    response_type='post',
                                    content=None,
                                    body=body,
                                    botReplied=success
                                )
                                response.save()

                    if tip_amount > 0:
                        # Identify and save the sender
                        sender, _ = User.objects.get_or_create(twitter_id=data['user']['id_str'])
                        if not sender.twitter_user_details:
                            sender_details = self.api.GetUser(data['user']['id'])
                            sender_details = sender_details.AsDict()
                            del sender_details['status']
                            sender.twitter_user_details = sender_details

                        sender.last_activity = timezone.now()
                        sender.save()
                        # Identify and save the recipient
                        recipient, _ = User.objects.get_or_create(twitter_id=data['in_reply_to_user_id'])
                        if not recipient.twitter_user_details:
                            recipient_details = self.api.GetUser(data['in_reply_to_user_id'])
                            recipient_details = recipient_details.AsDict()
                            del recipient_details['status']
                            recipient.twitter_user_details = recipient_details
                            recipient.save()
                        # Call the function that handles the tipping
                        tipping_succeeded = self.handle_tipping(tip_amount, sender.id, recipient.id, data)
                        if not tipping_succeeded:
                            break

    def send_direct_message(self, user_id, message, message_id=None):
        proceed = False
        if message_id:
            if not settings.REDISKV.sismember('twitter_msgs', message_id):
                proceed = True
        else:
            proceed = True
        if proceed:
            body = {
                'user_id': user_id,
                'return_json':True,
                'message_id': message_id,
                'message': message
            }
            send_success = False
            time.sleep(3)  # Delay the sending by a few seconds
            try:
                self.withdrawal_api.PostDirectMessage(
                    text=message,
                    user_id=body['user_id'],
                    return_json=body['return_json']
                )
                send_success = True
            except twitter.error.TwitterError as exc:
                logger.error(repr(exc))

            if send_success and message_id:
                settings.REDISKV.sadd('twitter_msgs', message_id)
                if settings.REDISKV.scard('twitter_msgs') >= 10000:
                    settings.REDISKV.spop('twitter_msgs')

            response, _ = Response.objects.get_or_create(
                response_type='direct_message',
                body=body,
            )
            response.botReplied = send_success
            response.save()

    def transfer_spice(self, text, body):
        from main.tasks import transfer_spice_to_another_acct

        sender = User.objects.get(twitter_id=body['user_id'])
        if not Response.objects.filter(body__message_id=body['message_id']).exists():
            text = re.sub('\s+', ' ', text)
            words = text.split(' ')

            recipient_source = words[0]
            recipient_username = words[1].replace('@', '')
            transfer_amount = float(words[2].replace(',', ''))

            recipient = None
            if recipient_source == 'telegram':
                recipient = User.objects.filter(telegram_user_details__username=recipient_username)
            elif recipient_source == 'reddit':
                recipient = User.objects.filter(reddit_user_details__username=recipient_username)

            if recipient.exists():
                recipient = recipient.first()
                message = transfer_spice_to_another_acct(sender.id, recipient.id, transfer_amount)
            else:
                message = 'Oops! The account you want to transfer to does not exist! Try another username.'
            return message

    def process_direct_messages(self, last_id=None):
        success_request = False
        try:
            messages = self.withdrawal_api.GetDirectMessages(count=200, return_json=True)
            success_request = True
        except twitter.error.TwitterError as exc:
            logger.error(repr(exc))
        if success_request:
            if settings.TWITTER_WITHDRAWAL_ACCESS_KEY:
                for message in messages['events']:
                    twitter_bot_id = settings.TWITTER_WITHDRAWAL_ACCESS_KEY.split('-')[0]
                        
                    sender_id = message['message_create']['sender_id']
                    if sender_id != twitter_bot_id:
                        if not settings.REDISKV.sismember('twitter_msgs', message['id']):
                            text = message['message_create']['message_data']['text']
                            transfer_text = text.lstrip('/').strip()
                            text = text.lower().lstrip('/').strip()
                            user_id = message['message_create']['sender_id']
                            user, created = User.objects.get_or_create(twitter_id=user_id)
                            if not user.twitter_user_details:
                                user_details = self.withdrawal_api.GetUser(user_id)
                                user_details = user_details.AsDict()
                                try:
                                    del user_details['status']
                                except KeyError:
                                    pass
                                user.twitter_user_details = user_details
                                user.save()

                            if user.twitter_screen_name == settings.TWITTER_BOT_NAME:
                                user = None
                            user.last_activity = timezone.now()
                            user.save()
                            qs_user = User.objects.filter(id=user.id)

                            # response = None
                            # if text == 'deposit':
                            #     if user:
                            #         response = 'Send deposit to this address:\n\n%s' % (user.simple_ledger_address)
                            # else:
                            response = get_response(text)

                            # show_generic_response = True
                            if response:
                                self.send_direct_message(user_id, response, message['id'])
                                # show_generic_response = False
                            else:
                            #     if text == 'anonymousname' and user:
                            #         response = 'Hi! Your anonymous username is %s' % user.anon_name
                            #         self.send_direct_message(user_id, response, message['id'])

                            #     elif text == 'spicefeednameon' and user:
                            #         qs_user.update(display_username=True)
                            #         response = 'Ok spicefeed will show your actual username.. privacy rekt'
                            #         self.send_direct_message(user_id, response, message['id'])

                            #     elif text == 'spicefeednameoff' and user:
                            #         qs_user.update(display_username=False)
                            #         response = 'Ok spicefeed will now hide your username and replace it with one we have "very" carefully made up for you..'
                            #         self.send_direct_message(user_id, response, message['id'])

                                if text == 'balance' and user:
                                    amount = int(get_balance(user.id, settings.SPICE_TOKEN_ID))
                                    # amount = '{:,}'.format(round(amount, 8))
                                    amount_str = str(amount)
                                    # if amount_str.endswith('.0'):
                                    #     amount_str = amount_str[:-2]
                                    # if 'e' in amount_str:
                                    #     amount_str = "{:,.8f}".format(float(amount_str))
                                    response = 'You have %s \U0001f336 SPICE \U0001f336!' % amount_str
                                    self.send_direct_message(user_id, response, message['id'])
                                    show_generic_response = False
                                    # Update last activity
                                    user.last_activity = timezone.now()
                                    user.save()

                            #     if text == 'telegram' and user:
                            #         response = get_response('telegram')
                            #         self.send_direct_message(user_id, response, message['id'])

                            #     if text == 'reddit' and user:
                            #         response = get_response('reddit')
                            #         self.send_direct_message(user_id, response, message['id'])

                            #     body = {
                            #         'user_id': user_id,
                            #         'return_json':True,
                            #         'message_id': message['id']
                            #     }

                            #     if not Response.objects.filter(body__message_id=message['id']).exists():
                            #         if text.startswith('telegram ') and user:
                            #             if re.match(f'^telegram\s+@[\w_]+\s+{self.amt_with_commas_regex}$', text):
                            #                 response = self.transfer_spice(transfer_text, body)
                            #                 logger.info('response: %s', response)
                            #             else:
                            #                 response = get_response('telegram')
                            #             self.send_direct_message(user_id, response, message['id'])
                            #             show_generic_response = False

                            #         if text.startswith('reddit ') and user:
                            #             if re.match(f'^reddit\s+[\w_]+\s+{self.amt_with_commas_regex}$', text):
                            #                 response = self.transfer_spice(transfer_text, body)
                            #                 logger.info('response: %s', response)
                            #             else:
                            #                 response = get_response('reddit')
                            #             self.send_direct_message(user_id, response, message['id'])
                            #             show_generic_response = False

                                if re.findall('^/?withdraw\s+all\s.*$', text) and user:
                                    temp = int(get_balance(user.id, settings.SPICE_TOKEN_ID))
                                    if temp > 0:
                                        amount = temp
                                        addr = None
                                        withdraw_error = ''
                                        response = None
                                        try:
                                            # amount_temp = text.split()[1]
                                            amount_temp = str(amount)
                                            try:
                                                if not re.match(f'^{self.amt_with_commas_regex}$', amount_temp):
                                                    raise ValueError('')
                                                # amount = float(amount_temp.replace(',', '').strip())
                                            except ValueError:
                                                response = "You have entered an invalid amount!"
                                            addr_temp = text.split()[2].strip()
                                            if  addr_temp.startswith('simpleledger') and len(addr_temp) == 55:
                                                addr = addr_temp.strip()
                                                response = "You have entered an invalid SLP address!"
                                        except IndexError:
                                            response = "You have not entered a valid amount or SLP address!"

                                        if addr and amount:
                                            # balance = int(user.balance)
                                            # if amount <= balance:
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
                                                time_now = timezone.now()
                                                tdiff = time_now - last_withdraw_time
                                                withdraw_time_limit = tdiff.total_seconds()
                                                if withdraw_time_limit < 3600:
                                                    withdraw_limit = True
                                                    response = 'You have reached your hourly withdrawal limit!'

                                            if not withdraw_limit:
                                                if amount >= settings.TWITTER_WITHDRAWAL_LIMIT:
                                                    withdrawal = Withdrawal(
                                                        user=user,
                                                        address=addr,
                                                        amount=amount
                                                    )
                                                    withdrawal.save()
                                                    current_app.send_task(
                                                        'main.tasks.withdraw_spice_tokens',
                                                        args=(withdrawal.id,),
                                                        kwargs={
                                                            'user_id': user_id,
                                                            'bot': 'twitter'
                                                        },
                                                        queue='twitter'
                                                    )
                                                    response = f'Your \U0001f336 {amount} SPICE \U0001f336 withdrawal request is being processed.'
                                                else:
                                                    # response = "Only 1000 \U0001f336 and above is allowed to withdraw."
                                                    response = f"We can’t process your withdrawal request because it is below minimum. The minimum amount allowed is {settings.TWITTER_WITHDRAWAL_LIMIT} \U0001f336 SPICE."
                                            # else:
                                            #     response = "You don't have enough \U0001f336 SPICE \U0001f336 to withdraw!"

                                        if not addr or not amount:
                                            response = """
                                            Withdrawal can be done by running the following command:
                                            \n/withdraw all "simpleledger_address"
                                            \n\nExample:
                                            \n/withdraw all simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
                                            """
                                        if response:
                                            self.send_direct_message(user_id, response, message['id'])
                                            show_generic_response = False
                                    else:
                                        response = "You don't have enough \U0001f336 SPICE \U0001f336 to withdraw!"

                            # if show_generic_response:
                            #     # Send the message
                            #     response = """ To learn more about SpiceBot, please visit:
                            #     \nhttps://spicetoken.org/bot_faq/
                            #     \nIf you need further assistance, please contact @spicedevs"""
                            #     self.send_direct_message(user_id, response, message['id'])
