# Generated by Django 2.2.1 on 2019-08-16 08:17

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0042_user_account'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='confirmation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]
