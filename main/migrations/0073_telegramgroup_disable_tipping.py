# Generated by Django 2.2.1 on 2019-10-29 08:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0072_merge_20191017_0840'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramgroup',
            name='disable_tipping',
            field=models.BooleanField(default=False),
        ),
    ]
