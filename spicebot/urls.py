"""spicebot URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.conf.urls import url
from django.urls import path, include

from main.views import *
from bridge.views import *


urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin/restart-supervisor/', csrf_exempt(RestartSupervisorView.as_view()), name='restart'),
    path('<int:id>/', contentpage, name='index'),
    path('webhooks/telegram/<params>', csrf_exempt(TelegramBotView.as_view())),
    path('webhooks/telegram/', csrf_exempt(TelegramBotView.as_view())),
    path('slpnotify/', csrf_exempt(SlpNotifyView.as_view())),
    path('api/signup/',signup, name='signup'),
    path('api/login/', login, name='login'),
    path('api/logout/', logout, name='logout'),
    path('api/connect-account/', connectAccount, name='connectAccount'),
    path('api/confirm-account/', confirmAccount, name='confirmAccount'),
    path('api/feed/stats/', csrf_exempt(SpiceFeedStats.as_view())),
    path('api/feed/content/', csrf_exempt(SpiceFeedContentView.as_view())),
    path('api/feed/leaderboard/', csrf_exempt(SpiceFeedLeaderBoardView.as_view())),
    path('api/faucet/', csrf_exempt(SpiceFaucetView.as_view())),
    path('api/faucet/task/', csrf_exempt(SpiceFaucetTaskView.as_view())),
    path('api/feed/details/<int:id>/', csrf_exempt(SpiceFeedContentDetailsView.as_view())),
    path('api/feed/pof/', csrf_exempt(ProofOfFrensView.as_view())),
    path('api/feed/search/<slug:user>/', csrf_exempt(UserSearchView.as_view())),
    path('api/feed/telegram-profile-photo/', csrf_exempt(TelegramProfilePhoto.as_view())),
    path('api/weekly-report/<int:id>/', csrf_exempt(WeeklyReportView.as_view())),
    path('api/spicebot/subscribe/', csrf_exempt(SubscribeView.as_view())),
    path('api/spicebot/balance/', csrf_exempt(BalanceView.as_view())),
    path('api/spicebot/deposit/', csrf_exempt(DepositView.as_view())),
    path('api/spicebot/withdraw/', csrf_exempt(WithdrawalView.as_view())),
    path('api/spicebot/tip/', csrf_exempt(TipView.as_view())),
    path('api/spicebot/transfer/', csrf_exempt(TransferView.as_view())),
    path('api/spicebot/dicemanager/', csrf_exempt(DiceManagerView.as_view())),
    path('api/spicebot/paperrockscissormanager/', csrf_exempt(PaperRockScissorManagerView.as_view())),
    path('api/spicebot/metrics/', csrf_exempt(MetricsView.as_view())),
    path('api/spicebot/telegram-group-profile-photo/', csrf_exempt(GroupProfilePicView.as_view())),
    path('api/spicebot/tokens/', csrf_exempt(SLPTokensView.as_view())),
    path('api/spicebot/frozencheck/<int:telegram_id>/', csrf_exempt(FrozenCheckView.as_view())),
    path('api/spicebot/trade/', csrf_exempt(SpiceTradeManagerView.as_view())),

    path('bridge/watchtower/', csrf_exempt(WatchtowerWebhookView.as_view()))
]
