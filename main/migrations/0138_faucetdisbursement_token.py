# Generated by Django 2.2.1 on 2020-11-14 08:32

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0137_auto_20201114_0828'),
    ]

    operations = [
        migrations.AddField(
            model_name='faucetdisbursement',
            name='token',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='faucet_disbursement', to='main.SLPToken'),
        ),
    ]