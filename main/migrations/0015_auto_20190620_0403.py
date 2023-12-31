# Generated by Django 2.2.1 on 2019-06-20 04:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0014_auto_20190620_0256'),
    ]

    operations = [
        migrations.CreateModel(
            name='SimpleLedgerAddress',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('simple_ledger_address', models.CharField(max_length=60, unique=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='slp_addresses', to='main.User')),
            ],
        ),
        migrations.DeleteModel(
            name='SimpleLegerAddress',
        ),
    ]
