# Generated by Django 2.2.1 on 2019-12-17 07:57

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0082_auto_20191125_0604'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriber',
            name='details',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=None, null=True),
        ),
    ]
