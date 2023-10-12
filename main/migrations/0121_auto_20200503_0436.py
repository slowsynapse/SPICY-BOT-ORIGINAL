# Generated by Django 2.2.1 on 2020-05-03 04:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0120_transaction_match_string'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='match_string',
        ),
        migrations.AddField(
            model_name='transaction',
            name='transaction_hash',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
