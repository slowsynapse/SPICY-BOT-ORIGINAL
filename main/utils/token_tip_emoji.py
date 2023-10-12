from django.db.models import Q
import re
from main.models import SLPToken, User
from django.conf import settings
import random

class TokenTipEmoji(object):
    
    def __init__(self, *args, **kwargs):
        self.text = kwargs.get('text', None)
        assert self.text, 'text required.'
        self.ref_emojis = {}
        tokens = SLPToken.objects.exclude(tip_emojis={})
        for token in tokens:
            self.ref_emojis.update(token.tip_emojis)

    def extract(self):
        collection = {}
        for emoji in self.ref_emojis.keys():
            if emoji in self.text:
                considerable = True
                if emoji == '+':
                    # checks if plus is alone in text
                    if not re.match('^\s*([+]\s?)+\s*$', self.text):
                        considerable = False
                if considerable:
                    multiplier = self.text.count(emoji)   
                    token, value = self.get_token_value(emoji)
                    if token not in collection.keys(): collection[token] = 0
                    altogether = value * multiplier
                    collection[token] += altogether
                    self.text.replace(emoji, "")
        final_collection = {}
        for key in collection.keys():
            token = SLPToken.objects.get(name=key)
            # if self.has_balance(collection[key], token):
            final_collection.update({key:collection[key]})
        return final_collection

    def get_token_value(self,  emoji):
        q = Q(**{"tip_emojis__%s" % emoji: None })
        qs = SLPToken.objects.exclude(q)
        token = qs.first()
        value = token.tip_emojis[emoji]
        if value == "undefined": value = random.choice(range(0,1000))
        return token.name, value

        
        