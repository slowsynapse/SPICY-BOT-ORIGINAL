# Generated by Django 2.2.1 on 2019-08-27 14:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0047_user_pof'),
    ]

    operations = [
        migrations.AddField(
            model_name='deposit',
            name='date_swept',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]