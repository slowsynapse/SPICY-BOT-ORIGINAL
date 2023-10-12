# Generated by Django 2.2.1 on 2020-03-11 03:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0095_deposit_slp_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='content',
            name='slp_token',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='main.SLPToken'),
        ),
    ]
