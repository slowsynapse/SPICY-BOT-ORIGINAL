from bridge.utils.smartbch import SlpBridge
from celery import shared_task
from django.conf import settings
from bridge.models import (
    SwapRequest,
    Fulfillment
)
from django.utils import timezone
from main.tasks import send_telegram_message
import logging

logger = logging.getLogger(__name__)


@shared_task(queue='bridge')
def fulfill_swap_request(request_id):
    swap_request = SwapRequest.objects.get(id=request_id)
    token = swap_request.token

    # Initialize the contract
    slp_bridge = SlpBridge(
        contract_address=token.sep20_contract,
        default_account_address=token.sep20_source_address
    )

    if not swap_request.date_fulfilled:
        logger.info(f"Executing swap request #{request_id}...")
        # Compute the amount based on the token's set SLP-to-SEP20 ratio
        amount =  float(swap_request.amount) / token.slp_to_sep20_ratio
        amount = round(amount, token.sep20_decimals)
        txn_hash = slp_bridge.transfer(
            swap_request.to_address,
            float(amount),
            settings.BRIDGE_SEP20_PRIVATE_KEYS[token.name.lower()],
            decimals=token.sep20_decimals
        )
        if txn_hash:
            fulfillment = Fulfillment(
                amount=amount,
                swap_request=swap_request,
                send_transaction_hash=txn_hash
            )
            fulfillment.save()
            
            swap_request.date_fulfilled = timezone.now()
            swap_request.save()

            explorer_link = f"https://www.smartscan.cash/transaction/{txn_hash}"
            message = f"{amount} {swap_request.token.name.upper()} has been sent to {swap_request.to_address}:\n{explorer_link}"
            send_telegram_message.delay(message, swap_request.telegram_chat_id, None)
