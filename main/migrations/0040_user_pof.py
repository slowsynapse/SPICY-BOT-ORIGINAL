# Generated by Django 2.2.1 on 2019-08-14 07:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0039_merge_20190814_0547'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='pof',
            field=models.FloatField(default=0),
        ),
    ]
