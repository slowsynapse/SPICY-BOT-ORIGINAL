# Generated by Django 2.2.1 on 2019-08-10 07:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0036_remove_user_wif'),
    ]

    operations = [
        migrations.AlterField(
            model_name='content',
            name='parent',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.PROTECT, to='main.Content'),
        ),
    ]
