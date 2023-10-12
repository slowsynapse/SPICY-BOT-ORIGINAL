# Generated by Django 2.2.1 on 2020-10-14 08:37

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0135_slptoken_publish'),
    ]

    operations = [
        migrations.AddField(
            model_name='slptoken',
            name='allowed_devs',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=list),
        ),
    ]
