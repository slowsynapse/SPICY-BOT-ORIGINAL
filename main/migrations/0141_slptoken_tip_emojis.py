# Generated by Django 2.2.1 on 2020-11-18 03:52

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0140_slptoken_faucet_period_hours'),
    ]

    operations = [
        migrations.AddField(
            model_name='slptoken',
            name='tip_emojis',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]