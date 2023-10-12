# Generated by Django 2.2.1 on 2019-06-18 14:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0010_telegramchat'),
    ]

    operations = [
        migrations.CreateModel(
            name='TelegramGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chat_id', models.CharField(max_length=50)),
                ('chat_type', models.CharField(max_length=20)),
                ('title', models.CharField(max_length=70)),
                ('post_to_spicefeed', models.BooleanField(default=False)),
                ('privacy_set_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='main.User')),
            ],
        ),
        migrations.DeleteModel(
            name='TelegramChat',
        ),
    ]
