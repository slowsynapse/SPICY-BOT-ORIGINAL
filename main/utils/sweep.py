from pywallet import wallet
from decouple import config as env
from base58 import b58decode_check, b58encode_check
from subprocess import Popen, PIPE
from main.models import Deposit
from main.models import SLPToken
from django.utils import timezone
from main.utils.converter import convert_bch_to_slp_address
import cashaddress
from bitcash import PrivateKey
import base64


def decipher(value):
    return base64.b64decode(value.encode()).decode()


class SweepDeposits(object):

    def __init__(self, seed):
        self.master_wallet = wallet.Wallet.from_master_secret(seed, network='BCH')

    def _convert_to_slp(self, bitcoincash_address):
        simple_ledger_address = convert_bch_to_slp_address(bitcoincash_address)
        return simple_ledger_address

    def get_wallet(self, user_id):
        child_wallet = self.master_wallet.get_child(user_id)
        bitpay_addr = child_wallet.to_address()
        legacy = b58encode_check(b'\x00' + b58decode_check(bitpay_addr)[1:])
        addr_obj = cashaddress.convert.Address.from_string(legacy) 
        cash_addr = addr_obj.cash_address()
        private_key = child_wallet.export_to_wif()
        details = {
            'private_key': private_key,
            'cash_address': cash_addr,
            'slp_address': self._convert_to_slp(cash_addr)
        }
        return details

    def _sweep_address(self, config):
        user_wif = config['private_key']
        pk = PrivateKey(user_wif)
        if config['token_name'].lower() == 'bch':
            args = [
                decipher(env('SPICE_FUNDING_CASH_ADDR')),
                float(config['total_amount']),
                pk.address,
                user_wif
            ]
            cmd = 'node /code/spiceslp/send-bch.js {0} {1} {2} {3}'.format(*args)
            print(cmd)
        else:
            slp_address = convert_bch_to_slp_address(pk.address)
            args = [
                decipher(env('SPICE_FUNDING_SLP_ADDR')),
                float(config['total_amount']),
                config['token_id'],
                slp_address,
                user_wif
            ]
            cmd = 'node /code/spiceslp/send-tokens.js {0} {1} {2} {3} {4}'.format(*args)
            print(cmd)
        p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE) 
        stdout, _ = p.communicate()
        result = stdout.decode('utf8')
        status = result.splitlines()[-1].strip()
        tx_details = ''
        if status == 'success':
            tx_details = result.splitlines()[-2].strip()
        else:
            print(result)
        return status, tx_details

    def get_unswept_deposits(self, later_than='2019-07-28 18:03:21.438790+00:00'):
        deposits = Deposit.objects.filter(
            date_swept__isnull=True,
        )
        if later_than:
            deposits = deposits.filter(
                date_created__gt=later_than
            )
        unique_addresses = deposits.values_list(
            'user__bitcoincash_address',
            flat=True
        ).distinct()
        tokens = SLPToken.objects.all()
        token_deposits = {}
        for token in tokens:
            details = {}
            for deposit in deposits.filter(slp_token=token):
                cash_addr = deposit.user.bitcoincash_address
                if cash_addr in details.keys():
                    details[cash_addr]['deposits'].append(deposit.id)
                    details[cash_addr]['amounts'].append(round(deposit.amount, 8))
                else:
                    details[cash_addr] = {}
                    details[cash_addr]['deposits'] = [deposit.id]
                    details[cash_addr]['amounts'] = [round(deposit.amount, 8)]
                details[cash_addr]['user_id'] = deposit.user.id
                details[cash_addr]['simple_ledger_address'] = deposit.user.simple_ledger_address
            token_deposits[token.token_id] = details
        return token_deposits

    def execute(self, deposits=None):
        if not deposits:
            deposits = self.get_unswept_deposits()
        for token_id in deposits:
            count = 0
            token = SLPToken.objects.get(token_id=token_id)
            print('\n######## Dealing with %s deposits ########' % token.name)
            token_deposits = deposits[token_id]
            for address in token_deposits:
                count += 1
                details = token_deposits[address]
                user_id = details['user_id']
                print('\n%s of %s: Dealing with deposits from User ID %s' % (count, len(token_deposits), user_id))
                total_deposits = sum(details['amounts'])
                wallet = self.get_wallet(details['user_id'])
                config = {
                    'total_amount': round(total_deposits, 8),
                    'slp_address': details['simple_ledger_address'],
                    'token_id': token_id,
                    'token_name': token.name,
                    'private_key': wallet['private_key']
                }
                status, tx_details = self._sweep_address(config)
                if status == 'success':
                    print(tx_details)
                    user_deposits = Deposit.objects.filter(
                        id__in=details['deposits']
                    ).update(
                        date_swept=timezone.now()
                    )
        print('Completed!')
