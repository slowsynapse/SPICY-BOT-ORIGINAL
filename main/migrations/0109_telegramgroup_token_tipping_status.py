# Generated by Django 2.2.1 on 2020-03-30 06:49

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0108_metric_date_recorded'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramgroup',
            name='token_tipping_status',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]
