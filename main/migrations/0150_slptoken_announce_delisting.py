# Generated by Django 2.2.1 on 2021-04-13 06:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0149_auto_20210408_0602'),
    ]

    operations = [
        migrations.AddField(
            model_name='slptoken',
            name='announce_delisting',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
