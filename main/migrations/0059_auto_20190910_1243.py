# Generated by Django 2.2.1 on 2019-09-10 12:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0058_auto_20190906_0408'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deposit',
            name='transaction_id',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]