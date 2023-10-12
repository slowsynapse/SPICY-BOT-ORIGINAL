import base64
from main.models import SLPToken, User, Transaction
from django.db.models import Q
from main.utils.account import get_balance, create_transaction


from django.conf import settings
if 'sphere' in settings.INSTALLED_APPS:
    from sphere.models import Challenge
    from sphere.models import SLPToken as SphereToken
    from sphere.models import Exchange
    
from main.utils.responses import get_response
from hashlib import sha256
from main.tasks import send_telegram_message
from django.utils import timezone
import logging
import requests
import random
import json
import re
import uuid
import datetime
import webbrowser
import telegram
from constance import config
logger = logging.getLogger(__name__)


class SphereGame(object):

    def __init__(self):
        self.sphere_devs = []
        self.supported_tokens = {}
        self.token_regex = self.get_token_regex()
        self.bet_amount_regex = f"(((\d*[.]\d+)|(\d+))|((\d{1,3})(\,\d{3})+(\.\d+)?))\s+{self.token_regex}"        
        self.reply_markup= {
            "inline_keyboard": [
                [ {'text': 'Accept!', 'callback_data': ''} ]
            ]
        }

    
    def start_challenge(self, data):
        self.data = data
        self.pattern = f"^challenge\s+@[\w_]+\s+{self.bet_amount_regex}$"

        if 'message' in self.data.keys():
            message = self.data["message"]
            chat_type = message['chat']['type']
            from_id = message['from']['id']

            # Only sphere devs are allowed to play regardless of sphere deactivation.
            if config.DEACTIVATE_SPHERE:
                if str(from_id) not in self.sphere_devs: return

            username = ''
            if 'username' in message['from'].keys():
                username = message['from']['username']
            else:
                username = message['from']['first_name']

            chat_id = message["chat"]["id"]
            message_id = message["message_id"]           
            if 'text' in message.keys():
                self.text = message['text'].strip(' ')
                self.text, splitted_text = self.to_lower(self.text)
                if chat_type != 'private':
                    valid = True
                    message = ""                        
                    bet_amount = 0
                    
                    if re.findall(self.pattern, self.text):
                        if splitted_text[splitted_text.index('challenge')+1].replace('@', '') == username:
                            response = "❌  <b>Whoops! You can't challenge yourself.</b>  ❌"
                            send_telegram_message.delay(response, chat_id, message_id)
                            valid = False
                        
                        elif splitted_text[splitted_text.index('challenge')+1].replace('@', '') == settings.TELEGRAM_BOT_USER:                                
                            valid = False
                        
                        if not valid: return

                        user = User.objects.get(telegram_id=from_id)
                        
                        # check if user is frozen to prevent sending of messages..
                        if user.frozen:
                            message = f"Greetings {username}!\n\nYour account has been  ❄️  frozen  ❄\n"
                            message += "You are temporarily unable to do any spicebot operations at the moment."
                            send_telegram_message.delay(message, chat_id, message_id)
                            return

                        bet_amount = splitted_text[-2].replace(',', '')
                        contender_username =  splitted_text[-3].replace('@', '')
                        bet_amount = float(bet_amount)
                        slptoken = splitted_text[-1]
                        if slptoken.upper() not in self.supported_tokens.keys():
                            response = f"Sphere does not support { slptoken.upper() } at the moment."
                            send_telegram_message.delay(response, chat_id, message_id)
                            return
                        token_obj = self.supported_tokens[slptoken.upper()]
                    
                        if bet_amount < token_obj['min_bet_for_sphere']:
                            response = f"<b>Minimum bet</b> for sphere challenges is <b>{ token_obj['min_bet_for_sphere'] }</b>  {token_obj['emoji']}  <b>{slptoken.upper()}</b>  {token_obj['emoji']}!"
                            send_telegram_message.delay(response, chat_id, message_id)
                            return

                        valid_amount = False

                        if (bet_amount >= token_obj['min_bet_for_sphere'] and bet_amount <= token_obj['max_bet_for_sphere']) or valid_amount:

                            # Check if there's an existing challenge
                            challenge_qs = Challenge.objects.using('sphere_db').filter( Q(challenger_username=username) & Q(contender_username=contender_username) & Q(ended=False))
                            if challenge_qs.exists():
                                challenge = challenge_qs.last()
                                response = ""
                                if challenge.started:
                                    if challenge.challenger_username == username:
                                        response = f"<b>@{challenge.challenger_username}</b>, settle your on going challenge against @{challenge.contender_username}."
                                    elif challenge.contender_username == username:
                                        response = f"<b>@{challenge.contender_username}</b>,  settle your on going challenge against @{challenge.challenger_username}."
                                
                                if not challenge.accepted:
                                    challenge_duration = timezone.now() - challenge.date_created
                                    if challenge_duration.seconds < 180:
                                        response = f"<b>Hey {challenge.challenger_username}</b>, you already challenge @{challenge.contender_username}!"
                                    else:
                                        challenge.cancelled = True
                                        challenge.ended = True
                                        challenge.save()
                                if response:
                                    send_telegram_message.delay(response, chat_id, message_id)
                                    return

                            sphere_token, _ = SphereToken.objects.using('sphere_db').get_or_create(
                                name=token_obj['name'],
                                token_id=token_obj['token_id'],
                                emoji=token_obj['emoji']
                            )
                            challenge =  Challenge(
                                challenger_id=from_id,
                                challenger_username=username,
                                contender_username=contender_username, 
                                message_id=message_id,
                                chat_id=chat_id,
                                bet_amount=bet_amount,
                                result={},
                                slptoken=sphere_token,
                                percentage_fee=token_obj['sphere_percentage_fee'],
                                manager=token_obj['sphere_manager']
                            )

                            challenge.save(using='sphere_db')
                            
                            balance = get_balance(user.id,token_obj['token_id'])
                            if bet_amount <= balance:
                                self.reply_markup['inline_keyboard'][0][0]['callback_data'] = f"sphere-challenge:{challenge.id}"
                                self.reply_markup['inline_keyboard'][0][0]['text'] = "Accept!"
                                response = f"@{username} has challenged @{contender_username} to a duel for {bet_amount} {slptoken.upper()} {token_obj['emoji']}!"   
                                response += "<a href='https://enter-the-sphere.com/assets/EntertheSphereHandbook.pdf'> Learn To Play ! </a>"
                                send_telegram_message.delay(response, chat_id, message_id, reply_markup=self.reply_markup)
                            else:                                    
                                message = f"@{username}, you don't have enough {token_obj['emoji']} {slptoken.upper()} {token_obj['emoji']}!"
                                send_telegram_message.delay(message, chat_id, message_id)        
                                Challenge.objects.using('sphere_db').get(id=challenge.id).delete() 
                        else:
                            token_obj = self.supported_tokens[slptoken.upper()]
                            response = f"Bet amount must be between <b>{ token_obj['min_bet_for_sphere'] }</b> and <b>{ token_obj['max_bet_for_sphere'] }</b> {token_obj['emoji']} <b>{slptoken.upper()}</b> {token_obj['emoji']}!"
                            send_telegram_message.delay(response, chat_id, message_id)
                


    def start_game(self, data):
        match = data.get('matchId', '')
        challenger_token = match.split(':')[0]
        contender_token = match.split(':')[-1]
        qs = Challenge.objects.filter(
            Q(challenger_token=challenger_token) &
            Q(contender_token=contender_token) &
            Q(started=False)
        )
        if qs.exists():
            challenge = qs.first()
            challenge.started = True
            challenge.save()
            response = f"A {challenge.bet_amount}-{challenge.slptoken.name} {challenge.slptoken.emoji} match has been started between {challenge.challenger_username} and {challenge.contender_username}."
            send_telegram_message.delay(response, challenge.chat_id, challenge.message_id)

    def end_game(self, data):
        match = data.get('matchId', '')
        challenger_token = match.split(':')[0]
        contender_token = match.split(':')[-1]
        qs = Challenge.objects.using('sphere_db').filter(
            Q(challenger_token=challenger_token) &
            Q(contender_token=contender_token) &
            Q(ended=False)
        )
        if qs.exists():
            challenge = qs.first()
            winnerId = data.get('winnerId', '')
            if winnerId:
                user = User.objects.get(telegram_id=winnerId)
                winner_name = data.get('winner', '')
                losser_name = ''
                manager = User.objects.get(telegram_id=challenge.manager)
                game_amount = challenge.bet_amount * 2
                reward_amount = game_amount - (game_amount * challenge.percentage_fee)

                transaction_hash = f"{manager.id}-{challenge.message_id}-{challenge.chat_id}-{challenge.slptoken.name.lower()}-{reward_amount}-sphere-game-result"
                create_transaction(
                    manager.id,
                    reward_amount,
                    'Outgoing',
                    challenge.slptoken.id,
                    settings.TXN_OPERATION['SPHERE_CHALLENGE'],
                    transaction_hash=transaction_hash,
                    chat_id=challenge.chat_id
                )
                transaction_hash = f"{user.id}-{challenge.message_id}-{challenge.chat_id}-{challenge.slptoken.name.lower()}-{reward_amount}-sphere-game-result"
                create_transaction(
                    user.id,
                    reward_amount,
                    'Incoming',
                    challenge.slptoken.id,
                    settings.TXN_OPERATION['SPHERE_CHALLENGE'],
                    transaction_hash=transaction_hash,
                    chat_id=challenge.chat_id
                )

                if winnerId != challenge.challenger_id:
                    losser_name = challenge.challenger_username
                elif winnerId != challenge.contender_id:
                    losser_name = challenge.contender_username
                
                response = f"@{winner_name} destroyed @{losser_name} and won {challenge.bet_amount} {challenge.slptoken.emoji}. Congratulations!"
                send_telegram_message.delay(response, challenge.chat_id, challenge.message_id)
            else:
                challenge.cancelled = True
                challenge.ended = True
                self.unlock_stake(challenge, User.objects.get(telegram_id=challenge.challenger_id))
                self.unlock_stake(challenge, User.objects.get(telegram_id=challenge.contender_id))
                response = f"The match between @{challenge.challenger_username} and @{challenge.contender_username} has ended."
                send_telegram_message.delay(response, challenge.chat_id, challenge.message_id)

            challenge.result = data
            challenge.ended = True
            challenge.save()

    def accept_challenge(self, challenge):
        callback = self.data['callback_query']
        
        # Only sphere devs are allowed to play regardless of sphere deactivation.
        if config.DEACTIVATE_SPHERE:
            if str(callback['from']['id']) not in self.sphere_devs: return
        if not challenge.accepted:
            if challenge.contender_username == callback['from']['username']:
                # check contender's balance.
                challenge.contender_id = callback['from']['id']
                challenge.accepted = True
                challenge.save()

                self.set_game_token(challenge)

                user = User.objects.get(telegram_id=callback['from']['id'])
                balance = get_balance(user.id,challenge.slptoken.token_id)
                bot = telegram.Bot(token=settings.TELEGRAM_BOT_TOKEN)
                chat_id = callback['message']['chat']['id']

                if challenge.bet_amount <= balance:
                    # Initialize the game
                    game = telegram.CallbackGame()
                    short_name = f"{settings.SPHERE_SHORT_NAME}"
                    game.game_short_name= short_name
                    buttons = [[telegram.InlineKeyboardButton(text="Play Enter The Sphere",callback_game=game)]] 
                    keyboard_markup = telegram.InlineKeyboardMarkup(buttons)
                    bot.send_game(chat_id=chat_id,game_short_name=short_name,reply_markup=keyboard_markup) 
                    return 'accepted'
                else:
                    bot.answerCallbackQuery(callback_query_id=callback['id'],text='Insuficient Balance', show_alert=True)
                    return 'rejected'

    def unlock_stake(self, challenge, user):
        slptoken = SLPToken.objects.get(token_id=challenge.slptoken.token_id)
        # Sender outgoing transaction
        manager = User.objects.get(telegram_id=challenge.manager)
        transaction_hash = f"{manager.telegram_id}-{challenge.message_id}-{challenge.chat_id}-{slptoken.name.lower()}-{challenge.bet_amount}--{settings.TXN_OPERATION['SPHERE_CHALLENGE']}"
        create_transaction(
            manager.id,
            challenge.bet_amount,
            'Outgoing',
            slptoken.id,
            settings.TXN_OPERATION['SPHERE_CHALLENGE'],
            transaction_hash=transaction_hash,
            chat_id=challenge.chat_id
        )

        # Recipient incoming transaction
        transaction_hash = f"{user.telegram_id}-{challenge.message_id}-{challenge.chat_id}-{slptoken.name.lower()}-{challenge.bet_amount}--{settings.TXN_OPERATION['SPHERE_CHALLENGE']}"
        create_transaction(
            user.id,
            challenge.bet_amount,
            'Incoming',
            slptoken.id,
            settings.TXN_OPERATION['SPHERE_CHALLENGE'],
            transaction_hash=transaction_hash,
            chat_id=challenge.chat_id
        )
   
    def lock_stake(self,challenge, user, chat_id):
        
        slptoken = SLPToken.objects.get(token_id=challenge.slptoken.token_id)
        if challenge.challenger_id == user.telegram_id:
            transaction_hash = f"{challenge.challenger_token}-sphere-challenge"
        elif challenge.contender_id == user.telegram_id:
            transaction_hash = f"{challenge.contender_token}-sphere-challenge"

        # Sender outgoing transaction    
        sender_hash = "%s-%s" % (user.telegram_id, transaction_hash)
        qs_trs = Transaction.objects.filter(transaction_hash=sender_hash)
        if not qs_trs.exists():
            create_transaction(
                user.id,
                challenge.bet_amount,
                'Outgoing',
                slptoken.id,
                settings.TXN_OPERATION['SPHERE_CHALLENGE'],
                transaction_hash=sender_hash,
                chat_id=chat_id
            )

        # Recipient incoming transaction
        manager = User.objects.get(telegram_id=challenge.manager)
        recipient_hash = "%s-%s" % (manager.telegram_id, transaction_hash)
        qs_trs = Transaction.objects.filter(transaction_hash=recipient_hash)
        if not qs_trs.exists():
            create_transaction(
                manager.id,
                challenge.bet_amount,
                'Incoming',
                slptoken.id,
                settings.TXN_OPERATION['SPHERE_CHALLENGE'],
                transaction_hash=recipient_hash,
                chat_id=chat_id
            )
    
    def enter_game(self, callback, chat_id, message_id):
        from_id = str(callback['from']['id'])
        challenge_qs = Challenge.objects.using('sphere_db').filter(
            (Q(challenger_id=from_id) | Q(contender_id=from_id)) &
            Q(accepted=True) & Q(ended=False)
        )
        
        if challenge_qs.exists():
            challenge = challenge_qs.last()
            user = User.objects.get(telegram_id=callback['from']['id'])
            balance = get_balance(user.id, challenge.slptoken.token_id)
            if challenge.bet_amount > balance:
                message = f"@{user.telegram_username}, you don't have enough {challenge.slptoken.emoji} {challenge.slptoken.name.upper()} {challenge.slptoken.emoji}!"
                return send_telegram_message.delay(message, chat_id, message_id)

            self.lock_stake(challenge, user, callback['message']['chat']['id'])
            
            
            domain = settings.DOMAIN.split("https://")[-1]
            bot_url = f"{domain}/webhooks/telegram"
            game_url = ""
            base_url = "https://play.enter-the-sphere.com"        
            
            match = f'%s:%s' % (challenge.challenger_token, challenge.contender_token)
            if challenge.challenger_id == str(from_id):
                game_url = f'{base_url}?id={challenge.challenger_id}&match={match}&name={challenge.challenger_username}&token={challenge.challenger_token}&url={bot_url}'
            elif challenge.contender_id == str(from_id):
                game_url = f'{base_url}?id={challenge.contender_id}&match={match}&name={challenge.contender_username}&token={challenge.contender_token}&url={bot_url}'
            if game_url:
                bot = telegram.Bot(token=settings.TELEGRAM_BOT_TOKEN)
                bot.answerCallbackQuery(callback_query_id=callback['id'],url=game_url)

    def callback_query(self, data):
        self.data = data
        if 'callback_query' in self.data.keys():
            callback = self.data['callback_query']
            from_id = callback['from']['id']
            chat_id = callback['message']['chat']['id']
            message_id = callback['message']['message_id']
            if 'data' in callback.keys():
                # Catch contender's acceptance
                challenge_id = callback['data'].split(':')[-1] if callback['data'].startswith('sphere-challenge:') else ''
                if challenge_id:
                    user = User.objects.get(telegram_id=from_id)

                    challenge_qs = Challenge.objects.using('sphere_db').filter(
                        Q(contender_username=user.telegram_username) &
                        Q(ended=False) &
                        Q(accepted=False)
                    )
                    
                    if challenge_qs.exists():
                        challenge = challenge_qs.last()
                        balance = get_balance(user.id, challenge.slptoken.token_id)
                        if challenge.bet_amount > balance:
                            message = f"@{user.telegram_username}, you don't have enough {challenge.slptoken.emoji} {challenge.slptoken.name.upper()} {challenge.slptoken.emoji}!"
                            return send_telegram_message.delay(message, chat_id, message_id)                    
                        return self.accept_challenge(challenge)

            elif 'game_short_name' in callback.keys():
                # Catch responses from both players
                if callback['game_short_name'] == settings.SPHERE_SHORT_NAME:
                    self.enter_game(callback, chat_id, message_id)

    def request_game_token(self, tg_user_id):
        token = str(uuid.uuid4()).replace('-','')
        resp = requests.post('http://34.92.159.8:8082/setToken', json={"id": str(tg_user_id), "token": str(token)})
        if int(resp.status_code) == 200: return token

    def set_game_token(self, challenge):
        if not challenge.challenger_token:
            game_token = self.request_game_token(challenge.challenger_id)
            challenge.challenger_token = game_token

        if not challenge.contender_token:
            game_token = self.request_game_token(challenge.contender_id)
            challenge.contender_token = game_token
        challenge.save(using='sphere_db')
        return challenge.challenger_token, challenge.contender_token
        
    def to_lower(self, text):
        splitted_text = text.split()
        lowered_arr = []
        for word in splitted_text:
            if not re.findall('^@\w+$', word):
                lowered_arr.append(word.lower())
            else:
                lowered_arr.append(word)
        return ' '.join(lowered_arr), lowered_arr    

    def get_token_regex(self):
        token_regex = ''
        sphere_tokens = SLPToken.objects.exclude(Q(sphere_manager=None) or Q(sphere_manager=""))

        tokens = list(sphere_tokens.values('name', 'verbose_names', 'allowed_devs'))
        
        for token in list(sphere_tokens.values()):
            self.supported_tokens[token['name'].upper()] = token
            for name in token['verbose_names']: self.supported_tokens[name.upper()] = token

        for token in tokens:
            verbose = [f"{name.lower()}|" for name in token['verbose_names']]
            token_regex += f'{token["name"].lower()}|{ "".join(verbose)}'
            self.sphere_devs += token['allowed_devs']
        token_regex = token_regex[:-1]
        token_regex = f'({token_regex})'.replace('bch', 'sat')
        return token_regex