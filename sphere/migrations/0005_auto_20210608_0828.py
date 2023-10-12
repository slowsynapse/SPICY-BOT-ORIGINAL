# Generated by Django 2.2.1 on 2021-06-08 08:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sphere', '0004_auto_20210608_0820'),
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
            model_name='challenge',
            name='slptoken',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sphere_challenges', to='sphere.SLPToken'),
        ),
    ]
