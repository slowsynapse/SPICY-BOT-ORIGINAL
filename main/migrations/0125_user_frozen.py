# Generated by Django 2.2.1 on 2020-05-11 03:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0124_merge_20200505_0944'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='frozen',
            field=models.BooleanField(default=False),
        ),
    ]
