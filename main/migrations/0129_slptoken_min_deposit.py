# Generated by Django 2.2.1 on 2020-06-28 05:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0128_transaction_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='slptoken',
            name='min_deposit',
            field=models.FloatField(default=1),
        ),
    ]
