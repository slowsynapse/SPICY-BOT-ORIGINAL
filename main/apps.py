from django.apps import AppConfig
from django.conf import settings

class MainConfig(AppConfig):
    name = 'main'

    def build_child_socket(self):
        from rest_hooks.models import Hook
        from django.conf import settings
        from django.contrib.auth.models import User as djUser
        user = djUser.objects.first()
        if user:
            events = settings.HOOK_EVENTS.keys()
            for event in events:
                model = event.split('.')[0]
                target = '%s/webhooks/%s' % (settings.HOOK_TARGET, model)
                obj, created = Hook.objects.get_or_create(user=user, event=event, target=target)
                        
    def ready(self):
        import main.signals
        # from main.tasks import deposit_socket, enable_feature
        # from constance import config
        # urls = [
            # 'https://slpsocket.bitcoin.com/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0=',
            # 'http://209.188.18.218:4001/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0=',
            # 'https://slpsocket.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjogewogICAgfQogIH0KfQ=='
        # ]
        # for url in urls:    
            # deposit_socket.delay(url)
