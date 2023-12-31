# Generated by Django 2.2.1 on 2020-08-06 07:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0130_user_slpnotified'),
    ]

    operations = [
        migrations.AddField(
            model_name='deposit',
            name='spentIndex',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterUniqueTogether(
            name='deposit',
            unique_together={('user', 'transaction_id', 'spentIndex')},
        ),
    ]
