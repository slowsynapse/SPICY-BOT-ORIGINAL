from base58 import b58decode_check, b58encode_check
from pywallet.utils import Wallet
from django.conf import settings
import cashaddress


def generate_cash_address(user_id):
    wallet_obj = Wallet.deserialize(
        settings.PARENT_XPUBKEY,
        network='BCH'
    )
    child_wallet = wallet_obj.get_child(user_id)
    bitpay_addr = child_wallet.to_address()
    legacy = b58encode_check(b'\x00' + b58decode_check(bitpay_addr)[1:])
    addr_obj = cashaddress.convert.Address.from_string(legacy) 
    cash_addr = addr_obj.cash_address()
    return cash_addr
