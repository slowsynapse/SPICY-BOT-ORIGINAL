from django.contrib import admin
from bridge.models import (
    Token,
    SwapRequest,
    Fulfillment
)
from bridge.tasks import fulfill_swap_request

class TokenAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'slp_token_id',
        'slp_balance',
        'sep20_contract',
        'sep20_balance'
    ]

admin.site.register(Token, TokenAdmin)


class SwapRequestAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'amount',
        'token',
        'date_created',
        'from_address',
        'receive_transaction_hash',
        'to_address',
        'send_transaction_hash',
        'date_fulfilled'
    ]

    raw_id_fields = ['user']

    actions = ['process_request']

    def send_transaction_hash(self, obj):
        return obj.fulfillment.send_transaction_hash

    def process_request(self, request, queryset):
        for obj in queryset.all():
            if obj.receive_transaction_hash:
                if not obj.date_fulfilled:
                    fulfill_swap_request(obj.id)

admin.site.register(SwapRequest, SwapRequestAdmin)


admin.site.register(Fulfillment)
