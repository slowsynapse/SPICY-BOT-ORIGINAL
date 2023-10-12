# Generated by Django 2.2.1 on 2019-08-14 16:07

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0039_content_last_activity'),
    ]

    operations = [
        migrations.AddField(
            model_name='content',
            name='total_tips',
            field=models.FloatField(default=0),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='content',
            name='parent',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='main.Content'),
        ),
    ]
