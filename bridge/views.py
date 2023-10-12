from bridge.models import (
    Token,
    SwapRequest
)
from bridge.tasks import fulfill_swap_request
from django.conf import settings
from django.http import JsonResponse
from django.views import View
import logging

logger = logging.getLogger(__name__)

class WatchtowerWebhookView(View):

    def post(self, request):
        response = {'success': False}
        txid = request.POST.get('txid', None)
        token = request.POST.get('token', None)
        amount = request.POST.get('amount', None)
        source = request.POST.get('source', None)
        address = request.POST.get('address', None)
        spent_index = request.POST.get('index', 0)
        block = request.POST.get('block', None)
        logger.info(f"Deposit to a bridge address detected: {amount} of token ID {token}.")
        if txid and token and amount and source and address:
            token_check = Token.objects.filter(
                slp_token_id=token
            )
            if token_check.exists():
                token = token_check.first()
                swap_request_check = SwapRequest.objects.filter(
                    token=token,
                    from_address=address
                )
                if swap_request_check.exists():
                    swap_request = swap_request_check.first()
                    # Proceed only if deposited amount is greater or equal to the swap request amount
                    rounded_amount = int(round(float(amount)))
                    if (rounded_amount - int(swap_request.amount)) >= 0:
                        swap_request.amount = rounded_amount
                        swap_request.receive_transaction_hash = txid
                        swap_request.save()

                        fulfill_swap_request.delay(swap_request.id)
                response['success'] = True
        return JsonResponse(response)
