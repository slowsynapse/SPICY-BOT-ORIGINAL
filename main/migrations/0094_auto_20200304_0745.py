# Generated by Django 2.2.1 on 2020-03-04 07:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0093_auto_20200302_0519'),
    ]

    operations = [
        migrations.CreateModel(
            name='SLPToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60)),
                ('token_id', models.CharField(max_length=70)),
            ],
        ),
        migrations.AlterField(
            model_name='mute',
            name='base_fee',
            field=models.FloatField(default=100000),
        ),
        migrations.AlterField(
            model_name='mute',
            name='remaining_fee',
            field=models.FloatField(default=100000),
        ),
        migrations.AddField(
            model_name='transaction',
            name='slp_token',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='token', to='main.SLPToken'),
        ),
    ]
