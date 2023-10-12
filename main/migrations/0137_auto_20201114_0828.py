# Generated by Django 2.2.1 on 2020-11-14 08:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0136_slptoken_allowed_devs'),
    ]

    operations = [
        migrations.AddField(
            model_name='slptoken',
            name='faucet_amount_max',
            field=models.FloatField(default=10),
        ),
        migrations.AddField(
            model_name='slptoken',
            name='faucet_amount_min',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='slptoken',
            name='faucet_daily_allotment',
            field=models.FloatField(default=1000),
        ),
        migrations.AddField(
            model_name='slptoken',
            name='faucet_interval',
            field=models.IntegerField(default=24),
        ),
    ]
