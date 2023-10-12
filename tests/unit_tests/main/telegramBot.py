import mock
from pytest_mock import mocker
import pytest
from mock import patch

from main.utils import telegram
from main import tasks
from main.models import User, Deposit
from django.conf import settings
import json

class TelegramBotTest(object):


    def __init__(self, requests_mock, monkeypatch):
        self.requests_mock = requests_mock
        self.monkeypatch = monkeypatch
        self.telegram_input = {
            "message":  {
                "chat": {
                    "id": 7,
                    "type": "private",
                    "title": "SpiceBotTest2Group",
                    "all_members_are_administrators": True
                },
                "date": 1560759314,
                "from": {
                    "id": 123,
                    "is_bot": False,
                    "first_name": "TestingIni",
                },
                "text": "",
                "message_id": 1428
            },
            "update_id": 208026397
        }


    def script_reader(self, *args, **kwargs):
        handler = telegram.TelegramBotHandler
        with patch.object(handler, "__init__", lambda x, y: None):
            obj = handler(None)
            obj.message = None
            obj.update_id = None
            obj.dest_id = None
            obj.tip = False
            obj.tip_with_emoji = False
            obj.data = self.telegram_input
            msg = obj.process_data()['message']
        return msg


    def start(self, *args, **kwargs):
        self.telegram_input['message']['text'] = kwargs['text']
        self.telegram_input['message']['from']['id'] = 789
        self.telegram_input['message']['from']['first_name'] = 'TestingAccount'
        if not kwargs.get('retried', False):
            assert User.objects.count() == 2
        msg = self.script_reader(*args, **kwargs)
        if not kwargs.get('retried', False):
            assert User.objects.count() == 3
        assert kwargs['reply'] in str(msg)


    def faqs(self, *args, **kwargs):
        self.telegram_input['message']['text'] = kwargs['text']
        self.telegram_input['message']['from']['id'] = 789
        self.telegram_input['message']['from']['first_name'] = 'TestingAccount'
        msg = self.script_reader(*args, **kwargs)
        assert kwargs['reply'] in str(msg)


    def deposit(self, *args, **kwargs):
        self.telegram_input['message']['text'] = kwargs['text']
        self.telegram_input['message']['from']['id'] = 123
        self.telegram_input['message']['from']['first_name'] = 'TestingIni'
        msg = self.script_reader(*args, **kwargs)
        assert kwargs['reply'] == msg


    def check_deposit(self):
        expectation = json.dumps([
            {
                'txid': 'ca73c91e626b97001dafe022e0da3c88b6cf976f78f2d1bae73662ad00bdb1d9',
                'tokenDetails': {'valid': True,
                    'detail': {
                        'decimals': 8,
                        'tokenIdHex': '4de69e374a8ed21cbddd47f2338cc0f479dc58daa2bbe11cd604ca488eca0ddf',
                        'transactionType': 'SEND',
                        'versionType': 1,
                        'documentUri': 'spiceslp@gmail.com',
                        'documentSha256Hex': None,
                        'symbol': 'SPICE',
                        'name': 'Spice',
                        'txnBatonVout': None,
                        'txnContainsBaton': False,
                        'outputs': [
                            {
                                'address': 'simpleledger:qrh8c6dmuyx53429hruw2f9c0pc599es0gertxpqlt',
                                'amount': '1000'
                            },
                            {
                                'address': 'simpleledger:qqpwl8vp65hvx5rhjgzxn2fkan8mrm37py3v9qm5vs',
                                'amount': '499995'
                            }
                        ]
                    },
                    'invalidReason': None,
                    'schema_version': 71
                }
            }
        ])
        qs = User.objects.filter(telegram_id=123)
        user = qs.first()
        spice_addr = user.simple_ledger_address
        token_id = settings.SPICE_TOKEN_ID
        url = f"https://rest.bch.actorforth.org/v2/slp/transactions/{token_id}/{spice_addr}"

        self.requests_mock.get(url, text=expectation)

        user_list = list(qs.values())
        assert False == Deposit.objects.all().exists()
        value = tasks.check_deposits(objList=user_list)
        assert True == Deposit.objects.all().exists()
        assert value == ['123 - 1,000.00']


    def balance(self, *args, **kwargs):
        self.telegram_input['message']['text'] = kwargs['text']
        self.telegram_input['message']['from']['id'] = 123
        self.telegram_input['message']['from']['first_name'] = 'TestingIni'
        msg = self.script_reader(*args, **kwargs)
        assert kwargs['reply'] in str(msg)


    def tip(self, *args, **kwargs):
        self.telegram_input['message']['text'] = kwargs['text']
        self.telegram_input['message']['from']['id'] = 123
        self.telegram_input['message']['from']['first_name'] = 'TestingIni'
        self.telegram_input['message']['reply_to_message'] = {
            "from": {
                "id": 789,
                "username": "TestingAccount",
                "first_name": "TestingAccount",
                "is_bot": False
            },
            "message_id": 4321,
        }
        if kwargs.get('tipToBot', False):
            if kwargs.get('private', False):
                self.telegram_input['message']['chat']['type'] = 'private'
            else:
                self.telegram_input['message']['chat']['type'] = 'public'
            self.telegram_input['message']['reply_to_message']['from']['first_name'] = 'spice_devbot'
            self.telegram_input['message']['reply_to_message']['from']['username'] = 'spice_devbot'
        msg = self.script_reader()
        if msg is not None:
            assert kwargs['reply'] in msg
        else:
            assert kwargs['reply'] == msg


    def withdraw(self, *args, **kwargs):
        chat_type = kwargs.get('private', False)
        if chat_type:
            self.telegram_input['message']['chat']['type'] = 'private'
        else:
            self.telegram_input['message']['chat']['type'] = 'group'
        self.telegram_input['message']['text'] = kwargs['text']
        self.telegram_input['message']['from']['id'] = 123
        self.telegram_input['message']['from']['first_name'] = 'TestingIni'
        msg = self.script_reader(**kwargs)
        if msg is not None:
            assert kwargs['reply'] in msg
        else:
            assert kwargs['reply'] == msg


@pytest.mark.django_db
def test_telegramBot_transaction(requests_mock, monkeypatch):
    telegramBot = TelegramBotTest(requests_mock, monkeypatch)
    telegramBot.start(
        text="Hello buddy! I like you. This is my first chat",
        reply="To learn more about SpiceBot"
    )
    telegramBot.start(
        text="Hello again buddy! How are you?",
        reply="To learn more about SpiceBot",
        retried=True,
    )
    telegramBot.faqs(
        text="faqs",
        reply="To learn more about SpiceBot"
    )
    telegramBot.deposit(
        text="deposit",
        reply=None
    )
    telegramBot.check_deposit()
    telegramBot.balance(
        text="balance",
        reply="you have 1"
    )
    telegramBot.tip(
        text="tip 1",
        tipToBot=True,
        private=True,
        reply="To tip someone SPICE"
    )
    telegramBot.tip(
        text="tip 1",
        tipToBot=True,
        private=False,
        reply=None
    )
    telegramBot.tip(
        text="tip 1",
        reply="tipped"
    )
    telegramBot.tip(
        text="tip 100000",
        reply="you don't have enough"
    )
    telegramBot.tip(
        text="tip 100000 spice",
        reply="you don't have enough"
    )
    telegramBot.tip(
        text="tip 100000 spices",
        reply="you don't have enough"
    )
    telegramBot.withdraw(
        text="withdraw",
        private=True,
        reply="Withdrawing converts your SPICE Points"
    )
    telegramBot.withdraw(
        text="withdraw ",
        private=True,
        reply="Withdrawing converts your SPICE Points"
    )
    telegramBot.withdraw(
        text=" Withdraw ",
        private=True,
        reply="Withdrawing converts your SPICE Points"
    )
    telegramBot.withdraw(
        text="withdraw money",
        private=True,
        reply="Withdrawal can be done by running the following command"
    )
    telegramBot.withdraw(
        text="withdraw 10s spices",
        private=True,
        reply="Withdrawal can be done by running the following command"
    )
    telegramBot.withdraw(
        text="withdraw 1 simpleledger:qz2nyvzryrwsvg3zzwqmxmkatz9gze5ueyrwq30a8w",
        private=True,
        reply="We can’t process your withdrawal request because it is below minimum"
    )
    telegramBot.withdraw(
        text="withdraw 1000 simpleledger:qz2nyvzryrwsvg3zzwqmxmkatz9gze5ueyrwq30a8w",
        private=True,
        reply="withdrawal request is being processed."
    )
    telegramBot.withdraw(
        text="withdraw 1000 simpleledger:qz2nyvzryrwsvg3zzwqmxmkatz9gze5ueyrwq30a8w",
        private=True,
        reply="reached your hourly withdrawal limit!",
    )
    telegramBot.withdraw(
        text="withdraw 1000000 simpleledger:qz2nyvzryrwsvg3zzwqmxmkatz9gze5ueyrwq30a8w",
        private=True,
        reply="you don't have enough"
    )
