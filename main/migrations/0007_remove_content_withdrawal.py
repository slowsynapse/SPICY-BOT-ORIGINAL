# Generated by Django 2.2.1 on 2019-06-07 01:48

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_auto_20190607_0007'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='content',
            name='withdrawal',
        ),
    ]
