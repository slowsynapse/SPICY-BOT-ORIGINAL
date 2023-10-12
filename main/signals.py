from django.db.models.signals import post_save, pre_save
from django.db.models import Sum
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
from main.tasks import download_upload_file
from main.models import (
    User, 
    Transaction,
    Deposit,
    Content,
    Media,
    BitcoinBlockHeight,
    SLPToken,
    Mute,
)
from main.utils.account import get_balance
from main.utils.wallets import generate_cash_address
from subprocess import Popen, PIPE
from django.contrib.auth.models import User as djUser
from django.db import transaction as trans
from random_username.generate import generate_username
from main.utils.converter import convert_bch_to_slp_address
# from constance.signals import config_updated

import logging, requests

logger = logging.getLogger(__name__)

def create_addresses(user):
    bitcoincash_address = generate_cash_address(user.id)
    simple_ledger_address = convert_bch_to_slp_address(bitcoincash_address)
    user.bitcoincash_address = bitcoincash_address
    user.simple_ledger_address = simple_ledger_address
    user.slpnotified = True
    user.save()


def subscribe_to_watchtower(user):
    simple_ledger_address = user.simple_ledger_address
    bitcoincash_address = user.bitcoincash_address
    for tokenaddress in [simple_ledger_address, bitcoincash_address]:
        data = {
            'project_id': settings.WATCHTOWER_PROJECT_ID,
            'address': tokenaddress,
            'webhook_url': f"{settings.DOMAIN}/slpnotify/"
        }
        url = settings.WATCHTOWER_SUBSCRIPTION_ENDPOINT
        resp = requests.post(url, json=data)
        if resp.status_code in [500, 502]:
            raise Exception('Watchtower server error or timeout')
        else:
            success = resp.json()['success']
            if success:
                user.subscribed_to_watchtower = True
                user.save()
            else:
                if resp.json()['error'] == 'subscription_already_exists':
                    user.subscribed_to_watchtower = True
                    user.save()


@receiver(pre_save, sender=User)
def user_pre_save(sender, instance=None, **kwargs):
    if instance.id and not instance.subscribed_to_watchtower:
        previous = User.objects.get(id=instance.id)
        send_subscription = False
        if previous.last_private_message is None:
            if instance.last_private_message:
                send_subscription = True
        else:
            if instance.last_private_message > previous.last_private_message:
                send_subscription = True
        if send_subscription:
            subscribe_to_watchtower(instance)


@receiver(post_save, sender=User)
def user_post_save(sender, instance=None, created=False, **kwargs):
    if created and not instance.simple_ledger_address:
        create_addresses(instance)
        anon_name = generate_username(1)[0]
        unique_anon_name = f"{anon_name}{instance.id}"
        User.objects.filter(id=instance.id).update(anon_name=unique_anon_name)
    if instance.ban:
        contents = Content.objects.filter(
            recipient=instance,
            post_to_spicefeed=True
        )
        contents.update(post_to_spicefeed=False)


@receiver(post_save, sender=Content)
def content_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        data = instance.details
        # if instance.source == 'telegram':

        #     if 'photo' in data['message']['reply_to_message'].keys():
        #         file_type = 'photo'
        #         file_id = data['message']['reply_to_message']['photo'][-1]['file_id']
        #         download_upload_file.delay(file_id, file_type, instance.id)

        #     elif 'sticker' in data['message']['reply_to_message'].keys():
        #         file_type = 'sticker'
        #         file_id = data['message']['reply_to_message']['sticker']['file_id']
        #         download_upload_file.delay(file_id, file_type, instance.id)

        #     elif 'animation' in data['message']['reply_to_message'].keys():
        #         file_type = 'animation'
        #         file_id = data['message']['reply_to_message']['animation']['file_id']
        #         download_upload_file.delay(file_id, file_type, instance.id)

        #     elif 'video' in data['message']['reply_to_message'].keys():
        #         file_type = 'animation'
        #         file_id = data['message']['reply_to_message']['video']['file_id']
        #         download_upload_file.delay(file_id, file_type, instance.id)

        #     elif 'video_note' in data['message']['reply_to_message'].keys():
        #         file_type = 'animation'
        #         file_id = data['message']['reply_to_message']['video_note']['file_id']
        #         download_upload_file.delay(file_id, file_type, instance.id)

        #     elif 'voice' in data['message']['reply_to_message'].keys():
        #         file_type = 'audio'
        #         file_id = data['message']['reply_to_message']['voice']['file_id']
        #         download_upload_file.delay(file_id, file_type, instance.id)

        #     elif 'document' in data['message']['reply_to_message'].keys():
        #         file_type = data['message']['reply_to_message']['document']['mime_type']
        #         if 'image' in file_type:
        #             file_type = 'photo'
        #         file_id = data['message']['reply_to_message']['document']['file_id']
        #         download_upload_file.delay(file_id, file_type, instance.id)

        # Initially equate tip amount and total_tips
        instance.total_tips = instance.tip_amount
        instance.save()


        # Initially equate tip amount and total_tips

        content_qs = Content.objects.filter(id=instance.id)
        content_qs.update(total_tips=instance.tip_amount)

        if instance.parent:
            # Update parent's total_tips and last activity
            total_tips = instance.parent.tip_amount
            children_tips = instance.parent.children.all().aggregate(Sum('tip_amount'))['tip_amount__sum'] or 0
            total_tips += children_tips
            last_activity=timezone.now()
            content_qs = Content.objects.filter(id=instance.parent.id)
            content_qs.update(
                total_tips=total_tips,
                last_activity=last_activity
            )


@receiver(post_save, sender=SLPToken)
def slp_token_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        instance.name = instance.name.upper()
        instance.save()

@receiver(post_save, sender=Mute)
def mute_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        instance.remaining_unmute_fee = instance.unmute_fee
        instance.save()
