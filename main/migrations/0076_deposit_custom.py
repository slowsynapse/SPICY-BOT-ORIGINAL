# Generated by Django 2.2.1 on 2019-11-12 09:29

from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('main', '0075_deposit_source'),
    ]

    def update_deposit_record(apps, schema_editor):
        Deposit = apps.get_model('main', 'Deposit')
        deposits = Deposit.objects.filter(date_processed=None)
        for deposit in deposits:
            deposit.source = 'old-deposit'
            deposit.date_processed = deposit.date_created
            deposit.save()
        
    operations = [
        migrations.RunPython(update_deposit_record)
    ]
