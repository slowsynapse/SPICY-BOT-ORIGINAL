# Generated by Django 2.2.1 on 2019-11-12 07:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0073_telegramgroup_disable_tipping'),
    ]

    operations = [
        migrations.AddField(
            model_name='deposit',
            name='date_processed',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]