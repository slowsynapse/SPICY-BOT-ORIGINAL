# Generated by Django 2.2.1 on 2020-01-24 22:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0086_auto_20191231_0321'),
    ]

    operations = [
        migrations.AlterField(
            model_name='media',
            name='file_id',
            field=models.CharField(max_length=500),
        ),
    ]
