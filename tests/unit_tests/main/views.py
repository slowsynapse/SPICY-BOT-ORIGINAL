from django.test import Client
import pytest
import json
from main.models import User, Content

@pytest.mark.django_db
def test_SpiceFeedContentView(mocker):
    client = Client()
    response = client.get('/api/feed/content/')
    assert response.status_code == 200


@pytest.mark.django_db
def test_SpiceFeedLeaderBoardView(mocker):
    client = Client()
    response = client.get('/api/feed/leaderboard/')
    assert response.status_code == 200


@pytest.mark.django_db
def test_SpiceFeedContentDetailsView(mocker):
    user1 = User.objects.first()
    user2 = User.objects.last()
    instance = Content(
        source='telegram',
        tip_amount=10,
        sender=user1,
        recipient=user2,
        details={'message':{'text':'nice','date':1, 'reply_to_message': {'text': 'sample', 'date': 1}}},
        recipient_content_id={},
    )
    instance.save()
    client = Client()
    response = client.get('/api/feed/details/%s/' % instance.id)
    assert response.status_code == 200