from django.conf import settings
from django.utils import timezone
from main.utils.responses import get_response, get_maintenance_response
from main.models import User, Content, Transaction, Withdrawal, Response, SLPToken
from celery import current_app
from praw.models import Message
from main.utils.miscellaneous_pattern import Misc_Pattern
from main.utils.account import create_transaction, get_balance
from constance import config

from django.db.models import Sum
import emoji
import praw
import logging
import time
import redis
import json
import random
import re

logger = logging.getLogger(__name__)

class RedditBot(object):

    def __init__(self):
        self.text = ''
        self.body = None
        if settings.DEPLOYMENT_INSTANCE == 'prod':
            self.subreddit_name = 'spice'
            self.keyphrase = '@spicetokens'
        else:
            self.subreddit_name = 'testingground4bots'
            self.keyphrase = '@chillbotskysta1'
        self.authenticate()
        self.amt_with_commas_regex = '(((\d*[.]\d+)|(\d+))|((\d{1,3})(\,\d{3})+(\.\d+)?))'


    def authenticate(self):
        self.reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            username=settings.REDDIT_USERNAME,
            password=settings.REDDIT_PASSWORD,
            user_agent=settings.REDDIT_USER_AGENT
        )


    # def get_tip_amount(self, text):
    #     results = re.findall(r'[+-]? *(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text)
    #     tip_value = sum([ float(r) for r in results])
    #     for char in allowed_symbols:
    #         multiplier = text.count(char)
    #         if char == '\U0001F344':
    #             value = random.choice(range(0,1000))
    #         else:
    #             value = allowed_symbols[char]
    #         tip_value += (value * multiplier)
    #     return tip_value


    def is_valid_tip_pattern(self, text):
        if self.keyphrase in text:
            substrings = text.split(' ')
            for substring in substrings:
                if substring == '':
                    continue
                if not substring.startswith('@') and not substring[0] in emoji.UNICODE_EMOJI:
                    return False
                return True
        return False

    def get_tip_amount(self, text):
        tip_value = 0
        if self.is_valid_tip_pattern(text):
            results = re.findall(r'\@\w+',text)
            for r in results: text = text.replace(r, '')
            text = text.lstrip('')
            for char in settings.ALLOWED_SYMBOLS.keys():
                multiplier = text.count(char)
                if char == '\U0001F344':
                    value = random.choice(range(0,1000))
                    text = text.replace(char,"")
                else:
                    value = settings.ALLOWED_SYMBOLS[char]
                    if value:
                        text = text.replace(char,"")
                tip_value += (value * multiplier)
            text = text.lstrip('')

        # if text.startswith('tip'):
        #     results = re.findall(r'[+-]? *(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text)
        #     tip_value += sum([ float(r) for r in results])
        if tip_value == 0:
            if not self.has_emoji(text):
                results = re.findall(r'[+-]? *(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text)
                try:
                    tip_value = float(results[-1])
                except IndexError:
                    pass
        return tip_value

    def has_emoji(self, text):
        for char in text:
            if char in emoji.UNICODE_EMOJI or char == "+":
               return True
        return False

    def compute_POF(self, user, text):
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

    def handle_tipping(self, amount, sender, recipient, comment):
        success = False
        content_check = Content.objects.filter(
            source='reddit',
            details__comment_details__comment_id=comment['comment_id']
        )

        proceed = False
        body = {
            'comment': comment['comment_body'],
            'sender': comment['author'],
            'comment_id': comment['comment_id']
        }
        if not content_check.count():
            one_satoshi = 0.00000001
            if amount >= one_satoshi:
                balance = get_balance(sender.id, settings.SPICE_TOKEN_ID)
                if balance >= amount:
                    proceed = True
                else:
                    if not Response.objects.filter(body=body).exists():
                        response = 'Hi! You tried to tip but your SPICE balance is insufficient.'
                        msg_subject = 'Tipping Alert'
                        resp = Response(
                            response_type='direct_message',
                            body=body
                        )
                        resp.save()
                        self.send_message(response, msg_subject, body['sender'], resp.id)

        if self.is_feat_disabled('tipping'):
            msg_subject = 'Tipping Alert'
            response = get_maintenance_response('tipping')
            proceed = False
            resp = Response(
                    response_type='direct_message',
                    body=body
                )
            resp.save()
            self.send_message(response, msg_subject, body['sender'], resp.id)


        if proceed:
            parent = None
            is_comment = False
            #Get parent tipper
            if '_' in comment['link_id']:
                submission = self.reddit.submission(id=comment['link_id'][3:])
            else:
                submission = self.reddit.comment(id=comment['link_id'])
                is_comment = True

            recipient_content_id = {
               'submission_id': comment['link_id'][3:]
            }
            if Content.objects.filter(recipient_content_id=recipient_content_id).exists():
                parent = Content.objects.get(parent=None, recipient_content_id=recipient_content_id)

            # logger.info('submission_details: %s\n\n', submission)
            # logger.info('media_url: %s \n\n', submission.url)
            # if not is_comment:
            #     media_url = submission.url
            #     self.text = submission.selftext
            # else:
            #     media_url = ''
            #     self.text = submission.body

            #file_ext = '(.png|.jpg|.mp4|.mp3|.gif)'
            #pattern = f'(https?:\/\/[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.{file_ext}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.{file_ext})'
            pattern = 'https:\/\/(.*?)(.png|.jpg|.mp4|.mp3|.gif|.mkv)$'

            if not is_comment:
                self.text = submission.selftext
                m = re.match(pattern, submission.url)
                if m:
                    media_url = submission.url
                else:
                    media_url = ''
            else:
                media_url = ''
                self.text = submission.body
            logger.info('text: %s\n\n', self.text)

            if not media_url:
                msg = self.text.replace('(', ' ').replace(')', ' ').replace('\n', ' ')
                msg = msg.replace('[', ' ').replace(']', ' ')
                # text_ls = list(filter(None, self.text.split(' ')))
                # for t in text_ls:
                #     if re.match(pattern, t):
                #         media_url = t
                #         break

                #logger.info('pattern: %s, text: %s\n\n', pattern,msg)
                m = re.search(pattern, msg)

                if m:
                    media_url = m.group()
                    logger.info('here: %s', m.group())
                else:
                    media_url = 'https://storage.googleapis.com/spice-slp-media/redditpost.jpg'


            logger.info('media_url: %s\n\n', media_url)

            try:
                submission_details = {
                    'date_created': submission.created_utc,
                    'subreddit': submission.subreddit.display_name,
                    'permalink': submission.permalink,
                    'text': self.text,
                    'id': submission.id,
                    'media_url': media_url
                }
            except praw.exceptions.APIException as exc:
                submission_details = None
            detail = {
                'comment_details': comment,
                'submission_details': submission_details
            }
            #Save to DB
            content = Content(
                source='reddit',
                tip_amount=amount,
                sender=sender,
                recipient=recipient,
                details=detail,
                post_to_spicefeed=sender.post_to_spicefeed,
                recipient_content_id=recipient_content_id,
                parent=parent
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

            #Post comment about tipping
            pof_receiver = self.compute_POF(recipient, self.text)
            pof_sender = self.compute_POF(sender,self.text)
            args = (amount, comment['link_author'])
            status = 'Hi! I have transferred your tip of %s \U0001f336 SPICE \U0001f336 to %s' % args
            status += '\n\n[How to use Spice](https://spicetoken.org/bot_faq/)'
            status += ' | [What is Spice](https://spicetoken.org/)'
            status += ' | [r/Spice](https://np.reddit.com/r/spice/)'
            # status += f'\n\nhttps://spice.network/details/{content.id}'
            env = settings.DEPLOYMENT_INSTANCE.strip(' ').lower()
            if env == 'prod':
                status += f'\n\nhttps://spice.network/details/{content.id}'
            elif env == 'staging':
                status += f'\n\nhttps://spicefeed-staging.scibizinformatics.com/details/{content.id}'
            else:
                status += f'\n\nhttps://spicefeed-dev.scibizinformatics.com/details/{content.id}'

            reply_body = {
                'response': status,
                'comment_id': comment['comment_id']
            }
            resp = Response(response_type='reddit_comment', body=reply_body)
            resp.save()
            try:
                comment_reply = self.reddit.comment(id=comment['comment_id'])
                comment_reply.reply(status)
                comment.update(replied=True)
                success = True
                resp.botReplied = True
                resp.save()
            except praw.exceptions.APIException as exc:
                logger.error(repr(exc))

        return success

    def check_failed_reply(self):
        responses = Response.objects.filter(response_type='reddit_comment')
        responses = responses.filter(botReplied=False)
        for response in responses:
            reply_body = response.body
            try:
                comment_reply = self.reddit.comment(id=reply_body['comment_id'])
                comment_reply.reply(reply_body['response'])
                response.botReplied = True
                response.save()
            except praw.exceptions.APIException as exc:
                logger.error(repr(exc))


    def process_subreddit_mentions(self, subreddit_name):
        subreddit = self.reddit.subreddit(subreddit_name)
        logger.info('The Active subreddit is: %s', subreddit)
        # phrase to activate the bot
        # Get the comment data with bot mentions
        data = []
        for comment in subreddit.comments():

            if self.keyphrase in comment.body and comment.link_author != '[deleted]' and comment.link_author is not None:

                parent = comment.parent()
                link_id = comment.link_id[3:]

                if link_id == parent.id:
                    link_author = comment.link_author
                    link_author_id = self.reddit.redditor(comment.link_author).id
                    link_id = comment.link_id

                else:
                    if parent.author: link_author = parent.author.name
                    if link_author is not '': link_author_id = self.reddit.redditor(link_author).id
                    link_id = parent.id

                data_items = {
                    'author': comment.author.name,
                    'author_id': comment.author.id,
                    'link_author': link_author,
                    'link_author_id': link_author_id,
                    'link_id': link_id,
                    'date_created': comment.created_utc,
                    'comment_id': comment.id,
                    'comment_body': comment.body,
                    'replied': False
                }
                data.append(data_items)

        for comment in data:

            proceed = True
            if comment['author'] == comment['link_author']:
                proceed = False
            if comment['link_author'] == settings.REDDIT_USERNAME:
                proceed = False
            if not comment['replied'] and proceed:
                comment_text = comment['comment_body']
                # Get tip amount
                # tip_amount = self.get_tip_amount(comment_text)
                env = settings.DEPLOYMENT_INSTANCE.strip(' ').lower()
                # pattern_calc = Pattern()
                # tip_amount = pattern_calc.tip_getter(**{
                #     'type': 'by_mention',
                #     'text': comment_text,
                #     'action': 'tip',
                #     'env': env
                # })

                # This is just temporary
                tip_amount = 0

                if tip_amount == 0:
                    msc_pattern = Misc_Pattern()
                    message = msc_pattern.check_lightning(comment_text)

                    reply_body = {
                        'response': message,
                        'comment_id': comment['comment_id']
                    }
                    resp = Response(response_type='reddit_comment', body=reply_body)
                    resp.save()
                    try:
                        comment_reply = self.reddit.comment(id=comment['comment_id'])
                        comment_reply.reply(message)
                        comment.update(replied=True)
                        success = True
                        resp.botReplied = True
                        resp.save()
                    except praw.exceptions.APIException as exc:
                        logger.error(repr(exc))

                if tip_amount > 0:
                    # Identify and save the sender
                    user_detail = {
                        'user_id': comment['author_id'],
                        'username': comment['author']
                    }
                    sender, _ = User.objects.get_or_create(
                        reddit_id=comment['author_id'],
                    )
                    if not sender.reddit_user_details:
                        sender.reddit_user_details=user_detail
                    sender.last_activity = timezone.now()
                    sender.save()

                    # Identify and save the recipient
                    user_detail = {
                        'user_id': comment['link_author_id'],
                        'username': comment['link_author']
                    }
                    recipient, _ = User.objects.get_or_create(
                        reddit_id=comment['link_author_id'],
                    )
                    if not recipient.reddit_user_details:
                        recipient.reddit_user_details=user_detail
                    recipient.save()

                    self.handle_tipping(tip_amount, sender, recipient, comment)

    # def process_mentions(self, last_id=None):
    #     # the subreddits you want your bot to live on
    #     subreddits = [self.subreddit_name]
    #     if settings.DEPLOYMENT_INSTANCE == 'prod':
    #         subreddits += ['btc', 'bitcoincash','hotsauce', 'HotPeppers']

    #     for subreddit in subreddits:
    #         self.process_subreddit_mentions(subreddit)

    def get_unread_messages(self):
        unread_messages = []
        for item in self.reddit.inbox.unread(limit=None):
            if isinstance(item, Message):
                unread_messages.append(item)
        return unread_messages

    def transfer_spice(self, text, sender_id):
        from main.tasks import transfer_spice_to_another_acct

        text = re.sub('\s+', ' ', text)
        words = text.split(' ')

        recipient_source = words[0]
        recipient_username = words[1].replace('@', '')
        transfer_amount = float(words[2].replace(',', ''))

        recipient = None
        if recipient_source == 'twitter':
            recipient = User.objects.filter(twitter_user_details__screen_name=recipient_username)
        elif recipient_source == 'telegram':
            recipient = User.objects.filter(telegram_user_details__username=recipient_username)

        if recipient.exists():
            recipient = recipient.first()
            message = transfer_spice_to_another_acct(sender_id, recipient.id, transfer_amount)
        else:
            message = 'Oops! The account you want to transfer to does not exist! Try another username.'

        return message

    def process_messages(self):
        for message in self.get_unread_messages():
            if message.author:
                user, created = User.objects.get_or_create(reddit_id=message.author.id)
                user.last_activity = timezone.now()
                user.save()
                if not user.reddit_user_details:
                    user_detail = {
                        'user_id': message.author.id,
                        'username': message.author.name
                    }
                    user.reddit_user_details = user_detail
                    user.save()

                qs_user = User.objects.filter(id=user.id)

                recipient = message.author.name
                show_generic_response = True
                transfer_text = str(message.body).strip()
                self.text = str(message.body).strip().lower()
                response = None
                msg_subject = ''

                body = {
                    'message': self.text,
                    'subject': message.subject,
                    'sender': recipient,
                    'message_id': message.id
                }
                if not Response.objects.filter(body=body).exists():
                    if self.text.startswith('anonymousname'):
                        msg_subject = 'Spicefeed Anonymous Name'
                        response = 'Hi! Your anonymous username is %s' % user.anon_name
                        show_generic_response = False

                    if self.text.startswith('spicefeednameon'):
                        msg_subject = 'Spicefeed Name'
                        qs_user.update(display_username=True)
                        response = 'Ok spicefeed will show your actual username.. privacy rekt'
                        show_generic_response = False

                    if self.text.startswith('spicefeednameoff'):
                        msg_subject = 'Spicefeed Name'
                        qs_user.update(display_username=False)
                        response = 'Ok spicefeed will now hide your username and replace it with one we have "very" carefully made up for you..'
                        show_generic_response = False

                    if self.text.startswith('balance'):
                        msg_subject = 'Balance Inquiry'


                        amount = get_balance(user.id, settings.SPICE_TOKEN_ID)
                        amount = '{:,}'.format(round(amount, 8))
                        amount_str = str(amount)
                        if amount_str.endswith('.0'):
                            amount_str = amount_str[:-2]
                        if 'e' in amount_str:
                            amount_str = "{:,.8f}".format(float(amount_str))
                        response = 'You have %s \U0001f336 SPICE \U0001f336!' % amount_str
                        show_generic_response = False

                    if self.text.startswith('twitter '):
                        msg_subject = 'SPICE Transfer'
                        if re.match(f"^\s*twitter\s+@[\w_]+\s+{self.amt_with_commas_regex}\s*$", self.text):
                            response = self.transfer_spice(transfer_text, user.id)
                        show_generic_response = False

                    if self.text.startswith('telegram '):
                        msg_subject = 'SPICE Transfer'
                        if re.match(f"^\s*telegram\s+@[\w_]+\s+{self.amt_with_commas_regex}\s*$", self.text):
                            response = self.transfer_spice(transfer_text, user.id)
                        show_generic_response = False

                    if self.text.startswith('deposit'):
                        msg_subject = 'Deposit Alert'
                        response = f"Send deposit to this address:\n\n{user.simple_ledger_address}\n\n\n\n(Note that reddit spice bot can only support SPICE token as of now)"
                        if self.is_feat_disabled('deposit'):
                            response = get_maintenance_response('deposit')

                        show_generic_response = False

                    if self.text.startswith('withdraw'):
                        msg_subject = 'Withdrawal Alert'
                        amount = None
                        addr = None
                        token = None
                        withdraw_error = ''

                        try:
                            amount_temp = self.text.split()[1]
                            addr_temp = self.text.split()[-1].strip()
                            logger.info('\n\n%s', addr_temp)

                            try:
                                if not re.match(f'^{self.amt_with_commas_regex}$', amount_temp):
                                    raise ValueError('')
                                amount = float(amount_temp.replace(',', '').strip())
                            except ValueError:
                                response = "You have entered an invalid amount!"

                            if  addr_temp.startswith('simpleledger') and len(addr_temp) == 55:
                                addr = addr_temp.strip()
                                response = "You have entered an invalid SLP address!"
                        except IndexError:
                            response = "You have not entered a valid amount or SLP address!"

                        logger.info(addr)
                        logger.info(amount)

                        if addr and amount:
                            balance = get_balance(user.id, settings.SPICE_TOKEN_ID)
                            if amount <= balance:
                                # Limit withdrawals to 1 withdrawal per hour per user
                                withdraw_limit = False
                                latest_withdrawal = None
                                try:
                                    latest_withdrawal = Withdrawal.objects.filter(
                                        user=user,
                                        date_failed__isnull=True
                                    ).latest('date_created')
                                except Withdrawal.DoesNotExist as exc:
                                    logger.error(repr(exc))
                                if latest_withdrawal:
                                    last_withdraw_time = latest_withdrawal.date_created
                                    time_now = timezone.now()
                                    tdiff = time_now - last_withdraw_time
                                    withdraw_time_limit = tdiff.total_seconds()
                                    if withdraw_time_limit < 3600:
                                        withdraw_limit = True
                                        response = 'You have reached your hourly withdrawal limit!'

                                if not withdraw_limit:
                                    token = SLPToken.objects.filter(name='SPICE').first()
                                    if amount >= settings.WITHDRAWAL_LIMIT and token:
                                        withdrawal = Withdrawal(
                                            user=user,
                                            address=addr,
                                            amount=amount,
                                            slp_token=token
                                        )
                                        withdrawal.save()
                                        current_app.send_task(
                                            'main.tasks.withdraw_spice_tokens',
                                            args=(withdrawal.id,),
                                            kwargs={
                                                'user_id': message.author.name,
                                                'bot': 'reddit'
                                            },
                                            queue='reddit'
                                        )
                                        response = 'Your \U0001f336 SPICE \U0001f336 withdrawal request is being processed.'
                                    else:
                                        response = f"We can’t process your withdrawal request because it is below minimum. The minimum amount allowed is {settings.WITHDRAWAL_LIMIT} \U0001f336 SPICE."
                            else:
                                response = "You don't have enough \U0001f336 SPICE \U0001f336 to withdraw!"

                        if not addr or not amount:
                            response = """
                            Withdrawal can be done by running the following command:
                            \n/withdraw "amount" "simpleledger_address"
                            \n\nExample:
                            \n/withdraw 10 simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
                            \n\n(Note that reddit spice bot can only support SPICE token as of now)
                            """

                        if self.is_feat_disabled('withdrawal'):
                            response = get_maintenance_response('withdrawal')

                        show_generic_response = False


                if show_generic_response:
                    # Send the message
                    msg_subject = 'SpiceBot'

                    response = """ To learn more about SpiceBot, please visit:
                    \nhttps://spicetoken.org/bot_faq/
                    \n(Note that reddit spice bot can only support SPICE token as of now)
                    \nIf you need further assistance, please contact @spicedevs"""
                if response and not Response.objects.filter(body=body).exists():
                    resp = Response(
                        response_type='direct_message',
                        body=body
                    )
                    resp.save()
                    self.send_message(response, msg_subject, recipient, resp.id)
                    message.mark_read()
                return response



    def send_message(self, message, subject, recipient, id):
        response = Response.objects.get(pk=id)
        if response:
            body = {
                'message': message,
                'subject': subject,
                'recipient': recipient
            }
            try:
                self.reddit.redditor(
                    body['recipient']
                ).message(
                    body['subject'],
                    body['message']
                )
                response.botReplied = True
                response.save()
            except praw.exceptions.APIException as exc:
                logger.error(repr(exc))

        # Update user last activity
        user = User.objects.get(reddit_user_details__username=recipient)
        user.last_activity = timezone.now()
        user.save()

    def is_feat_disabled(self, feature):
        if feature == 'withdrawal':
            status = config.DEACTIVATE_WITHDRAWAL
        if feature == 'deposit':
            status = config.DEACTIVATE_DEPOSIT
        if feature == 'transfer':
            status = config.DEACTIVATE_TRANSFER
        if feature == 'tipping':
            status = config.DEACTIVATE_TIPPING
        # if feature == 'rain':
        #     status = config.DEACTIVATE_RAIN

        
        return status
