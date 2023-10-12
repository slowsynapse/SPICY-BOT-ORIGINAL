from django.conf import settings
from main.utils.converter import convert_bch_to_slp_address
from base58 import b58decode_check, b58encode_check
from pywallet import wallet
import cashaddress
import requests


def generate_slp_address(swap_request_id, xpub=None, wallet_hash=None):
    child = wallet.create_address(network='SLP', xpub=xpub, child=swap_request_id)
    bitpay_addr = child['address']
    legacy_addr = b58encode_check(b'\x00' + b58decode_check(bitpay_addr)[1:])
    addr_obj = cashaddress.convert.Address.from_string(legacy_addr) 
    cash_addr = addr_obj.cash_address()
    slp_addr = convert_bch_to_slp_address(cash_addr)
    data = {
        'project_id': settings.WATCHTOWER_PROJECT_ID,
        'wallet_hash': wallet_hash,
        'wallet_index': swap_request_id,
        'address': slp_addr,
        'webhook_url': f"{settings.DOMAIN}/bridge/watchtower/"
    }
    url = settings.WATCHTOWER_SUBSCRIPTION_ENDPOINT
    resp = requests.post(url, json=data)
    if resp.status_code in [200, 409]:
        return slp_addr
    else:
        return
