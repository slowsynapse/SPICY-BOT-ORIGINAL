# Generated by Django 2.2.1 on 2020-04-23 02:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0112_auto_20200420_0420'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mute',
            name='base_fee',
            field=models.FloatField(default=2083),
        ),
        migrations.AlterField(
            model_name='mute',
            name='duration',
            field=models.FloatField(default=60),
        ),
        migrations.AlterField(
            model_name='mute',
            name='remaining_fee',
            field=models.FloatField(default=2083),
        ),
        migrations.AlterField(
            model_name='telegramgroup',
            name='pillory_fee',
            field=models.FloatField(default=2083),
        ),
        migrations.AlterField(
            model_name='telegramgroup',
            name='pillory_time',
            field=models.FloatField(default=60),
        ),
    ]