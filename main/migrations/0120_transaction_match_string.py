# Generated by Django 2.2.1 on 2020-05-03 04:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0119_merge_20200427_0327'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='match_string',
            field=models.CharField(blank=True, max_length=200, null=True, unique=True),
        ),
    ]
