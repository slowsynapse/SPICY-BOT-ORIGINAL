import requests
from main.models import Content, Media, TelegramGroup, User, SLPToken
import logging
logger = logging.getLogger(__name__)
from rest_hooks.models import Hook
import json
from datetime import datetime
from django.core.serializers.json import DjangoJSONEncoder
import time

class Transferrable(object):

    def __init__(self):
        self.contents = Content.objects.filter(transferred=False)
        # self.media = Media.objects.filter(transferred=False)
        self.media = Media.objects.all()
        self.telegram_groups = TelegramGroup.objects.filter(transferred=False)
        self.users = User.objects.filter(transferred=False)
        self.sep = '======='

    def send(self, *args, **kwargs):
        target = kwargs.get('target', '')
        payload = kwargs.get('payload', {})
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url=target,data=json.dumps(payload,cls=DjangoJSONEncoder),headers=headers)
        if response.status_code == 200:
            return True
        return False

    def process_users(self):
        event = 'user.created'
        hook = Hook.objects.get(event=event)
        print(f'{self.sep} Replicating Users to Spicefeedhub {self.sep}')
        target = hook.target
        for user in self.users:
            payload = {
                'hook': hook.dict(),
                'data': {
                    'reddit_id': user.reddit_id,
                    'reddit_user_details': user.reddit_user_details,
                    'twitter_id': user.twitter_id,
                    'twitter_user_details': user.twitter_user_details,
                    'telegram_id': user.telegram_id,
                    'telegram_user_details': user.telegram_user_details,
                    'user_id': user.user_id,
                    'user_details': user.user_details,
                    'post_to_spicefeed': user.post_to_spicefeed,
                    'last_activity': user.last_activity,
                    'pof': user.pof,
                    'account': user.account,
                    'ban': user.ban,
                    'anon_name': user.anon_name,
                    'display_username': user.display_username
                }
            }
            created = self.send(**{'payload': payload, 'target': target})
            if created:
                print(f'USERS | ID : {user.id} | {user.display_username}')
                User.objects.filter(id=user.id).update(transferred=True)
            else:
                print(f'FAILED - USERS | ID : {user.id} | {user.display_username}')

    def process_contents(self):
        print(f'{self.sep} Replicating Contents to Spicefeedhub {self.sep}')
        event = 'content.created'
        hook = Hook.objects.get(event=event)
        target = hook.target
        for content in self.contents:
            if content.parent:
                parent_id = content.parent.id
            else:
                parent_id = None
            if content.slp_token:
                slp = {
                    'name': content.slp_token.name,
                    'token_id': content.slp_token.token_id,
                    'emoji': content.slp_token.emoji
                }
            else:
                # This is for Contents with no SLP Token
                slptoken = SLPToken.objects.first()
                slp = {
                    'name': slptoken.name,
                    'token_id': slptoken.token_id,
                    'emoji': slptoken.emoji
                }
            payload = {
                'hook': hook.dict(),
                'data': {
                    'content_id': content.id,
                    'source': content.source,
                    'tip_amount': content.tip_amount,
                    'sender': content.sender.get_user_id,
                    'recipient': content.recipient.get_user_id,
                    'details': content.details,
                    'post_to_spicefeed': content.post_to_spicefeed,
                    'date_created': content.date_created,
                    'last_activity': content.last_activity,
                    'recipient_content_id': content.recipient_content_id,
                    'total_tips': content.total_tips,
                    'parentid': parent_id,
                    'slp': slp
                }
            }
            if self.send(**{'payload': payload, 'target': target}):
                Content.objects.filter(id=content.id).update(transferred=True)
                print(f'CONTENTS | ID : {content.id} | SOURCE : {content.source}')

    def process_media(self):
        print(f'{self.sep} Replicating Media to Spicefeedhub {self.sep}')
        event = 'media.created'
        hook = Hook.objects.get(event=event)
        target = hook.target
        for media in self.media:
            if media.content:
                content = media.content.recipient_content_id
            else:
                content = None
            payload = {
                'hook': hook.dict(),
                'data': {
                    'recipient_content_id': content, 
                    'file_id': media.file_id,
                    'url': media.aws_url                
                }
            }
            if self.send(**{'payload': payload, 'target': target}):
                Media.objects.filter(id=media.id).update(transferred=True)
                logger.info(f'MEDIA | ID : {media.id} | SOURCE : {media.url}')

    def process_telegram_group(self):
        logger.info(f'{self.sep} Replicating Telegram Groups to Spicefeedhub {self.sep}')
        event = 'telegram_group.created'
        hook = Hook.objects.get(event=event)
        target = hook.target
        for group in self.telegram_groups:
            payload = {
                'hook': hook.dict(),
                'data': {
                    'chat_id': group.chat_id,
                    'chat_type': group.chat_type,
                    'title': group.title,                                
                    'post_to_spicefeed': group.post_to_spicefeed,
                    'users': group.get_user_list()
                }
            }
            if self.send(**{'payload': payload, 'target': target}):
                TelegramGroup.objects.filter(id=group.id).update(transferred=True)
                logger.info(f'TELEGRAMGROUP | ID : {group.id}')


    def run(self):
        self.process_users()
        self.process_telegram_group()
        self.process_contents()      
        self.process_media()