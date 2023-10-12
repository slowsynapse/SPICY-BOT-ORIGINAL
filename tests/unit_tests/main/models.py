import pytest
from main.models import (
    User,
    Withdrawal,
    TelegramGroup,
    Content,
    Transaction,
    Deposit,
    Media,
    FaucetDisbursement
)
pytestmark = pytest.mark.django_db

class TestUserModel(object):

     
    def test_save(self):
        user = User(
            telegram_id=321
        )
        user.save()
        assert user.simple_ledger_address != ""
        assert user.bitcoincash_address != ""


class TestWithdrawModel(object):

    def test_save(self):
        user = User.objects.first()
        amount = '100'
        address = 'simpleledger:qqpwl8vp65hvx5rhjgzxn2fkan8mrm37py3v9qm5vs'
        transaction_id = 'ca73c91e626b97001dafe022e0da3c88b6cf976f78f2d1bae73662ad00bdb1d9'
        w = Withdrawal(user=user,amount=amount,address=address,transaction_id=transaction_id)
        w.save()
        assert w.id == 1


class TestTelegramGroupModel(object):

    def test_save(self):
        user = User.objects.first()
        instance = TelegramGroup(
            chat_id='123',
            chat_type='private',
            title='SPICEBOT',
            privacy_set_by=user
        )
        instance.save()
        assert instance.id == 1


class TestContentModel(object):

    def test_save(self):
        user1 = User.objects.first()
        user2 = User.objects.last()
        instance = Content(
            source='telegram',
            tip_amount=10,
            sender=user1,
            recipient=user2,
            details={'message':{'reply_to_message': {}}},
            recipient_content_id={},
        )
        instance.save()
        assert instance.id == 1


class TestTransactionModel(object):

    def test_save(self):
        user=User.objects.first()
        instance = Transaction(
            user=user,
            amount=10,
            transaction_type='Incoming'
        )
        instance.save()
        assert instance.id == 1


class TestDepositModel(object):

    def test_save(self):
        user = User.objects.first()
        instance = Deposit(
            user=user,
            transaction_id='ca73c91e626b97001dafe022e0da3c88b6cf976f78f2d1bae73662ad00bdb1d9',
            amount=10,
            notes='Test only'
        )
        instance.save()
        assert instance.id == 1


class TestMediaModel(object):

    def test_save(self):
        user1 = User.objects.first()
        user2 = User.objects.last()
        content = Content(
            source='telegram',
            tip_amount=10,
            sender=user1,
            recipient=user2,
            details={'message':{'reply_to_message': {}}},
            recipient_content_id={},
        )
        content.save()
        instance = Media(
            content=content,
            file_id='100',
            url='https://explorer.bitcoin.com/bch/address/bitcoincash:qz2nyvzryrwsvg3zzwqmxmkatz9gze5uey04t26aes'
        )
        instance.save()
        assert instance.id == 1


class TestFaucetDisbursementModel(object):

    def test_save(self):
        instance = FaucetDisbursement(
            ip_address='192.168.1.1',
            ga_cookie='34cq3rfcasdfasasdfsdfasdfasdfasfas',
            slp_address='simpleledger:qz2nyvzryrwsvg3zzwqmxmkatz9gze5ueyrwq30a8w',
            transaction_id='ca73c91e626b97001dafe022e0da3c88b6cf976f78f2d1bae73662ad00bdb1d9',
            amount=10
        )
        instance.save()
        assert instance.id == 1
        
