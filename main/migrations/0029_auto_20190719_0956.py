# Generated by Django 2.2.1 on 2019-07-19 09:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0028_auto_20190719_0952'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='bitcash_address',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='simple_ledger_address',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='wif',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
    ]
