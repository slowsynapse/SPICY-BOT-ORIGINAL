# Generated by Django 2.2.1 on 2020-04-07 09:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0111_auto_20200402_0300'),
    ]

    operations = [
        migrations.AddField(
            model_name='slptoken',
            name='color',
            field=models.CharField(default='#F5B7B1', max_length=30),
        ),
    ]
