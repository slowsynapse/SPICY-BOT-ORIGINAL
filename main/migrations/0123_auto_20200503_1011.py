# Generated by Django 2.2.1 on 2020-05-03 10:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0122_auto_20200503_0455'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='transaction_hash',
            field=models.CharField(max_length=200, unique=True),
        ),
    ]
