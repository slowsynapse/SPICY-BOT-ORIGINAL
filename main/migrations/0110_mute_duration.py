# Generated by Django 2.2.1 on 2020-04-01 05:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0109_telegramgroup_token_tipping_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='mute',
            name='duration',
            field=models.FloatField(default=720.0),
        ),
    ]