# Generated by Django 2.2.1 on 2019-06-29 12:15

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0017_simpleledgeraddress_date_created'),
    ]

    operations = [
        migrations.AddField(
            model_name='media',
            name='content',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='media', to='main.Content'),
        ),
    ]
