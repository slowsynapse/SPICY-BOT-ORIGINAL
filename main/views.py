import time
import json
import os
import logging
import datetime as dt
import subprocess

from rest_framework import authentication, permissions
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.contrib.auth import authenticate, login
from rest_framework.decorators import api_view, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_200_OK
)

import csv
import requests
import string
import base64
import random
import collections, functools, operator 

from celery.result import AsyncResult
from subprocess import Popen, PIPE
from main.utils.account import create_transaction, get_balance, swap_related_transactions
from main.utils.telegram import TelegramBotHandler
from main.utils.reddit import RedditBot
from main.utils.twitter import TwitterBot
from main.utils.aws import AWS

from main.utils.token_tip_text import TokenTipText
from main.utils.token_tip_emoji import TokenTipEmoji

from main.models import (
    Content,
    User,
    Media,
    FaucetDisbursement,
    Account,
    TelegramGroup,
    WeeklyReport,
    Withdrawal,
    Transaction,
    Subscriber,
    Deposit,
    SLPToken,
    Metric
)
from django.db.models import Sum, Count, Q, F
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.core.paginator import Paginator, EmptyPage
from PIL import Image
from django.views import View
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum
from django.utils.crypto import get_random_string
from datetime import timedelta, datetime
from random import randint
from main.tasks import (
    process_faucet_request,
    restart_supervisor,
    withdraw_spice_tokens,
    transfer_spice_to_another_acct,
    deposit_initial_save,
    deposit_analyzer,
    # process_wagerbot_bet
)
from django.shortcuts import render
from difflib import SequenceMatcher
from django.shortcuts import redirect
import time
from django.db import transaction as trans
from constance import config

from sphere.utils.game import SphereGame
from sphere.utils.exchange import TokenExchange

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes((AllowAny,))
def signup(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if username is None or password is None:
        return Response({'error': 'Please provide both username and password'},
                        status=HTTP_400_BAD_REQUEST)

    new_user = Account.objects.create_user(
        username=username,
        password=password
    )
    new_user.save()

    token, _ =  Token.objects.get_or_create(user=new_user)

    return Response(
        {'success': True, 'token': token.key, 'username': username},
        status=HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes((AllowAny,))
def login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if username is None or password is None:
        return Response({'error': 'Please provide both username and password'},
                        status=HTTP_400_BAD_REQUEST)
    user = authenticate(username=username,password=password)
    if not user:
        return Response({'error': 'Invalid Credentials'},
                        status=HTTP_404_NOT_FOUND)    
    token, _ = Token.objects.get_or_create(user=user)

    return Response(
        {'success': True, 'token': token.key, 'username':username},
        status=HTTP_200_OK
    )

@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def logout(request):
    request.user.auth_token.delete()    
    return Response({'status': 'success'}, status=HTTP_200_OK)

@api_view(['POST'])
@permission_classes((IsAuthenticated, ))
def connectAccount(request):
    token = request.META.get('HTTP_AUTHORIZATION').replace('Token ', '')
    user = Token.objects.get(key=token).user

    account = Account.objects.get(username=user.username)
    username = request.data.get('username')
    source = request.data.get('source')
    #Generate Random Key
    confirmation_key = get_random_string(length=6)
    users = User.objects.all()
    proceed = False

    status = None
    for u in users:
        #send code to telegram
        if source == 'telegram' and u.telegram_display_name == username:                                    
            details = u.telegram_user_details            
            message = "Your code is %s\n" % confirmation_key
            name = u.telegram_display_name
            url = 'https://api.telegram.org/bot'
            data = {
                "chat_id": details['id'],
                "text": message, 
                "parse_mode": "HTML",
            }            

            response = requests.post(
                f"{url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
            )

            status = response.status_code
            if status == 200:
                proceed = True                           
        #send code to twitter
        elif source == 'twitter' and u.twitter_screen_name == username:
            name = u.twitter_screen_name
            message = "Your code is %s\n" % confirmation_key
            bot = TwitterBot()
            bot.send_direct_message(u.twitter_id, message)
            proceed = True

        if proceed:
            confirmation = {
                "key": confirmation_key,
                "source": source,
                "user": name
            }
            account.confirmation = confirmation
            account.save()  

            return Response({"status": "success"}, status=HTTP_200_OK)        

    return Response({"status": "failure"}, status=HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def confirmAccount(request):
    token = request.META.get('HTTP_AUTHORIZATION').replace('Token ', '')
    user = Token.objects.get(key=token).user
    account = Account.objects.get(username=user.username)
    proceed = False

    code = request.data.get('code')
    code = code.replace(' ', '')     
    if account.confirmation['key'] == code:        
        username = account.confirmation['user']
        source = account.confirmation['source']
        users = User.objects.all()
         
        for u in users:            
            if source == 'telegram' and u.telegram_display_name == username:
                proceed = True
            if source == 'twitter' and u.twitter_screen_name == username:
                proceed = True

            if proceed:
                u.account = account
                u.save()
                
                account.confirmation = None
                account.save()        
                
                return Response({"status": "success"}, status=HTTP_200_OK)
    return Response({"status": "failure"}, status=HTTP_400_BAD_REQUEST)


class SubscribeView(View):

    def post(self, request):
        # username, password, payment, email_address
        data = json.loads(request.body)
        username = data.get('username', '')
        password = data.get('password', '')
        payment = data.get('payment', False)
        email = data.get('email', '')
        app_name = data.get('app_name', '')
        response = {}

        response['success'] = False
        if payment:
            if not Subscriber.objects.filter(username=username).exists():
                if not Subscriber.objects.filter(email=email).exists():
                    if len(password) > 8:

                        token = get_random_string(length=16)
                        new_subscriber = Subscriber(
                            username = username,
                            password=password,
                            app_name=app_name,
                            email=email,
                            token=token,
                            payment=payment
                        )
                        new_subscriber.save()
                        response['success'] = True
                        response['app_name'] = app_name
                        response['token_key'] = token                        
                    else:
                        response['error'] = 'Password must be at least 8 characters long'
                else:
                    response['error'] = 'Email is already in use'
            else:
                response['error'] = 'Usename already exists'
        else:
            response['error'] = 'Payment not processed'

        return JsonResponse(response)

        
class ProofOfFrensView(View):

    def get(self, request):        
        data = User.objects.all().order_by('pof')[0:50]

        return JsonResponse({'success': True})        


class RestartSupervisorView(View):

    def get(self, request):
        restart_supervisor.delay()
        time.sleep(.8)
        return redirect('/admin')

    
class TelegramBotView(View):

    def post(self, request, *args, **kwargs):
        
        telegram_data = json.loads(request.body)        
        if 'message' in telegram_data.keys():            
            proceed = True
            try:
                text = telegram_data['message']['text']
            except KeyError as exc:
                proceed = False
            if proceed:
                #redis = settings.REDISKV
                #message_ids = redis.lrange('telegram_message_ids', 0, -1)
                #msg_id = str(telegram_data['message']['message_id']).encode()
                
                # Temporarily disabled duplicate message checking as this has caused
                # the bot to be silent in a number of groups even when no duplicate messages is sent
                # TODO: This needs to be re-checked.
                
                # if msg_id not in message_ids:
                #if True:
                #    if not text.lower().startswith('rain'): redis.lpush('telegram_message_ids', msg_id)
                    
                token_tip_emoji_calc = TokenTipEmoji(text=text)
                token_tip_text_calc = TokenTipText(text=text)

                has_tips = token_tip_emoji_calc.extract()
                has_text_tips = token_tip_text_calc.extract()

                for key in has_text_tips.keys():
                    has_tips[key] = has_text_tips[key]
                
                if has_tips.keys():
                    for token in has_tips.keys():    
                        value = has_tips[token]
                        if value > 0:
                            handler = TelegramBotHandler(telegram_data, **{
                                "tip_amount": value,
                                "token_name": token
                            })
                            handler.process_data()
                            handler.respond()
                else:
                    handler = TelegramBotHandler(telegram_data)
                    handler.process_data()
                    handler.respond()
                
                if has_tips.keys():
                    for token in has_tips.keys():    
                        value = has_tips[token]
                        if value > 0:
                            handler = TelegramBotHandler(telegram_data, **{
                                "tip_amount": value,
                                "token_name": token
                            })
                            handler.process_data()
                            handler.respond()
                else:
                    handler = TelegramBotHandler(telegram_data)
                    handler.process_data()
                    handler.respond()
                
                SphereGame().start_challenge(telegram_data)
                TokenExchange().start(telegram_data)

        elif 'callback_query' in telegram_data.keys():
            handler = TelegramBotHandler(telegram_data)
            handler.process_data()
            handler.respond()

            game = SphereGame()
            game.callback_query(telegram_data)
            
        elif 'start' == kwargs.get('params', ''): SphereGame().start_game(telegram_data)

        elif 'end' == kwargs.get('params', ''): SphereGame().end_game(telegram_data)

        settings.REDISKV.set('last_error_log',request.body)


        return JsonResponse({"ok": "POST request processed"})


class WeeklyReportView(View): 

    def get(self, request, id):        
        weekly_report = json.loads(WeeklyReport.objects.get(id=id).report)
        date = WeeklyReport.objects.get(id=id).date_generated
        date = date.strftime('_%d_%m_%Y')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="weekly_report%s.csv"' % date

        writer = csv.writer(response)
        writer.writerow(['Group', 'Total Weekly Contents', 'Total Weekly Tips'])
        for report in weekly_report:
            writer.writerow([report['group'], report['total_weekly_contents'], report['total_tips']])
        return response


class SpiceFeedStats(View):

    def get(self, request):
        tg_channels = TelegramGroup.objects.all()
        users_received_tips = User.objects.annotate(
            received=Count('tips_received')
        ).filter(
            received__gt=0
        )
        users_sent_tips = User.objects.annotate(
            sent=Count('tips_sent')
        ).filter(
            sent__gt=0
        )
        users = users_received_tips | users_sent_tips
        tips = Content.objects.all()
        disbursements = FaucetDisbursement.objects.all()

        # All time stats
        response = {
            'all_time': {
                'total_telegram_channels': tg_channels.count(),
                'total_tips': tips.count(),
                'total_tip_amount': tips.aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0,
                'total_users': users.count(),
                'faucet_disbursements': disbursements.count(),
                'total_faucet_disbursement': disbursements.aggregate(Sum('amount'))['amount__sum'] or 0
            }
        }

        # Last 24 hours
        data = {}
        dt = timezone.now() - timedelta(hours=24)
        tips_sub = tips.filter(date_created__gte=dt)
        disbursements_sub = disbursements.filter(date_created__gte=dt)
        data['total_telegram_channels'] = tg_channels.filter(date_created__gte=dt).count()
        data['total_tips'] = tips_sub.count()
        data['total_tip_amount'] = tips_sub.aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0
        data['total_users'] = users.filter(date_created__gte=dt).count()
        data['faucet_disbursements'] = disbursements_sub.count()
        data['total_faucet_disbursement'] = disbursements_sub.aggregate(Sum('amount'))['amount__sum'] or 0
        response['last_24_hours'] = data

        return JsonResponse(response)


class SpiceFeedContentView(View):
    
    def get(self, request):
        category = request.GET.get('category', 'latest')
        media_only = request.GET.get('media_only', 'false')
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 50)
        contents = Content.objects.filter(recipient__ban=False)
        all_contents = contents.filter(
            post_to_spicefeed=True
        )
        if media_only == 'true':
            all_contents = all_contents.annotate(
                media_count=Count('media')
            ).filter(
                media_count__gte=1
            )
        if category == 'milklist':
            all_contents = all_contents.filter(
                post_to_spicefeed=True,
                tip_amount__lt=0.000001,
                parent=None
            ).order_by('-last_activity')
        else:
            all_contents = all_contents.filter(
                post_to_spicefeed=True,
                tip_amount__gte=5,
                parent=None            
            )
            if category == 'latest':
                all_contents = all_contents.order_by('-last_activity')
            elif category == 'hottest':
                last_24_hrs = timezone.now() - timedelta(hours=24)
                all_contents = all_contents.filter(
                    parent=None,
                    last_activity__gte=last_24_hrs
                ).order_by('-total_tips')
        paginator = Paginator(all_contents, per_page)
        response = {}
        page_contents = None
        try:
            page_contents = paginator.page(int(page))
        except EmptyPage:
            response['success'] = False
            response['error'] = 'empty_page'
        contents = []
        if page_contents:
            for content in page_contents.object_list:
                if content.children.count():
                    if category == 'latest':
                        content = content.children.last()
                if content.post_to_spicefeed:
                    int_amount = content.tip_amount * 100000000
                    data = {
                        'created_at': content.date_created.isoformat(),
                        'permalink': content.id,
                        'service': content.source,
                        'int_amount': int_amount,
                        'string_amount': str(int_amount),
                    }                
                    temp_contents = Content.objects.filter(parent=content, post_to_spicefeed=True)                
                    total_tips = content.tip_amount
                    for temp in temp_contents:
                        total_tips+=temp.tip_amount
                    data['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
                    recipient_instance = content.recipient
                    if recipient_instance.display_username:
                        data['tipped_user_name'] = recipient_instance.get_username
                    else:    
                        data['tipped_user_name'] = recipient_instance.anon_name
                    sender_instance = content.sender
                    if sender_instance.display_username:
                        data['tipper_user'] = sender_instance.get_username
                    else:    
                        data['tipper_user'] = sender_instance.anon_name                    

                    if content.source == 'telegram':
                        try:
                            original_message = content.details['message']['reply_to_message']['text']
                        except KeyError:
                            original_message = ''
                        #data['tipped_user_name'] = content.recipient.telegram_display_name
                        #data['tipper_user'] = content.sender.telegram_display_name
                        data['tipper_message'] = content.details['message']['text']
                        data['tipper_message_date'] = content.details['message']['date']
                        data['original_message'] = original_message
                        data['original_message_mediapath'] = content.get_media_url()
                        data['additional_tippers'] = []
                    elif content.source == 'twitter':
                        try:
                            original_message = content.details['replied_to']['text']
                        except KeyError:
                            original_message = ''
                        #data['tipped_user_name'] = content.recipient.twitter_screen_name
                        #data['tipper_user'] = content.sender.twitter_screen_name
                        data['tipper_message'] = content.details['reply']['text']
                        data['tipper_message_date'] = content.details['reply']['created_at']
                        data['original_message'] = original_message
                        data['original_message_mediapath'] = ''
                        data['additional_tippers'] = []

                    elif content.source == 'reddit':
                        logger.info('in reddit')
                        try:
                            original_message = content.details['submission_details']['text']
                        except KeyError:
                            original_message = ''
                        #data['tipped_user_name'] = content.recipient.reddit_username
                        #data['tipper_user'] = content.sender.reddit_username
                        data['tipper_message'] = content.details['comment_details']['comment_body']
                        data['tipper_message_date'] = content.details['comment_details']['date_created']
                        data['original_message'] = original_message
                        data['original_message_mediapath'] = content.details['submission_details']['media_url']
                        data['additional_tippers'] = []

                    # For now, exclude reddit content from spicefeed
                    #if content.source != 'reddit':
                        # Second-level filtering for media only
                    if media_only == 'true':
                        if 'original_message_mediapath' in data.keys():
                            if data['original_message_mediapath']:
                                contents.append(data)
                    else:
                        contents.append(data)

        if len(contents):
            response['success'] = True
            try:
                next_page = page_contents.next_page_number()
            except EmptyPage:
                next_page = None
            try:
                previous_page = page_contents.previous_page_number()
            except EmptyPage:
                previous_page = None
            response['pagination'] = {
                'page': page,
                'per_page': per_page,
                'next_page_number': next_page,
                'previous_page_number': previous_page
            }
            response['contents'] = contents
        return JsonResponse(response)


class SpiceFeedLeaderBoardView(View):

    def get(self, request):
        category = request.GET.get('category', 'sent')
        if category == 'sent':
            query = Content.objects.values('sender__id').annotate(
                total_tipped=Sum('tip_amount')).order_by('-total_tipped')[0:50]
        elif category == 'received':
            query = Content.objects.values('recipient__id').annotate(
                total_received=Sum('tip_amount')
            ).order_by('-total_received')[0:50]
        ranking = []
        for item in query:
            if category == 'sent':
                user = User.objects.get(id=item['sender__id'])
                del item['sender__id']
                item['total_tipped'] *= 100000000
            elif category == 'received':
                user = User.objects.get(id=item['recipient__id'])
                del item['recipient__id'] 
                item['total_received'] *= 100000000

            if user.display_username:
                item['username'] = user.get_username
            else:
                item['username'] = user.anon_name #user.telegram_display_name or user.twitter_screen_name or user.reddit_username

            item['mediapath'] = ''
            ranking.append(item)
        response = {
            'ranking': ranking
        }
        return JsonResponse(response)


class SpiceFaucetView(View):

    def post(self, request):
        data = json.loads(request.body)
        slp_address = data.get('slp_address')
        recaptcha_token = data.get('recaptcha_token')
        response = {'success': False}

        url = 'https://www.google.com/recaptcha/api/siteverify'
        payload = {
            'secret': settings.RECAPTCHA_SECRET,
            'response': recaptcha_token
        }
        resp = requests.post(url, payload)
        if resp.status_code == 200 and resp.json()['success']:
            if not slp_address.startswith('simpleledger') and not len(slp_address) == 55:
                response['error'] = "The SLP address is invalid"
            else:

                from_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                to_date = timezone.now()
                total_today = FaucetDisbursement.objects.filter(
                    date_completed__gt=from_date,
                    date_completed__lte=to_date
                ).aggregate(Sum('amount'))
                total_today = total_today['amount__sum'] or 0
                
                if total_today < settings.FAUCET_DAILY_LIMIT:
                    ip_address = request.META.get('HTTP_X_FORWARDED_FOR', None)
                    if not ip_address:
                        ip_address = request.META.get('REMOTE_ADDR', '')
                    cookies = request.META.get('HTTP_COOKIE', '')                    
                    try:
                        cookies_map = dict([x.split('=') for x in cookies.split(';')])                        
                        cookies_map = { key.strip(' '): val for (key, val) in cookies_map.items() }                    
                        ga_cookie = cookies_map['_ga']
                    except ValueError:
                        ga_cookie = None
                    except KeyError:
                        ga_cookie = None
                    proceed = False
                    threshold = timezone.now() - timedelta(hours=24)
                    
                    ip_check = FaucetDisbursement.objects.filter(
                        ip_address=ip_address,
                        date_created__gt=threshold
                    )
                    slp_check = FaucetDisbursement.objects.filter(
                        slp_address=slp_address,
                        date_created__gt=threshold
                    )
                    if ip_check.count() == 0 and slp_check.count() == 0:
                        proceed = True
                        if ga_cookie is not None:
                            cookie_check = FaucetDisbursement.objects.filter(
                                ga_cookie=ga_cookie,
                                date_created__gt=threshold
                            )
                            if cookie_check.count():
                                proceed = False
                    if not proceed:
                        response['error'] = 'We detected that you already submitted a request recently. '
                        response['error'] += 'You can only request once every 24 hours. Try again tomorrow!'
                else:
                    proceed = False
                    response['error'] = 'Our daily limit for the amount of SPICE to give out has been reached. Try again tomorrow!'

                if proceed:
                    amount = 20
                    n = randint(19, 76)
                    if n == 19:
                        amount = 0
                    elif n == 76:
                        amount = 500
                    else:
                        amount = n

                    faucet_tx = FaucetDisbursement(
                        slp_address=slp_address,
                        ip_address=ip_address,
                        ga_cookie=ga_cookie,
                        amount=amount
                    )
                    faucet_tx.save()

                    task = process_faucet_request.delay(faucet_tx.id)
                    response['task_id'] = task.task_id
                    response['amount'] = amount
                    response['success'] = True
        else:
            response['error'] = "The captcha system marked you as a potential bot.<br>Either you are a real or you took so long to submit the form and the captcha token just expired.<br>If it's the latter, then just go back to the form and try again."

        return JsonResponse(response)


class SpiceFaucetTaskView(View):

    def post(self, request):
        data = json.loads(request.body)
        task_id = data.get('task_id')        
        res = AsyncResult(task_id)
        response = {'success': False}

        if res.ready():
            result = res.result
            try:
                if result['status'] == 'success':               
                    tx_url = '\nhttps://explorer.bitcoin.com/bch/tx/' + result['txid']
                    response = {
                        'tx_url': tx_url,
                        'success': True
                    }
                elif result['status'] == 'failure':
                    response['error'] = 'There was an error in processing your request'
            except TypeError as exc:
                logger.error(exc)
        return JsonResponse(response)


class SpiceFeedContentDetailsView(View):
    
    def get(self, request, id):
        response = None
        file_type= None
        post = {}
        top_tipper = {}      
        original_message = ''
        item = Content.objects.filter(pk=id)
        if item.exists():
            item = item.first()
            if item.post_to_spicefeed:
                chat_name = ''
                original_message = ''

                # Get tipped message     
                if item.recipient.display_username:
                    user = item.recipient.get_username
                else:
                    user = item.recipient.anon_name

                if item.source == 'telegram':   
                    #user = item.recipient.telegram_display_name
                    date = item.details['message']['reply_to_message']['date']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    if 'text' in item.details['message']['reply_to_message'].keys():
                        original_message = item.details['message']['reply_to_message']['text']
                    if 'chat' in item.details['message'].keys():
                        if 'title' in item.details['message']['chat'].keys(): 
                            chat_name = item.details['message']['chat']['title']
                elif item.source == 'twitter':
                    #user = item.recipient.twitter_screen_name
                    date = item.details['replied_to']['created_at']
                    date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                    if 'text' in item.details['replied_to'].keys():
                        original_message = item.details['replied_to']['text']
                elif item.source == 'reddit':
                    #user = item.recipient.reddit_username
                    date = item.details['comment_details']['date_created']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    if 'text' in item.details['submission_details'].keys():
                        original_message = item.details['submission_details']['text']
                    if 'subreddit' in item.details['submission_details'].keys():
                        chat_name = item.details['submission_details']['subreddit']
                post = {
                    'tipped_user_name': user,
                    'original_message': original_message,
                    'date': date,
                    'source': item.source,
                    'chat_name': chat_name
                }        

                # Get media URL
                post['original_message_mediapath'] = item.get_media_url()

                #Get first tipper
                first_tipper = {}

                if item.sender.display_username:
                    first_tipper['tipper_user'] = item.sender.get_username
                else:
                    first_tipper['tipper_user'] = item.sender.anon_name            

                if item.source == 'telegram':
                    #first_tipper['tipper_user'] = item.sender.telegram_display_name
                    first_tipper['tipper_message'] = item.details['message']['text']            
                elif item.source == 'twitter':
                    #first_tipper['tipper_user'] = item.sender.twitter_screen_name
                    first_tipper['tipper_message'] = item.details['reply']['text']
                elif item.source == 'reddit':
                    #first_tipper['tipper_user'] = item.sender.reddit_username
                    first_tipper['tipper_message'] = item.details['comment_details']['comment_body']
                first_tipper['tip_amount'] = item.tip_amount

                #List of all tippers
                contents={}
                date = None
                contents = Content.objects.filter(parent=item)
                post['total_tips'] = 0

                if item.sender.display_username:
                    sender = item.sender.get_username
                else:
                    sender = item.sender.anon_name

                if item.source == 'telegram':
                    date = item.details['message']['date']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    #sender = item.sender.telegram_display_name
                    message = item.details['message']['text']
                elif item.source == 'twitter':
                    date = item.details['reply']['created_at']
                    date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                    #sender = item.sender.twitter_screen_name
                    message = item.details['reply']['text']
                elif item.source == 'reddit':
                    date = item.details['comment_details']['date_created']
                    date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                    #sender = item.sender.reddit_username
                    message = item.details['comment_details']['comment_body']
                tips = [{
                    'tipper': sender,
                    'amount': '{0:.10f}'.format(item.tip_amount).rstrip('0').rstrip('.'),
                    'date': date,
                    'message': message

                }]
                total_tips = item.tip_amount

                for content in contents:
                    sender_instance = content.sender
                    if sender_instance.display_username:            
                        sender = sender_instance.get_username
                    else:
                        sender = sender_instance.anon_name

                    if item.source == 'telegram':
                        date = content.details['message']['date']
                        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                        #sender = content.sender.telegram_display_name
                        message = content.details['message']['text']    
                    elif item.source == 'twitter':
                        date = content.details['reply']['created_at']
                        date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                        #sender = content.sender.twitter_screen_name
                        message = content.details['reply']['text']
                    elif item.source == 'reddit':
                        date = content.details['comment_details']['date_created']
                        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                        #sender = content.sender.reddit_username
                        message = content.details['comment_details']['comment_body']
                    tipper = {
                        'tipper': sender,
                        'amount': '{0:.10f}'.format(content.tip_amount).rstrip('0').rstrip('.'),
                        'date': date,
                        'message': message
                    }
                    total_tips += content.tip_amount
                    tips.append(tipper)
                tips = sorted(tips, key = lambda i: i['amount'],reverse=True)
                try:
                    cont = Content.objects.get(pk=tips[0]['id'])
                except KeyError:
                    pass       

                post['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
                # Get more from recipient
                more={}
                more_content=[]
                more = Content.objects.filter(
                    post_to_spicefeed=True,
                    recipient=item.recipient,
                    parent=None
                ).exclude(parent=item.parent, pk=item.id)[:5]

                for temp in more:          
                    original_message = ''
                    chat_name = ''

                    if temp.recipient.display_username:
                        tipped_user_name = temp.recipient.get_username 
                    else:
                        tipped_user_name = temp.recipient.anon_name

                    if temp.source == 'telegram':
                        #tipped_user_name = temp.recipient.telegram_display_name
                        date = temp.details['message']['reply_to_message']['date']
                        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                        if 'text' in temp.details['message']['reply_to_message'].keys():
                            original_message = temp.details['message']['reply_to_message']['text']
                        if 'chat' in item.details['message'].keys():
                            if 'title' in item.details['message']['chat'].keys(): 
                                chat_name = item.details['message']['chat']['title']
                    elif temp.source == 'twitter':
                        #tipped_user_name = temp.recipient.twitter_screen_name
                        date = temp.details['replied_to']['created_at']
                        date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
                        if 'text' in temp.details['replied_to'].keys():
                            original_message = temp.details['replied_to']['text']
                    elif temp.source == 'reddit':
                        #tipped_user_name = temp.recipient.reddit_username
                        date = temp.details['comment_details']['date_created']
                        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
                        if 'text' in temp.details['submission_details'].keys():
                            original_message = temp.details['submission_details']['text']
                        if 'subreddit' in temp.details['submission_details'].keys():
                            chat_name = item.details['submission_details']['subreddit']
                    content = { 
                        'date': date,
                        'original_message': original_message,
                        'source': temp.source,
                        'tipped_user_name': tipped_user_name,
                        'id': temp.id,
                        'chat_name': chat_name
                    }            
                    content['original_message_mediapath'] = ''                        

                    #get total tips
                    total_tips = temp.tip_amount
                    more_contents = Content.objects.filter(parent=temp)
                    for more_item in more_contents:
                        total_tips += more_item.tip_amount

                    content['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
                    content['original_message_mediapath'] = temp.get_media_url()
                    more_content.append(content)

                response = {            
                    'post': post,
                    'first_tipper': first_tipper,            
                    'all_tips': tips,
                    'more_content': more_content
                }
            else:
                response = {'success': False, 'error': 'private_content'}
        else:
            response = {'success': False, 'error': 'private_content'}
        return JsonResponse(response)


@api_view(['GET'])
def contentpage(request,id):
    item = Content.objects.get(pk=id)   
    media_type = None    

    try:
        if item.recipient.display_username:
            user = item.recipient.get_username
        else:    
            user = item.recipient.anon_name

        if item.source == 'telegram':   
            #user = item.recipient.telegram_display_name
            date = item.details['message']['reply_to_message']['date']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            original_message = item.details['message']['reply_to_message']['text']
        elif item.source == 'twitter':
            #user = item.recipient.twitter_screen_name
            date = item.details['replied_to']['created_at']
            date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
            original_message = item.details['replied_to']['text']
        elif item.source == 'reddit':
            #user = item.recipient.reddit_username
            date = item.details['comment_details']['date_created']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            original_message = item.details['submission_details']['text']
    except KeyError:
        original_message = ''        
    if 'message' in item.details.keys():
        if 'photo' in item.details['message']['reply_to_message'].keys():
            media_type = 'photo'
        elif 'video' in item.details['message']['reply_to_message'].keys():
            media_type = 'video'
    post = {
        'id': id,
        'tipped_user_name': user,
        'original_message': original_message,
        'date': date,
        'source': item.source,
        'media_type': media_type        
    }        

    post['original_message_mediapath'] = item.get_media_url()

    date = None
    contents = Content.objects.filter(parent=item)
    post['total_tips'] = 0


    if item.sender.display_username:
        sender = item.sender.get_username
    else:    
        sender = item.sender.anon_name

    if item.source == 'telegram':
        date = item.details['message']['date']
        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
        #sender = item.sender.telegram_display_name
        message = item.details['message']['text']
    elif item.source == 'twitter':
        date = item.details['reply']['created_at']
        date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
        #sender = item.sender.twitter_screen_name
        message = item.details['reply']['text']
    elif item.source == 'reddit':
        date = item.details['comment_details']['date_created']
        date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
        #sender = item.sender.reddit_username
        message = item.details['comment_details']['comment_body']
    tips = [{
        'tipper': sender,
        'amount': '{0:.10f}'.format(item.tip_amount).rstrip('0').rstrip('.'),
        'date': date,
        'message': message

    }]
    total_tips = item.tip_amount

    for content in contents:
        sender_instance = content.sender
        if sender_instance.display_username:  
            sender = sender_instance.get_username
        else:
            sender = sender_instance.anon_name

        if item.source == 'telegram':
            date = content.details['message']['date']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            #sender = content.sender.telegram_display_name
            message = content.details['message']['text']    
        elif item.source == 'twitter':
            date = content.details['reply']['created_at']
            date = dt.datetime.strptime(date, '%a %b %d %X %z %Y').strftime('%H:%M %d/%m/%Y')
            #sender = content.sender.twitter_screen_name
            message = content.details['reply']['text']
        elif item.source == 'reddit':
            date = content.details['comment_details']['date_created']
            date = datetime.utcfromtimestamp(date).strftime('%H:%M %d/%m/%Y')
            #sender = content.sender.reddit_username
            message = content.details['comment_details']['comment_body']
        tipper = {
            'tipper': sender,
            'amount': '{0:.10f}'.format(content.tip_amount).rstrip('0').rstrip('.'),
            'date': date,
            'message': message
        }
        total_tips += content.tip_amount
        tips.append(tipper)
    tips = sorted(tips, key = lambda i: i['amount'],reverse=True)
    try:
        cont = Content.objects.get(pk=tips[0]['id'])
    except KeyError:
        pass       
    post['total_tips'] = '{0:.10f}'.format(total_tips).rstrip('0').rstrip('.')
    return render(request, 'main/index.html', post)


class UserSearchView(View):

    def get(self, request, user):
        item = user.replace('-', ' ')
        #media_only = request.GET.get('media_only', 'false')
        success = False
        response  = {}
        user = None
        user_content = []

        if item.startswith('userid'):
            user_id = item.split('userid')[-1]
            user = User.objects.get(id=user_id)
            success = True
            
        # users = User.objects.all()
        # user = None
        # user_content = []        
        # for u in users:            
        #     if u.telegram_display_name == item or u.twitter_screen_name == item or u.reddit_username == item:                
        #         user = u
        #         success = True
        #         break
        
        if success and user:  
            #user data
            details = {}

            if user.display_username:
                details['username'] = user.get_username
            else:
                details['username'] = user.anon_name

            if user.telegram_id:
                #details['username'] = user.telegram_display_name
                details['source'] = 'telegram'
            if user.twitter_id:
                #details['username'] = user.twitter_screen_name
                details['source'] = 'twitter'
            if user.reddit_id:
                #details['username'] = user.reddit_username
                details['source'] = 'reddit'

            total_received = Content.objects.filter(
                recipient=user
            ).aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0
            total_tipped = Content.objects.filter(
                sender=user
            ).aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0

            details['total_tips_received'] = total_received
            details['total_tips_sent'] = total_tipped
            details['pof'] = user.pof_display

            #received            
            try:
                received_contents = Content.objects.filter(
                    recipient=user,
                    post_to_spicefeed=True,
                    parent=None
                ).order_by('-id')                
            except Content.DoesNotExist:
                received_contents = None            

            received = []
            for content in received_contents:
                original_message = ''
                chat_name = ''
                tipper_message = ''
                sender_instance = content.sender
                if sender_instance.display_username:
                    sender_username = sender_instance.get_username
                else:
                    sender_username = sender_instance.anon_name

                if content.source == 'telegram':   
                    date = content.details['message']['date']                 
                    #sender_username = content.sender.telegram_display_name
                    tipper_message = content.details['message']['text']
                    if 'text' in content.details['message']['reply_to_message'].keys():
                        original_message = content.details['message']['reply_to_message']['text']
                    if 'chat' in content.details['message'].keys():
                        if 'title' in content.details['message']['chat'].keys(): 
                            chat_name = content.details['message']['chat']['title']
                if content.source == 'twitter':            
                    date = content.details['reply']['created_at']       
                    #sender_username = content.sender.twitter_screen_name
                    tipper_message = content.details['reply']['text']
                    if 'text' in content.details['replied_to'].keys():
                        original_message = content.details['replied_to']['text']
                if content.source == 'reddit':                   
                    date = content.details['comment_details']['date_created']
                    #sender_username = content.sender.reddit_username
                    tipper_message =content.details['comment_details']['comment_body']
                    if 'text' in content.details['submission_details'].keys():
                        original_message = content.details['submission_details']['text']
                    if 'subreddit' in content.details['submission_details'].keys():
                        chat_name = content.details['submission_details']['subreddit']

                #total = Content.objects.filter(recipient_content_id=content.recipient_content_id)
                #total_tips = 0
                #for item in total:
                #    total_tips+=item.tip_amount

                int_amount = content.tip_amount * 100000000
                temp = {
                    'created_at': content.date_created.isoformat(),
                    'permalink': content.id,
                    'service': content.source,
                    'int_amount': int_amount,
                    'string_amount': str(int_amount),                  
                    'total_tips': content.total_tips,                  
                    'tipped_user_name': details['username'],
                    'tipper_user': sender_username,
                    'tipper_message': tipper_message,
                    'tipper_message_date': date,
                    'original_message': original_message,                                           
                    'original_message_mediapath': content.get_media_url(),
                    'additional_tippers': [],
                    'pof': details['pof']
                }                
                user_content.append(temp)

            response = {
                'success': True,
                'details': details,
                'contents': user_content
            }

        else:
            response['success'] = False
            possible_user = []
            # User.objects.filter(tips_received)

            Q1 = User.objects.filter(display_username=True)
            Q1 = Q1.filter(
                Q(telegram_user_details__username__icontains=item) |
                Q(telegram_user_details__first_name__icontains=item) |
                Q(twitter_user_details__screen_name__icontains=item) |
                Q(reddit_user_details__username__icontains=item)
            )

            Q2 = User.objects.filter(display_username=False)
            Q2 = Q2.filter(
                anon_name__icontains=item
            )

            combined_qs = Q1 | Q2

            # combined_qs = User.objects.filter(
            #     Q(telegram_user_details__username__icontains=item) |
            #     Q(telegram_user_details__first_name__icontains=item) |
            #     Q(twitter_user_details__screen_name__icontains=item) |
            #     Q(reddit_user_details__username__icontains=item)
            # )

            combined_qs = combined_qs.filter(ban=False)

            if combined_qs.count() > 0:
                first10 = combined_qs.order_by('-id')[0:10]

                for user in first10:
                    if user.display_username:
                        username = user.get_username
                        # possible_user.append({'id': user.id, 'username': username, 'source': user.get_source()})
                    else:
                        username = user.anon_name
                    possible_user.append({'id': user.id, 'username': username, 'source': user.get_source})
                #possible_user = [{'id': x.id, 'username': x.anon_name, 'source': x.get_source()} for x in first10]


            response['possible_user'] = possible_user

        return JsonResponse(response)


class BalanceView(View):

    def post(self, request):
        data = json.loads(request.body)
        user_details = data.get('user', '')        
        subscriber_username = data.get('subscriber_username', '')
        token = data.get('token', '')
        slptoken = data.get('slptoken', 'spice')
        main_groups = ['telegram', 'twitter', 'reddit']
        response = {}
        proceed = False
        response['success'] = False
        try:            
            subscriber = Subscriber.objects.get(username=subscriber_username)            
            proceed = True
        except Subscriber.DoesNotExist:            
            response['error'] = 'Username does not exist'            
            return response
        slptoken_qs = SLPToken.objects.filter(name__iexact=slptoken)
        if slptoken_qs.exists():
            slptoken = slptoken_qs.first()
            if proceed and subscriber.token == token:
                user_details['app_name'] = subscriber.app_name
                if user_details['app_name'] not in main_groups:
                    user, _ = User.objects.get_or_create(
                        user_id=user_details['id']
                    )
                    user.user_details = user_details
                    user.save()
                else:
                    if user_details['app_name'] == 'telegram':
                        user = User.objects.get(telegram_id=user_details['id'])
                    elif user_details['app_name'] == 'twitter':
                        user = User.objects.get(twitter_id=user_details['id'])
                    elif user_details['app_name'] == 'reddit':
                        user = User.objects.get(reddit_id=user_details['id'])
                response['balance'] = get_balance(user.id, slptoken.token_id)
                response['success'] = True
            else:
                response['error'] = 'Invalid Subscriber token'
        else:
            response['error'] = 'Invalid SLP token'
        return JsonResponse(response)


class DepositView(View):
    def post(self, request):
        response = {}
        response['success'] = False
        if not config.DEACTIVATE_API_DEPOSIT:
            data = json.loads(request.body)
            user_details = data.get('user', '')        
            subscriber_username = data.get('subscriber_username', '')
            token = data.get('token', '')

            proceed = False

            try:            
                subscriber = Subscriber.objects.get(username=subscriber_username)            
                proceed = True
            except Subscriber.DoesNotExist:  
                response['error'] = 'Username does not exist'         
                return response

            user_details['app_name'] = subscriber.app_name
            if proceed and subscriber.token == token:
                user, _ = User.objects.get_or_create(
                    user_id=user_details['id']
                )
                user.user_details = user_details
                user.save()

                response['deposit-address'] = user.simple_ledger_address
                response['success'] = True
            else:
                response['error'] = 'Invalid token'
        else:
            response['error'] = 'This is not available.'
        return JsonResponse(response)


class WithdrawalView(View):
    def post(self, request):
        response = {}
        response['success'] = False
        if not config.DEACTIVATE_API_WITHDRAW:
            # user_details, subscriber_username, token, amount, slp_address
            data = json.loads(request.body)
            user_details = data.get('user_details', '')
            subscriber_username = data.get('subscriber_username', '')
            token = data.get('token', '')
            amount = float(data.get('amount', 0))        
            slp_address = data.get('slp_address')            

            proceed = False
            user = None

            try:
                subscriber = Subscriber.objects.get(username=subscriber_username)            
                proceed = True
            except Subscriber.DoesNotExist:  
                response['error'] = 'Username does not exist'
                return response            

            user_details['app_name'] = subscriber.app_name
            #withdrawal
            if proceed and subscriber.token == token:            
                try:
                    user = User.objects.get(user_id=user_details['id'])
                    user.user_details = user_details
                    user.save()
                except (User.DoesNotExist, TypeError):
                    pass

                if  slp_address.startswith('simpleledger') and len(slp_address) == 55:
                    proceed = True
                
                if user:
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
                        except Withdrawal.DoesNotExist:
                            pass
                        if latest_withdrawal:
                            last_withdraw_time = latest_withdrawal.date_created
                            time_now = timezone.now()
                            tdiff = time_now - last_withdraw_time
                            withdraw_time_limit = tdiff.total_seconds()
                            if withdraw_time_limit < 600:  # 1 withdrawal allowed every 10 minutes
                                withdraw_limit = True
                                response['status'] = 'You have reached your hourly withdrawal limit!'
                        if not withdraw_limit:
                            if amount >= 1000:
                                withdrawal = Withdrawal(
                                    user=user,
                                    address=slp_address,
                                    amount=amount
                                )
                                withdrawal.save()
                                withdraw_spice_tokens.delay(
                                    withdrawal.id,
                                    chat_id=None,
                                    update_id=None,
                                    bot=None
                                )
                                response['status'] = 'Your spice withdrawal request is being processed.'
                                response['success'] = True
                            else:                   
                                response['error'] = "We can’t process your withdrawal request because it is below minimum. The minimum amount allowed is 1000 SPICE."
                    else:
                        response['error'] = "You don't have enough spice to withdraw"            
                else:
                    response['error'] = 'User does not exist'                
            else:
                response['error'] = 'Invalid token'
        else:
            response['error'] = 'This is not available.'
        return JsonResponse(response)


class TipView(View):

    def post(self, request):        
        response = {}  
        if not config.DEACTIVATE_API_TIP:
            #sender, recipient, subscriber_name, token, post_details
            data = json.loads(request.body)
            subscriber_username = data.get('subscriber_username', '')
            token = data.get('token', '')
            post_details = data.get('post_details', None)
            text = data.get('text', '')
            
            sender_details = data.get('sender', '')        
            recipient_details = data.get('recipient', '')
                                    
            recipient_content_id = {
                'details': post_details
            }

            proceed = False        
            parent=None
            success = False
            response['success'] = False  
            
            #verify
            try:
                subscriber = Subscriber.objects.get(username=subscriber_username)            
                proceed = True
            except Subscriber.DoesNotExist:  
                response['error'] = 'Username does not exist'
                return JsonResponse(response)         
            
            #get users
            sender_details['app_name'] = subscriber.app_name
            sender, _ = User.objects.get_or_create(user_id=sender_details['id'])
            sender.user_details = sender_details
            sender.save()

            recipient_details['app_name'] = subscriber.app_name
            recipient, _ = User.objects.get_or_create(user_id=recipient_details['id'])
            recipient.user_details = recipient_details
            recipient.save()            
            
            #get tip amount
            env = settings.DEPLOYMENT_INSTANCE.strip(' ').lower()
            pattern_calc = TokenTipText()
            amount = pattern_calc.tip_getter(**{
                'type': 'by_reply',
                'text': text,
                'action': 'tip',
                'env': env
            })

            #process tip
            if proceed and subscriber.token == token:
                balance = get_balance(sender.id, settings.SPICE_TOKEN_ID)
                if amount <= balance and post_details:                
                    content_id_json = json.dumps(recipient_content_id)

                    if Content.objects.filter(recipient_content_id=content_id_json).exists():                    
                        content = Content.objects.filter(parent=None, recipient_content_id=content_id_json).first()
                        parent = content                

                    content = Content(
                        source='other',
                        tip_amount=amount,
                        sender=sender,
                        recipient=recipient,
                        details=post_details,
                        parent=parent,
                        recipient_content_id=content_id_json
                    )
                    content.save()

                    slptoken = SLPToken.objects.get(token_id=settings.SPICE_TOKEN_ID)
                    # Create incoming transaction
                    create_transaction(
                        recipient.id,
                        amount,
                        'Incoming',
                        slptoken.id,
                        settings.TXN_OPERATION['TIP']
                    )

                    # Create outgoing transaction
                    create_transaction(
                        sender.id,
                        amount,
                        'Outgoing',
                        slptoken.id,
                        settings.TXN_OPERATION['TIP']
                    )

                    response['success'] = True   
                    response['recipient'] = recipient.user_username
                    response['sender'] = sender.user_username
                    response['amount'] = amount
                    #"date_created": "Thu Nov 14 12:32:43 +0000 2019"
                    response['date'] = dt.datetime.strptime(post_details['date_created'], '%a %b %d %X %Y').strftime('%H:%M %d/%m/%Y')                            
                else:
                    response['error'] = 'Not enough balance to process tip'
            else:
                response['error'] = 'Invalid token'            
        else:
            response['success'] = False
            response['error'] = 'This is not available'                        
        return JsonResponse(response)


class SpiceTradeManagerView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        response = {}

        if not config.DEACTIVATE_API_TRADE:
            data = json.loads(request.body)

            user_id = data.get('user_id', None)
            message_id = data.get('message_id', None)
            group_id = data.get('group_id', None)
            amount = data.get('amount', 0)
            slp_token = data.get('slp_token', None)
            operation = data.get('operation', None)  # cancel, expire, trade (paying an order), order (placing an order)

            user_id_2 = data.get('user_id_2', None)
            slp_token_2 = data.get('slp_token_2', None)
            amount_2 = data.get('amount_2', None)
            
            if user_id and message_id and group_id and operation and slp_token:
                try:         
                    subscriber = Subscriber.objects.get(username=request.user.username)            
                except Subscriber.DoesNotExist:  
                    response['valid'] = False
                    response['reason'] = 'Trade Manager subscriber does not exist'
                    return response

                proceed = False

                if operation == 'trade':
                    if user_id_2 and amount_2 and slp_token_2:
                        proceed = True
                else:
                    proceed = True

                slp_token_qs = SLPToken.objects.filter(name__iexact=slp_token)

                if slp_token_qs.exists():
                    slp_token = slp_token_qs.first()
                    app_name = subscriber.app_name

                    if app_name == 'telegram':
                        trade_manager = User.objects.get(telegram_id=subscriber.details['user_collector_id'])
                        user = User.objects.get(telegram_id=user_id)

                        if not user.frozen:
                            with trans.atomic():
                                if operation == 'trade':
                                    slp_token_2 = SLPToken.objects.filter(name__iexact=slp_token_2).first()
                                    user_2 = User.objects.get(telegram_id=user_id_2)

                                    if get_balance(user_2.id, slp_token_2.token_id) >= amount_2:
                                        # Debit from user 2
                                        transaction_hash = f"{user_2.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token_2.name}"
                                        created, manager_thash_1 = create_transaction(
                                            user_2.id,
                                            amount_2,
                                            'Outgoing',
                                            slp_token_2.id,
                                            settings.TXN_OPERATION['TRADE'],
                                            transaction_hash=transaction_hash
                                        )
                                        # Receive the trade from user 2 to user 1
                                        transaction_hash = f"{user.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token_2.name}"
                                        created, user_thash_1 = create_transaction(
                                            user.id,
                                            amount_2, 
                                            'Incoming',
                                            slp_token_2.id,
                                            settings.TXN_OPERATION['TRADE'],
                                            transaction_hash=transaction_hash
                                        )
                                        swap_related_transactions(manager_thash_1, user_thash_1)

                                        # Debit from the trade manager for user 2
                                        transaction_hash = f"{trade_manager.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token.name}"
                                        created, manager_thash_2 = create_transaction(
                                            trade_manager.id,
                                            amount,
                                            'Outgoing',
                                            slp_token.id,
                                            settings.TXN_OPERATION['TRADE'],
                                            transaction_hash=transaction_hash
                                        )

                                        # Receive the trade from manager for user 2
                                        transaction_hash = f"{user_2.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token.name}"
                                        created, user_thash_2 = create_transaction(
                                            user_2.id,
                                            amount, 
                                            'Incoming',
                                            slp_token.id,
                                            settings.TXN_OPERATION['TRADE'],
                                            transaction_hash=transaction_hash
                                        )
                                        swap_related_transactions(manager_thash_2, user_thash_2)

                                        response['valid'] = True
                                        response['reason'] = 'Success'
                                    else:
                                        response['valid'] = False
                                        response['reason'] = f"Sorry {user_2.telegram_display_name}, you don't have enough {slp_token_2.emoji} { slp_token_2.name.upper() } {slp_token_2.emoji}"

                                else:
                                    # Checking the balance here
                                    if get_balance(user.id, slp_token.token_id) >= amount or operation == 'cancel' or operation == 'expire':
                                        if operation == 'expire' or operation == 'cancel':
                                            upper_operation = operation.upper()
                                            operation_key = f"TRADE_{upper_operation}"

                                            # Debit from the trade manager
                                            transaction_hash = f"{trade_manager.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token.name}"
                                            created, manager_thash = create_transaction(
                                                trade_manager.id,
                                                amount,
                                                'Outgoing',
                                                slp_token.id,
                                                settings.TXN_OPERATION[operation_key],
                                                transaction_hash=transaction_hash
                                            )
                                            # Refund the token back to the user
                                            transaction_hash = f"{user.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token.name}"
                                            created, user_thash = create_transaction(
                                                user.id,
                                                amount, 
                                                'Incoming',
                                                slp_token.id,
                                                settings.TXN_OPERATION[operation_key],
                                                transaction_hash=transaction_hash
                                            )
                                            swap_related_transactions(manager_thash, user_thash)

                                        elif operation == 'order':
                                            # Debit order amount from user
                                            transaction_hash = f"{user.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token.name}"
                                            created, user_thash = create_transaction(
                                                user.id,
                                                amount,
                                                'Outgoing',
                                                slp_token.id,
                                                settings.TXN_OPERATION['TRADE_ORDER'],
                                                transaction_hash=transaction_hash
                                            )
                                            # Store order amount to the trade manager
                                            transaction_hash = f"{trade_manager.telegram_id}-{operation}-{message_id}-{group_id}-{slp_token.name}"
                                            created, manager_thash = create_transaction(
                                                trade_manager.id,
                                                amount, 
                                                'Incoming',
                                                slp_token.id,
                                                settings.TXN_OPERATION['TRADE_ORDER'],
                                                transaction_hash=transaction_hash
                                            )
                                            swap_related_transactions(user_thash, manager_thash)

                                        response['valid'] = True
                                        response['reason'] = 'Success'
                                    else:
                                        response['valid'] = False
                                        response['reason'] = f"Sorry {user.telegram_display_name}, you don't have enough {slp_token.emoji} { slp_token.name.upper() } {slp_token.emoji}"
                        else:
                            message = f"Greetings {user.get_username}!\n\nYour account has been  ❄️  frozen  ❄\n"
                            message += "You are temporarily unable to do any spicebot operations at the moment."
                            response['valid'] = False
                            response['reason'] = message
            else:
                response['valid'] = False
                response['reason'] = 'Incomplete request body.'
        else:
            response['valid'] = False
            response['reason'] = '\bTrading bot\b is currently undergoing maintenance and upgrades. Sorry for the inconvenience!'
                

        return JsonResponse(response)


class PaperRockScissorManagerView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        response = {}

        if not config.DEACTIVATE_API_PRSBOT:
            data = json.loads(request.body)
            # subscriber_username = data.get('subscriber_username', '')
            # user_id = data.get('user_id')
            # token = data.get('token', '')
            slptoken = data.get('slptoken', 'spice')
            main_groups = ['telegram', 'twitter', 'reddit']
            result = data.get('result', 'lost')
            bet = float(data.get('bet', 0))
            payout = float(data.get('payout', 0))
            user_id = data.get('user_id', None)
            message_id = data.get('message_id', None)
            scenario = data.get('scenario', None)
            proceed = False
            try:
                # subscriber = Subscriber.objects.get(username=subscriber_username)            
                subscriber = Subscriber.objects.get(username=request.user.username)            
                proceed = True
            except Subscriber.DoesNotExist:  
                response['error'] = 'Username does not exist'
                return response
            slptoken_qs = SLPToken.objects.filter(name__iexact=slptoken)
            if slptoken_qs.exists():
                slptoken = slptoken_qs.first()
                if proceed and user_id and message_id and scenario:
                    app_name = subscriber.app_name
                    if app_name in main_groups:
                        if app_name == 'telegram':
                            gambler = User.objects.get(telegram_id=user_id)
                            betmanager = User.objects.filter(telegram_id=subscriber.details['user_collector_id'])
                        # elif app_name == 'twitter':
                        #     gambler = User.objects.get(twitter_id=user_id)
                        #     betmanager = User.objects.filter(twitter_id=subscriber.details['user_collector_id'])
                        # elif app_name == 'reddit':
                        #     gambler = User.objects.get(reddit_id=user_id)
                        #     betmanager = User.objects.filter(reddit_id=subscriber.details['user_collector_id'])
                        if not gambler.frozen:
                            if betmanager.exists():
                                betmanager = betmanager.first()
                                with trans.atomic():
                                    # Checking the balance here
                                    if get_balance(gambler.id, slptoken.token_id) >= bet:
                                        # Create the transaction
                                        if bet != 0:
                                            # Debit from the gambler
                                            transaction_hash = f"{gambler.telegram_id}-{message_id}-{slptoken.name}-{bet}-{scenario}-{result}-1"
                                            created, sender_thash = create_transaction(
                                                gambler.id,
                                                bet,
                                                'Outgoing',
                                                slptoken.id,
                                                settings.TXN_OPERATION['JANKEN'],
                                                transaction_hash=transaction_hash
                                            )
                                            # Credit the bet manager
                                            transaction_hash = f"{betmanager.telegram_id}-{message_id}-{slptoken.name}-{bet}-{scenario}-{result}-1"
                                            created, recipient_thash = create_transaction(
                                                betmanager.id,
                                                bet, 'Incoming',
                                                slptoken.id,
                                                settings.TXN_OPERATION['JANKEN'],
                                                transaction_hash=transaction_hash
                                            )

                                            swap_related_transactions(sender_thash, recipient_thash)
                                        # Process the winnings, if any
                                        if result == 'win' or result == 'tie':
                                            # Debit from bet manager
                                            transaction_hash = f"{betmanager.telegram_id}-{message_id}-{slptoken.name}-{bet}-{scenario}-{result}-2"
                                            created, sender_thash = create_transaction(
                                                betmanager.id,
                                                payout,
                                                'Outgoing',
                                                slptoken.id,
                                                settings.TXN_OPERATION['JANKEN'],
                                                transaction_hash=transaction_hash
                                            )
                                            # Credit the gambler
                                            transaction_hash = f"{gambler.telegram_id}-{message_id}-{slptoken.name}-{bet}-{scenario}-{result}-2"
                                            created, recipient_thash = create_transaction(
                                                gambler.id,
                                                payout,
                                                'Incoming',
                                                slptoken.id,
                                                settings.TXN_OPERATION['JANKEN'],
                                                transaction_hash=transaction_hash
                                            )

                                            swap_related_transactions(sender_thash, recipient_thash)
                                        response['valid'] = True
                                        response['reason'] = 'Success'
                                    else:
                                        response['valid'] = False
                                        response['reason'] = f"Sorry {gambler.telegram_display_name}, you don't have enough {slptoken.emoji} { slptoken.name.upper() } {slptoken.emoji}"
                        else:
                            message = f"Greetings {gambler.get_username}!\n\nYour account has been  ❄️  frozen  ❄\n"
                            message += "You are temporarily unable to do any spicebot operations at the moment."
                            response['valid'] = False
                            response['reason'] = message
            else:
                response['valid'] = False
                token_names = SLPToken.objects.values('name')
                response['reason'] = 'Invalid token. Supported tokens are:\n'
                for token_name in token_names:
                    response['reason'] += f"{token_name['name']}\n"
        else:
            response['valid'] = False
            response['reason'] = '\bPaperRockScissors bots\b are currently undergoing maintenance and upgrades. Sorry for the inconvenience!'            

        return JsonResponse(response)


class FrozenCheckView(View):
    
    def get(self, request, telegram_id):
        user = User.objects.get(telegram_id=telegram_id)

        return JsonResponse({
            'frozen': user.frozen
        })


class DiceManagerView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        response = {}

        if not config.DEACTIVATE_API_DICEBOT:
            data = json.loads(request.body)
            # subscriber_username = data.get('subscriber_username', '')
            # user_id = data.get('user_id')
            # token = data.get('token', '')
            slptoken = data.get('slptoken', 'spice')
            main_groups = ['telegram', 'twitter', 'reddit']
            result = data.get('result', 'lost')
            bet = float(data.get('bet', 0))
            payout = float(data.get('payout', 0))
            user_id = data.get('user_id', None)
            message_id = data.get('message_id', None)
            group_id = data.get('group_id', None)
            proceed = False
            try:
                subscriber = Subscriber.objects.get(username=request.user.username)            
                proceed = True
            except Subscriber.DoesNotExist:  
                response['error'] = 'Username does not exist'
                return response
            slptoken_qs = SLPToken.objects.filter(name__iexact=slptoken)
            if slptoken_qs.exists():
                slptoken = slptoken_qs.first()
                if proceed:
                    app_name = subscriber.app_name
                    if app_name in main_groups:
                        if app_name == 'telegram':
                            gambler = User.objects.get(telegram_id=user_id)
                            betmanager = User.objects.filter(telegram_id=subscriber.details['user_collector_id'])
                        # elif app_name == 'twitter':
                        #     gambler = User.objects.get(twitter_id=user_id)
                        #     betmanager = User.objects.filter(twitter_id=subscriber.details['user_collector_id'])
                        # elif app_name == 'reddit':
                        #     gambler = User.objects.get(reddit_id=user_id)
                        #     betmanager = User.objects.filter(reddit_id=subscriber.details['user_collector_id'])
                        if not gambler.frozen:
                            if betmanager.exists():
                                betmanager = betmanager.first()
                                with trans.atomic():
                                    # Checking the balance here
                                    # usr = User.objects.get(id=gambler.id)
                                    # balance = usr.transactions.last().running_balance
                                    # if balance >= bet:
                                    if get_balance(gambler.id, slptoken.token_id) >= bet:
                                        # Create the transaction
                                        # Debit from the gambler
                                        transaction_hash = f"{gambler.telegram_id}-{message_id}-{group_id}-{slptoken.name}-{bet}-{result}-1"
                                        created, sender_thash = create_transaction(
                                            gambler.id,
                                            bet,
                                            'Outgoing',
                                            slptoken.id,
                                            settings.TXN_OPERATION['WAGER'],
                                            transaction_hash=transaction_hash
                                        )
                                        # Credit the bet manager
                                        transaction_hash = f"{betmanager.telegram_id}-{message_id}-{group_id}-{slptoken.name}-{bet}-{result}-1"
                                        created, recipient_thash = create_transaction(
                                            betmanager.id,
                                            bet, 'Incoming',
                                            slptoken.id,
                                            settings.TXN_OPERATION['WAGER'],
                                            transaction_hash=transaction_hash
                                        )

                                        swap_related_transactions(sender_thash, recipient_thash)
                                        # Process the winnings, if any
                                        if result == 'win':
                                            # Debit from bet manager
                                            transaction_hash = f"{betmanager.telegram_id}-{message_id}-{group_id}-{slptoken.name}-{bet}-{result}-2"
                                            created, sender_thash = create_transaction(
                                                betmanager.id,
                                                payout,
                                                'Outgoing',
                                                slptoken.id,
                                                settings.TXN_OPERATION['WAGER'],
                                                transaction_hash=transaction_hash
                                            )
                                            # Credit the gambler
                                            transaction_hash = f"{gambler.telegram_id}-{message_id}-{group_id}-{slptoken.name}-{bet}-{result}-2"
                                            created, recipient_thash = create_transaction(
                                                gambler.id,
                                                payout,
                                                'Incoming',
                                                slptoken.id,
                                                settings.TXN_OPERATION['WAGER'],
                                                transaction_hash=transaction_hash
                                            )

                                            swap_related_transactions(sender_thash, recipient_thash)
                                        response['emoji'] = slptoken.emoji
                                        response['valid'] = True
                                        response['reason'] = 'Success'
                                    else:
                                        response['valid'] = False
                                        response['reason'] = f"Sorry {gambler.telegram_display_name}, you don't have enough {slptoken.emoji} { slptoken.name.upper() } {slptoken.emoji}"
                        else:
                            message = f"Greetings {gambler.get_username}!\n\nYour account has been  ❄️  frozen  ❄\n"
                            message += "You are temporarily unable to do any spicebot operations at the moment."
                            response['valid'] = False
                            response['reason'] = message
            else:
                response['valid'] = False
                token_names = SLPToken.objects.values('name')
                response['reason'] = 'Invalid token. Supported tokens are:\n'
                for token_name in token_names:
                    if token_name == 'BCH':
                        response['reason'] += "SAT (Satoshis are used for BCH bets)\n"
                    else:
                        response['reason'] += f"{token_name['name']}\n"
        else:
            response['valid'] = False
            response['reason'] = '\bWager bots\b are currently undergoing maintenance and upgrades. Sorry for the inconvenience!'


        return JsonResponse(response)


class SlpNotifyView(View):

    def post(self, request):
        response = {'success': False}
        txid = request.POST.get('txid', None)
        token = request.POST.get('token', None)
        token_id = request.POST.get('token_id', None)
        amount = request.POST.get('amount', None)
        source = request.POST.get('source', None)
        address = request.POST.get('address', None)
        spent_index = request.POST.get('index', 0)
        block = request.POST.get('block', None)

        # Get token_id
        token = token or token_id
        if token:
            token = token.split('/')[-1]

        if txid and token and amount and source and address:
            if address.startswith('bitcoincash:'):
                qs = SLPToken.objects.filter(name='BCH')
            else:
                qs = SLPToken.objects.filter(token_id=token)
            if qs.exists():
                token = qs.first()
                if float(amount) < token.min_deposit:
                    response['success'] = True
                    return JsonResponse(response)

                obj, created = deposit_initial_save(**{
                    'amt': amount,
                    'address': address,
                    'txn_id': txid,
                    'token_id': token.token_id,
                    'spent_index': spent_index
                    }
                )
                if created:
                    deposit_analyzer(**{
                        'addr': address,
                        'amt' : float(amount),
                        'txn_id': txid,
                        'token_id': token.token_id,
                        'source': source,
                        'block': block
                    }) 
                response['success'] = True
        return JsonResponse(response)


class TransferView(View):
    def post(self, request):
        response = {}
        response['success'] = False
        if not config.DEACTIVATE_API_TRANSFER:
            data = json.loads(request.body)
            subscriber_username = data.get('subscriber_username', '')
            token = data.get('token', '')

            source = data.get('source', '')
            user_details = data.get('user', '')
            amount = float(data.get('amount', 0))
            recipient_username = data.get('recipient_username', '')

            recipient = None
            sender = None
            proceed = False

            try:
                subscriber = Subscriber.objects.get(username=subscriber_username)            
                proceed = True
            except Subscriber.DoesNotExist:  
                response['error'] = 'Username does not exist'
                return response

            user_details['app_name'] = subscriber.app_name
            try:            
                sender = User.objects.get(user_id=user_details['id'])
                sender.user_details = user_details
                sender.save()
            except User.DoesNotExist:
                pass

            if proceed and subscriber.token == token:
                if sender:
                    if source == 'telegram':
                        recipient = User.objects.filter(telegram_user_details__username=recipient_username)
                    elif source == 'twitter':
                        recipient = User.objects.filter(twitter_user_details__screen_name=recipient_username)
                    elif source == 'reddit':
                        recipient = User.objects.filter(reddit_user_details__username=recipient_username)

                    if recipient.exists():
                        recipient = recipient.first()
                        response['success'] =True
                        response['status'] = transfer_spice_to_another_acct(sender.id, recipient.id, amount)
                    else:
                        response['error'] = 'Oops! The account you want to transfer to does not exist! Try another username.'                    
                else:
                    response['error'] = 'User does not exist'
            else:
                response['error'] = 'Invalid token'
        else:
            response['error'] = 'This is not available.'

        return JsonResponse(response)


class TelegramProfilePhoto(View):

    def post(self, request):
        data = json.loads(request.body)
        subscriber_username = data.get('subscriber_username', '')
        token = data.get('token', '')

        response = {'success': False}
        proceed = False
        try:
            subscriber = Subscriber.objects.get(username=subscriber_username)            
            proceed = True
        except Subscriber.DoesNotExist:  
            response['error'] = 'Subscriber username does not exist'
            return JsonResponse(response)

        if proceed and subscriber.token == token:
            user_id = data.get('user_id', '')
            base_url = 'https://api.telegram.org/bot' + settings.TELEGRAM_BOT_TOKEN
            photos_url = base_url + '/getUserProfilePhotos?user_id=' + user_id + '&offset=1&limit=1'
            resp = requests.get(photos_url)
            if resp.status_code == 200:
                photos = resp.json()['result']['photos']
                if photos:
                    file_id = resp.json()['result']['photos'][0][0]['file_id']
                    file_url = base_url + '/getFile?file_id=' + file_id
                    resp = requests.get(file_url)
                    if resp.status_code == 200:
                        file_path = resp.json()['result']['file_path']
                        photo_url = 'https://api.telegram.org/file/bot' + settings.TELEGRAM_BOT_TOKEN
                        photo_url += '/' + file_path
                        resp = requests.get(photo_url)
                        if resp.status_code == 200:
                            response['image_type'] = file_path.split('.')[-1]
                            response['image'] = base64.b64encode(resp.content).decode()
                            response['success'] = True
                        else:
                            response['error'] = '3: Telegram API request error %s' % resp.status_code
                    else:
                        response['error'] = '2: Telegram API request error %s' % resp.status_code
                else:
                    response['success'] = True
                    response['image'] = None
            else:
                response['error'] = '1: Telegram API request error %s' % resp.status_code
        else:
            response['error'] = 'Invalid token'

        return JsonResponse(response)


class SLPTokensView(View):
    def get(self, request):
        response = {}
        slp_tokens = SLPToken.objects.all()

        for token in slp_tokens:
            response[token.name] = {}
            response[token.name]['emoji'] = token.emoji
            response[token.name]['color'] = token.color
        
        return JsonResponse(response)


class MetricsView(View):
    def get(self, request):
        response = {}
        if not config.DEACTIVATE_API_METRICS:
            qs_metrics = Metric.objects.order_by('date_recorded')

            if qs_metrics.exists():
                metric = qs_metrics.first()
                fields = list(Metric._meta.get_fields())
                fields.remove(fields[0])
                fields.remove(fields[-1])

                count = 0

                while count < len(fields):
                    index = fields[count].name
                    response[index] = {}

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

                    for sub_field in sub_fields:
                        if (sub_field == 'total_new_users' 
                        or sub_field == 'total_new_groups'
                        or sub_field == 'top_ten_active_groups'
                        ):
                            latest_metric = qs_metrics.last()

                            if sub_field == 'total_new_users':
                                val = latest_metric.user_metrics[sub_field]
                            elif sub_field == 'total_new_groups':
                                val = latest_metric.group_metrics[sub_field]
                            elif sub_field == 'top_ten_active_groups':
                                val = latest_metric.group_metrics[sub_field]
                            
                            response[index][sub_field] = val
                        else:
                            query_field_str = f'{index}__{sub_field}'
                            response[index][sub_field] = list(qs_metrics.annotate(
                                SPICE=KeyTextTransform(sub_field, index), 
                                date=F('date_recorded')
                            ).values(
                                'SPICE',
                                'date'
                            ))

                        # print(response[index][sub_field], '\n')
                        # for content in response[index][sub_field]:
                        #     content['SPICE'] = content[query_field_str]
                        #     del content[query_field_str]
                    count += 1
        else:
            response['error'] = 'This is not available.'

        return JsonResponse(response)                    
                                

class GroupProfilePicView(View):
    def post(self, request):
        logger.info('\n\nstarting....\n\n')
        data = json.loads(request.body)
        chat_id = data.get('chat_id', '')
        data = {
            "chat_id": chat_id
        }

        #Check if url exist in db
        group = TelegramGroup.objects.filter(chat_id=chat_id).first()
        url = ''

        #check if file_id changed
        url = 'https://api.telegram.org/'
        response = requests.post(
            f"{url}bot{settings.TELEGRAM_BOT_TOKEN}/getChat", data=data
        )
        resp = response.json()['result']
        file_id = resp['photo']['small_file_id']

        status = 'success'
        proceed=True

        logger.info('\n\nchecking group....\n\n')
        if group and group.profile_pic_file_id == file_id:
            url = group.profile_pic_url
            proceed = False
            logger.info('\n\nhere\n\n')

        if proceed:
            logger.info('\n\nproceed....\n\n')

            try:
                #get photo link
                response = requests.get('https://api.telegram.org/bot' + settings.TELEGRAM_BOT_TOKEN + '/getFile?file_id=' + file_id)
                file_path = response.json()['result']['file_path']
                download_url = 'https://api.telegram.org/file/bot' + settings.TELEGRAM_BOT_TOKEN + '/' + file_path
                logger.info(f'\n\ndownload_url: {download_url}\n\n')

            
                # Download photo
                logger.info(f"\n\ndownloading....\n\n")
                r = requests.get(download_url)
                temp_name = '/tmp/' + file_id + '-temp' + '.jpg'
                filename = '/tmp/' + file_id + "__" + timezone.now().strftime('%d%m%Y%H%M') +'.jpg'
                with open(temp_name, 'wb') as f:
                    f.write(r.content)
                im = Image.open(temp_name).convert("RGB")
                im.save(filename,"jpeg")
                os.remove(temp_name)
                fname = file_id + "__" + timezone.now().strftime('%d%m%Y%H%M') + '.jpg'
                logger.info(f"\n\nfname:{fname}\n\n")
        
                # Upload media file to AWS
                aws = AWS()
                aws_url = aws.upload(fname)

                # After uploading delete the file
                logger.info(f"\n\ndeleting....\n\n")
                os.remove('/tmp/' + fname)
                url=''
                if group:
                    group.profile_pic_url = url
                    group.aws_profile_pic_url = aws_url
                    group.profile_pic_file_id = file_id
                    group.save()
            except:
                logger.info('\n\nfailed\n\n')
                status = 'failure'
                url=''
    
        resp = {
            "image_url": url,
            "status": status
        }
        return JsonResponse(resp)
