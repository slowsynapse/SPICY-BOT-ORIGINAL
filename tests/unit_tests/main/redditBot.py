import mock
from pytest_mock import mocker
import pytest
from main.utils import reddit
from mock import patch
from main import tasks
from main.models import User, Deposit
from django.conf import settings
import json

class RedditBotTest(object):


	def __init__(self, requests_mock, monkeypatch):
		self.requests_mock = requests_mock
		self.monkeypatch = monkeypatch

	def script_reader(self, *args, **kwargs):
		handler = reddit.RedditBot
		with patch.object(handler, "__init__", lambda x, y: None):
			obj = handler(None)
			if settings.DEPLOYMENT_INSTANCE == 'prod':
				self.subreddit_name = 'spice'
				self.keyphrase = '@spicetokens'
			else:
				self.subreddit_name = 'testingground4bots'
				self.keyphrase = '@spicebot'
			obj.authenticate()
			msg = obj.process_messages()
		return msg	    


	


@pytest.mark.django_db
def test_redditBot_transaction(requests_mock, monkeypatch):
	redditBot = RedditBotTest(requests_mock, monkeypatch)
	#first message to reddit bot
	# redditBot.start(
	# 	text="Hi, this is my first message",
	# 	reply="To learn more about SpiceBot"	
	# )