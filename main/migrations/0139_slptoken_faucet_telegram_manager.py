# Generated by Django 2.2.1 on 2020-11-15 04:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0138_faucetdisbursement_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='slptoken',
            name='faucet_telegram_manager',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
    ]
