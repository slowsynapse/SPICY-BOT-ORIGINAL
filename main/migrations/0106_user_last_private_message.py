# Generated by Django 2.2.1 on 2020-03-25 03:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0105_metric'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='last_private_message',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]