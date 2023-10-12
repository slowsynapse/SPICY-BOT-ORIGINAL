from django.utils import timezone
from celery import shared_task
from datetime import datetime, timedelta
from django.conf import settings
import json, requests

def telegramgroup_rate_handler(group_id, tzone, msgcount=20, seconds=60):
    storage = settings.REDISKV
    keyword = f'{group_id}*'
    keys = storage.keys(keyword)
    current_dt = datetime.strptime(
        tzone.strftime('%D %T'),
        '%m/%d/%y %H:%M:%S'
    )
    if len(keys) == 0:
        key = f'{group_id}|=|{current_dt}'
        storage.set(key, 1)
        return False
    else:
        key = keys[0]

        # Analyze the key
        last_timestamp = key.decode().split('|=|')[-1]

        last_dt = datetime.strptime(last_timestamp, '%Y-%m-%d %H:%M:%S')
        diff = current_dt - last_dt
        if diff.total_seconds() > seconds:
            storage.delete(key)
            return True

        value = storage.get(key).decode()
        count = int(value)
        if count == msgcount:
            return True
        else:
            count += 1
            storage.set(key, count)
            return False 


@shared_task(queue='sphere_response')
def sphere_challenge_respond(group_id, message_id, message, reply_markup=None):
    hold = True
    while hold:
        hold = telegramgroup_rate_handler(
            group_id=group_id,
            tzone = timezone.now()
        )
    data = {
        "chat_id": group_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_to_message_id": message_id
    }

    if not message_id:
        data.pop('reply_to_message_id')
    if reply_markup:
        data['reply_markup'] =json.dumps(reply_markup, separators=(',', ':'))
             

    bot_url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{bot_url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
    )
    return response.status_code