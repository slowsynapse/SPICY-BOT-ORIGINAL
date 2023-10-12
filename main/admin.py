from django.contrib import admin
from django.db.models import Count, Sum, Case, When, F, IntegerField
from django.utils.html import format_html
from main.models import (
    User as SpiceUser,
    Content,
    Transaction,
    Deposit,
    Withdrawal,
    TelegramGroup,
    Media,
    FaucetDisbursement,
    Account,
    Response,
    Rain,
    WeeklyReport,
    ErrorLog,
    Subscriber,
    BitcoinBlockHeight,
    Mute,
    LastTelegramMessage,
    SLPToken,
    Metric,
    LastGroupActivity
)


admin.site.site_header = 'Spice Bot Administration'


class WithTransactions(admin.SimpleListFilter):

    title = 'with_transactions'
    parameter_name = 'with_transactions'

    def lookups(self, request, model_admin):
        return (
            ('Yes', 'Yes'),
            ('No', 'No'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        queryset = queryset.annotate(
            txn_count=Count('transactions')
        )
        if value == 'Yes':
            return queryset.filter(txn_count__gt=0)
        elif value == 'No':
            return queryset.filter(txn_count=0)
        return queryset


class UserAdmin(admin.ModelAdmin):

    list_display = [
        'id', 
        'telegram_display_name', 
        'twitter_screen_name', 
        'balance', 
        'reddit_username', 
        'user_username', 
        'pof', 
        'ban',
        'frozen'
    ]
    search_fields = ['telegram_user_details', 'twitter_user_details', 'reddit_user_details']
    list_filter = [WithTransactions]

    #update for other slp balance
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            _sum_incoming=Sum(
                Case(
                    When(
                        transactions__transaction_type__icontains='Incoming',
                        #transactions__slp_token__token_id=settings.SPICE_TOKEN_ID,
                        then=F('transactions__amount')
                    ),
                    output_field=IntegerField(),
                    default=0
                )
            ),
            _sum_outgoing=Sum(
                Case(
                    When(
                        transactions__transaction_type__icontains='Outgoing',
                        #transactions__slp_token__token_id=settings.SPICE_TOKEN_ID,
                        then=F('transactions__amount')
                    ),
                    output_field=IntegerField(),
                    default=0
                )
            ),
            _balance=F('_sum_incoming') - F('_sum_outgoing')
        )
        return queryset
    
    def telegram_display_name(self, obj):
        if obj.telegram_user_details:
            return obj.telegram_display_name
        return str(obj.telegram_id)

    def twitter_screen_name(self, obj):
        return obj.twitter_screen_name

    def reddit_username(self, obj):
        if obj.reddit_user_details:
            return obj.reddit_username
        return str(obj.reddit_username)

    def balance(self, obj):
        return obj._balance

    balance.admin_order_field = '_balance'


admin.site.register(SpiceUser, UserAdmin)

class SubscriberAdmin(admin.ModelAdmin):
    list_display = [
        'username',
        'token',
        'payment'
    ]

admin.site.register(Subscriber, SubscriberAdmin)

class ContentAdmin(admin.ModelAdmin):
    list_display = [
        'tip_amount',
        'source',
        'sender',
        'recipient', 
        'date_created',
        'parent'
    ]

    raw_id_fields = ['sender', 'recipient', 'parent']

admin.site.register(Content, ContentAdmin)


class ResponseAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'body',
        'response_type',
        'botReplied',
        'date_created',
    ]

admin.site.register(Response, ResponseAdmin)


class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 
        'amount',
        'slp_token',
        'transaction_type',
        'transaction_hash',
        'operation',
        'date_created',
        'remark'
    ]

    raw_id_fields = ['user']

admin.site.register(Transaction, TransactionAdmin)


class DepositAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'amount',
        'slp_token',
        'date_created',
        'date_swept',
        'source',
        'date_processed',
        '_txid',
        'spentIndex'
    ]
    raw_id_fields = ['user']

    def _txid(self, obj):
        url = f'https://explorer.bitcoin.com/bch/tx/{obj.transaction_id}'
        return format_html(
            f"""<a class="button"
            target="_blank" 
            href="{url}"
            style="background-color:transparent;
            padding:0px;
            color:#447e9b;
            text-decoration:None;
            font-weight:bold;">{obj.transaction_id}</a>"""
        )

admin.site.register(Deposit, DepositAdmin)



class BitcoinBlockHeightAdmin(admin.ModelAdmin):
    list_display = [
        'number',
        'processed',    
    ]
    ordering = ('-number',)

admin.site.register(BitcoinBlockHeight, BitcoinBlockHeightAdmin)

class WithdrawalAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'channel',
        'address',
        'amount',
        'slp_token',
        'date_created',
        'date_started',
        'date_completed',
        'date_failed'
    ]

    raw_id_fields = ['user']

    def channel(self, obj):
        channel = ''
        if obj.user.twitter_id:
            channel = 'twitter'
        if obj.user.telegram_id:
            channel = 'telegram'
        if obj.user.reddit_id:
            channel = 'reddit'
        return channel

admin.site.register(Withdrawal, WithdrawalAdmin)


class MediaAdmin(admin.ModelAdmin):
    list_display = [
        'file_id',
        'url'
    ]

admin.site.register(Media, MediaAdmin)


class TelegramGroupAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'chat_type',
        'post_to_spicefeed',
        'privacy_set_by'
    ]


admin.site.register(TelegramGroup, TelegramGroupAdmin)


class FaucetDisbursementAdmin(admin.ModelAdmin):
    list_display = [
        'slp_address',
        'amount',
        'ip_address',
        'date_created',
        'date_completed'
    ]


admin.site.register(FaucetDisbursement, FaucetDisbursementAdmin)


class AccountAdmin(admin.ModelAdmin):
    list_display = [
        'username',
        'email_addr'        
    ]

admin.site.register(Account, AccountAdmin)

class RainAdmin(admin.ModelAdmin):    
    list_display = [        
        'sender',
        'rain_amount',
        'get_recipients',
        'message_id'
    ]

admin.site.register(Rain, RainAdmin)

class WeeklyReportAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'report'
    ]
admin.site.register(WeeklyReport, WeeklyReportAdmin)

class ErrorLogAdmin(admin.ModelAdmin):    
    list_display = [        
        'origin',
        'datetime'
    ]

admin.site.register(ErrorLog, ErrorLogAdmin)


class MuteAdmin(admin.ModelAdmin):    
    list_display = [        
        'target_user',
        'group',
        'remaining_fee'
    ]

admin.site.register(Mute, MuteAdmin)


class LastTelegramMessageAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'last_message_timestamp',
        'telegram_group'   
    ]
admin.site.register(LastTelegramMessage, LastTelegramMessageAdmin)


class SLPTokenAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'token_id',
        'verbose_names'
    ]
admin.site.register(SLPToken, SLPTokenAdmin)


class MetricAdmin(admin.ModelAdmin):
    list_display = [
        'user_metrics',
        'tip_metrics',
        'date_recorded'
    ]

admin.site.register(Metric, MetricAdmin)



class LastGroupActivityAdmin(admin.ModelAdmin):
    list_display = [
        'group_title',
        'user',
        'timestamp'
    ]

    def group_title(self, obj):
        return obj.group.title

admin.site.register(LastGroupActivity, LastGroupActivityAdmin)

