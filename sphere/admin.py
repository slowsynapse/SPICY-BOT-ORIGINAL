from django.contrib import admin
from sphere.models import Challenge, Exchange


class ChallengeAdmin(admin.ModelAdmin):
    list_display = [
        'challenger_username',
        'contender_username',
        'bet_amount',
        'result',
        'date_created',
        'slptoken'
    ]

admin.site.register(Challenge, ChallengeAdmin)


class ExchangeAdmin(admin.ModelAdmin):
    list_display = [
        'date_created',
        'buyer_id',
        'seller_id',
        'payment_token',
        'payment_amount',
        'exchange_token',
        'exchange_amount',
        'date_processed',
    ]



admin.site.register(Exchange, ExchangeAdmin)