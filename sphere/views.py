from django.shortcuts import render
from django.views import View
from django.http import JsonResponse
from sphere.models import Challenge
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
if 'sphere' in settings.INSTALLED_APPS : from sphere.utils.game import SphereGame
import logging
import json

logger = logging.getLogger(__name__)

class BotView(View):

    def post(self, request):
        data = json.loads(request.body)
        logger.error('--- MESSAGE RECEIVED ---')
        proceed = True


        if 'callback_query' in data.keys():      
            callback = data['callback_query']
            group_id= callback['message']['chat']['id']
            root_msg_id = None

            if 'reply_to_message' in callback['message'].keys():
                root_msg_id = callback['message']['reply_to_message']['message_id']

            from_id = str(callback['from']['id'])
            proceed = False

            #get challenge
            challenge = Challenge.objects.using('sphere_db').filter(group_id=group_id, message_id=root_msg_id).first()

            if challenge:
                
                if challenge.challenger_id == from_id:
                    proceed = True
                elif challenge.contender_username == callback['from']['username']:
                    proceed = True

                if proceed:
                    key = f"{data['callback_query']['message']['message_id']}{group_id}"
                    key = f"callback-{key}" 

                    if key.encode() not in settings.REDISKV.keys():
                        logger.error('Saving')
                        settings.REDISKV.set(key, request.body)
                    else:
                        logger.error('Aborted')
                        return JsonResponse({"ok": "POST request aborted"})


        game = SphereGame()
        game.start(data)
        
        return JsonResponse({"ok": "POST request processed"})
