# Generated by Django 2.2.1 on 2019-10-02 00:24

from django.db import migrations


def add_date_created(apps, schema_editor):
    User = apps.get_model("main", "User")
    Content = apps.get_model("main", "Content")
    TelegramGroup = apps.get_model("main", "TelegramGroup")

    # Add date created to users
    users = User.objects.all()
    for user in users:
        first_tip_received = Content.objects.filter(recipient=user).first()
        first_tip_sent = Content.objects.filter(sender=user).first()

        if first_tip_received or first_tip_sent:
            if not first_tip_sent:
                if first_tip_received:
                    user.date_created = first_tip_received.date_created
            if not first_tip_received:
                if first_tip_sent:
                    user.date_created = first_tip_sent.date_created

            if first_tip_received and first_tip_sent:
                if first_tip_received.date_created < first_tip_sent.date_created:
                    user.date_created = first_tip_received.date_created
                else:
                    user.date_created = first_tip_sent.date_created

        user.save()
    
    # Add date created to telegram groups
    groups = TelegramGroup.objects.all()
    for group in groups:
        chat_id = group.chat_id
        contents = Content.objects.filter(source='telegram', details__message__chat__id=int(chat_id))
        if contents.first():
            group.date_created = contents.first().date_created
        else:
            group.date_created = None
        group.save()


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0065_auto_20191002_0024'),
    ]

    operations = [
        migrations.RunPython(add_date_created)
    ]
