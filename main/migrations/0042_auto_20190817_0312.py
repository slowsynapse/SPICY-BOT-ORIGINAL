# Generated by Django 2.2.1 on 2019-08-17 03:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0041_merge_20190815_0904'),
    ]

    operations = [
        migrations.AlterField(
            model_name='content',
            name='total_tips',
            field=models.FloatField(default=0, null=True),
        ),
    ]