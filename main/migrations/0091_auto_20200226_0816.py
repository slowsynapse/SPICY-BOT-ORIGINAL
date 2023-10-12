# Generated by Django 2.2.1 on 2020-02-26 08:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0090_transaction_remark'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_muted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='muted_count',
            field=models.IntegerField(default=0),
        ),
        migrations.CreateModel(
            name='Mute',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('remaining_fee', models.FloatField(default=20000)),
                ('date_started', models.DateTimeField(blank=True, default=None, null=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mutes', to='main.TelegramGroup')),
                ('target_user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mutes', to='main.User')),
            ],
        ),
    ]