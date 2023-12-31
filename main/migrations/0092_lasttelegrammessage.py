# Generated by Django 2.2.1 on 2020-02-21 09:27

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0091_auto_20200226_0816'),
    ]

    operations = [
        migrations.CreateModel(
            name='LastTelegramMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_message_timestamp', models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True)),
                ('telegram_group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='main.TelegramGroup')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='last_message', to='main.User')),
            ],
        ),
    ]
