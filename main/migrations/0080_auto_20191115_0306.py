# Generated by Django 2.2.1 on 2019-11-15 03:06

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0079_merge_20191114_1034'),
    ]

    def delete_duplicate_rows(apps, schema_editor):
        Response = apps.get_model('main', 'Response')
        responses = Response.objects.all()
        for response in responses: 
            qs = Response.objects.filter(body=response.body) 
            if qs.count() > 1:
                qs.first().delete() 

        
    operations = [
        migrations.RunPython(delete_duplicate_rows),
        migrations.AlterField(
            model_name='response',
            name='body',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict, unique=True),
        ),
    ]
