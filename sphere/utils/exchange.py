import re
from main.utils.account import get_balance, create_transaction
from constance import config
from main.tasks import send_telegram_message
from django.db.models import Q
from django.utils import timezone
from sphere.models import SLPToken as SLPTokenDB2
from main.models import SLPToken, User, TelegramGroup
from main.utils.responses import get_response
from django.conf import settings
from sphere.models import Exchange

class TokenExchange:

    def __init__(self):
        self.buy_pattern = 'buy\s+\d+\s+\w+'

    def to_lower(self, text):
        splitted_text = text.split()
        lowered_arr = []
        for word in splitted_text:
            if not re.findall('^@\w+$', word):
                lowered_arr.append(word.lower())
            else:
                lowered_arr.append(word)
        return ' '.join(lowered_arr), lowered_arr    
        
    def start(self, data):
        self.data = data

        if 'message' in self.data.keys():
            message = self.data["message"]
            chat_type = message['chat']['type']
            from_id = message['from']['id']
            chat_id = message["chat"]["id"]
            message_id = message["message_id"]           

            TelegramGroup.objects.get_or_create(chat_id=message["chat"]["id"])

            if 'text' in message.keys():
                self.text = message['text'].strip(' ')
                self.text, splitted_text = self.to_lower(self.text)
                if chat_type == 'private':
                    
                    if re.findall(self.buy_pattern, self.text):
                        if config.DEACTIVATE_BUYING_OF_ORB: return
                        Exchange.objects.using('sphere_db').filter(Q(buyer_id=from_id) & Q(date_processed=None)).delete()

                        # Alter this are to support buying and selling of other tokens
                        default_token = 'spice'
                        desired_token = splitted_text[2].upper()
                        desired_amount = splitted_text[1]

                        if default_token.upper() == desired_token:
                            response = f'Buying of {desired_token} is not allowed.'
                            return send_telegram_message.delay(response, chat_id, message_id)

                        # Payment Token
                        payment_token_qs = SLPToken.objects.filter(Q(name=default_token) | Q(verbose_names__icontains=default_token))
                        if not payment_token_qs.exists(): return send_telegram_message.delay(get_response('commands'), chat_id, message_id)
                        obj_payment_token = payment_token_qs.first()

                        # Desired Token
                        desired_token_qs = SLPToken.objects.filter(Q(name=desired_token) | Q(verbose_names__icontains=desired_token))
                        if not desired_token_qs.exists(): return send_telegram_message.delay(get_response('commands'), chat_id, message_id)
                        
                        obj_desired_token = desired_token_qs.first()
                        seller = obj_desired_token.sphere_manager
                        exchanges = obj_desired_token.token_exchange
                        rate = exchanges.get(default_token, None)

                        if rate:
    
                            desired_token, _ = SLPTokenDB2.objects.using('sphere_db').get_or_create(
                                name=obj_desired_token.name,
                                token_id=obj_desired_token.token_id,
                                emoji=obj_desired_token.emoji
                            )

                            payment_token, _ = SLPTokenDB2.objects.using('sphere_db').get_or_create(
                                name=obj_payment_token.name,
                                token_id=obj_payment_token.token_id,
                                emoji=obj_payment_token.emoji
                            )
        
                            seller = User.objects.filter(telegram_id=seller)
                            if not seller.exists(): return
                            seller = seller.first()

                            seller_balance = get_balance(seller.id, desired_token.token_id)
                            payment_amount = float(desired_amount) * float(rate)

                            # Check if the seller have enough amount of desired token.
                            if float(seller_balance) >= float(payment_amount):
                                response = f'{desired_amount} {desired_token.name.lower()} costs {payment_amount} {payment_token.name.lower()}. Respond with <b><u>yes</u></b> to proceed.'
                                exchange = Exchange(
                                    buyer_id=from_id,
                                    seller_id=seller.telegram_id,
                                    payment_token=payment_token,
                                    payment_amount=payment_amount,
                                    exchange_token=desired_token,
                                    exchange_amount=desired_amount,
                                )
                                exchange.save(using='sphere_db')
                            else:
                                response = f"Buying of { obj_desired_token.name.lower() } is unavailable at the moment."
                        else:
                            response = f'Buying of { obj_desired_token.name.lower() } is not yet supported.'
                        return send_telegram_message.delay(response, chat_id, message_id)

                    elif self.text == 'yes':
                        exchange = Exchange.objects.using('sphere_db').filter(Q(buyer_id=from_id) & Q(date_processed=None))
                        if not exchange.exists(): return send_telegram_message.delay(get_response('commands'), chat_id, message_id)

                        response = ""
                        exchange = exchange.first()
                        

                        # Check balance again.
                        buyer = User.objects.get(telegram_id=exchange.buyer_id)
                        seller = User.objects.get(telegram_id=exchange.seller_id)

                        buyer_balance = float(get_balance(buyer.id, exchange.payment_token.token_id))
                        seller_balance = float(get_balance(seller.id, exchange.exchange_token.token_id))


                        if buyer_balance < float(exchange.payment_amount):
                            response = f"Sorry, You don't have enough {exchange.payment_token.name.lower()} balance."
                            exchange.delete()
                            return send_telegram_message.delay(response, chat_id, message_id)
                            
                        if seller_balance < float(exchange.exchange_amount):
                            response = f"Buying of { exchange.payment_token.name.lower() } is unavailable at the moment."
                            exchange.delete()
                            return send_telegram_message.delay(response, chat_id, message_id)
                        
                        payment_token = SLPToken.objects.get(token_id=exchange.payment_token.token_id)
                        exchange_token = SLPToken.objects.get(token_id=exchange.exchange_token.token_id)

                        # PAYMENT TRANSACTION
                        buyer_hash = f"{buyer.id}-{message_id}-{chat_id}-{exchange.payment_token.name.lower()}-{exchange.payment_amount}-outgoing"
                        create_transaction(
                            buyer.id,
                            exchange.payment_amount,
                            'Outgoing',
                            payment_token.id,
                            settings.TXN_OPERATION['EXCHANGE'],
                            transaction_hash=buyer_hash,
                            chat_id=chat_id
                        )

                        seller_hash = f'{seller.id}-{message_id}-{chat_id}-{exchange.payment_token.name.lower()}-{exchange.payment_amount}-incoming'
                        create_transaction(
                            seller.id,
                            exchange.payment_amount,
                            'Incoming',
                            payment_token.id,
                            settings.TXN_OPERATION['EXCHANGE'],
                            transaction_hash=seller_hash,
                            chat_id=chat_id
                        )

                        # EXCHANGE TRANSACTION
                        buyer_hash = f"{buyer.id}-{message_id}-{chat_id}-{exchange.exchange_token.name.lower()}-{exchange.exchange_amount}-incoming"
                        create_transaction(
                            buyer.id,
                            exchange.exchange_amount,
                            'Incoming',
                            exchange_token.id,
                            settings.TXN_OPERATION['EXCHANGE'],
                            transaction_hash=buyer_hash,
                            chat_id=chat_id
                        )

                        seller_hash = f'{seller.id}-{message_id}-{chat_id}-{exchange.exchange_token.name.lower()}-{exchange.exchange_amount}-outgoing'
                        create_transaction(
                            seller.id,
                            exchange.exchange_amount,
                            'Outgoing',
                            exchange_token.id,
                            settings.TXN_OPERATION['EXCHANGE'],
                            transaction_hash=seller_hash,
                            chat_id=chat_id
                        )

                        exchange.date_processed = timezone.now()
                        exchange.save(using='sphere_db')

                        response = f"Transaction succeeded. You've been credited with  {exchange.exchange_amount} {exchange.exchange_token.emoji}."
                        send_telegram_message.delay(response, chat_id, message_id)
                    else:
                        Exchange.objects.using('sphere_db').filter(Q(buyer_id=from_id) & Q(date_processed=None)).delete()