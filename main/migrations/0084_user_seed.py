# Generated by Django 2.2.1 on 2019-12-18 07:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0083_subscriber_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='seed',
            field=models.CharField(default='', max_length=200),
        ),
    ]
