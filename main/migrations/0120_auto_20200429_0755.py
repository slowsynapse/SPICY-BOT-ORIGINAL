# Generated by Django 2.2.1 on 2020-04-29 07:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0119_merge_20200427_0327'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='telegramgroup',
            index=models.Index(fields=['chat_id'], name='main_telegr_chat_id_3fe3b5_idx'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['telegram_id'], name='main_user_telegra_e28522_idx'),
        ),
    ]
