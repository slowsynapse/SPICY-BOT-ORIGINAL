# Generated by Django 2.2.1 on 2019-07-24 13:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0034_auto_20190724_1127'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='telegram_id',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='twitter_id',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
    ]
