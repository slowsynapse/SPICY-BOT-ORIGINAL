# Generated by Django 2.2.1 on 2019-08-21 13:17

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0046_remove_user_pof'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='pof',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]
