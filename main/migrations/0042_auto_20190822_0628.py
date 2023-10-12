# Generated by Django 2.2.1 on 2019-08-22 06:28

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0041_merge_20190815_0326'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='reddit_id',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='user',
            name='reddit_user_details',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]
