# Generated by Django 2.2.1 on 2020-01-24 03:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0086_auto_20191231_0321'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='running_balance',
            field=models.FloatField(default=0),
        ),
    ]
