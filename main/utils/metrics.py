import calendar
import logging
from datetime import timedelta, datetime


from main.utils.account import get_balance
from django.db.models.query import QuerySet
from django.utils import timezone
from django.conf import settings
from django.db.models import (
    Avg, 
    Sum,
    Count,
    Q
)
from main.models import (
    User,
    Withdrawal,
    Deposit,
    Transaction,
    SLPToken,
    Rain,
    Subscriber,
    TelegramGroup,
    Metric,
)

logger = logging.getLogger(__name__)


class SpiceBotMetricHandler(object):

    def __init__(self):
        self.spice_token = SLPToken.objects.get(token_id=settings.SPICE_TOKEN_ID)
        self.SEC = 'second'
        self.MIN = 'minute'
        self.HOUR = 'hour'
        self.DAY = 'day'
        self.WEEK = 'week'
        self.MONTH = 'month'

        self.AVG = 'average'
        self.TOTAL = 'total'
        self.COUNT = 'count'

        self.WAGER = 'WAGER'
        self.JANKEN = 'JANKEN'

        self.WITHDRAW = 'WITHDRAW'
        self.TIP = 'TIP'

#################### UTILITY METHODS #########################

    def get_date_time(self, duration, time_type):
        time = None
        time_type = time_type.lower()
        if time_type == self.SEC:
            time = timezone.now() - timedelta(seconds=duration)
        elif time_type == self.MIN:
            time = timezone.now() - timedelta(minutes=duration)
        elif time_type == self.HOUR:
            time = timezone.now() - timedelta(hours=duration)
        elif time_type == self.DAY:
            time = timezone.now() - timedelta(days=duration)
        elif time_type == self.WEEK:
            time = timezone.now() - timedelta(weeks=duration)
        return time

    def round_or_zero(self, var):
        if var is None:
            return 0
        else:
            return round(var, 2)

    def qs_or_none(self, value):
        if isinstance(value, QuerySet):
            if value.count() == 0:
                return None
        return value
    
    # methods that have parameters used in get_daily_weekly_monthly_metrics method
    def is_parametrized_dwm_method(self, method):
        return (
            method == self.game_earnings
            or method == self.total_bets
            or method == self.get_fee_earnings
        )

    def is_weekly_monthly_allowed_method(self, method):
        return (
            method == self.total_new_users
            or method == self.total_new_groups
            or method == self.total_bets
            or method == self.game_earnings
            or method == self.get_fee_earnings
        )

    # Generic method for getting a metric value by daily, weekly and monthly
    def get_daily_weekly_monthly_metric(self, metric_method, **kwargs):
        metric_details = {}
        operation = kwargs.get('operation', '')

        # DAILY
        if self.is_parametrized_dwm_method(metric_method):
            metric_details[self.DAY] = self.qs_or_none(metric_method(1, operation))
        else:
            metric_details[self.DAY] = self.qs_or_none(metric_method(1))

        # only return weekly and monthly metrics every end of the week and month respectively
        today = timezone.now()
        last_day = calendar.monthrange(today.year, today.month)[1]

        # WEEKLY
        if today.strftime('%A') == 'Saturday':
            if self.is_parametrized_dwm_method(metric_method):
                metric_details[self.WEEK] = {
                    'value': self.qs_or_none(metric_method(7, operation)),
                    'is_new': True
                }
            else:
                metric_details[self.WEEK] = {
                    'value': self.qs_or_none(metric_method(7)),
                    'is_new': True
                }
        else:
            if self.is_weekly_monthly_allowed_method(metric_method):
                metric_details[self.WEEK] = {
                    'value': 0,
                    'is_new': False
                }

                qs_metrics = Metric.objects.order_by('date_recorded')

                if metric_method == self.total_new_users:
                    weekly_data = qs_metrics.exclude(user_metrics__total_new_users__week__value=0)
                elif metric_method == self.total_new_groups:
                    weekly_data = qs_metrics.exclude(group_metrics__total_new_groups__week__value=0)
                elif metric_method == self.total_bets:
                    if operation == self.WAGER:
                        weekly_data = qs_metrics.exclude(game_metrics__wagerbot_bets_count__week__value=0)
                    elif operation == self.JANKEN:
                        weekly_data = qs_metrics.exclude(game_metrics__jankenbot_bets_count__week__value=0)
                elif metric_method == self.game_earnings:
                    if operation == self.WAGER:
                        weekly_data = qs_metrics.exclude(game_metrics__wagerbot_earnings__week__value=0)
                    elif operation == self.JANKEN:
                        weekly_data = qs_metrics.exclude(game_metrics__jankenbot_earnings__week__value=0)
                elif metric_method == self.get_fee_earnings:
                    if operation == self.WITHDRAW:
                        weekly_data = qs_metrics.exclude(withdrawal_metrics__earnings__week__value=0)
                    elif operation == self.TIP:
                        weekly_data = qs_metrics.exclude(tip_metrics__earnings__week__value=0)


                if weekly_data.exists():
                    weekly_data = weekly_data.last()

                    if metric_method == self.total_new_users:
                        metric_details[self.WEEK]['value'] = weekly_data.user_metrics['total_new_users']['week']['value']
                    elif metric_method == self.total_new_groups:
                        metric_details[self.WEEK]['value'] = weekly_data.group_metrics['total_new_groups']['week']['value']
                    elif metric_method == self.total_bets:
                        if operation == self.WAGER:
                            metric_details[self.WEEK]['value'] = weekly_data.game_metrics['wagerbot_bets_count']['week']['value']
                        elif operation == self.JANKEN:
                            metric_details[self.WEEK]['value'] = weekly_data.game_metrics['jankenbot_bets_count']['week']['value']
                    elif metric_method == self.game_earnings:
                        if operation == self.WAGER:
                            metric_details[self.WEEK]['value'] = weekly_data.game_metrics['wagerbot_earnings']['week']['value']
                        elif operation == self.JANKEN:
                            metric_details[self.WEEK]['value'] = weekly_data.game_metrics['jankenbot_earnings']['week']['value']
                    elif metric_method == self.get_fee_earnings:
                        if operation == self.WITHDRAW:
                            metric_details[self.WEEK]['value'] = weekly_data.withdrawal_metrics['earnings']['week']['value']
                        elif operation == self.TIP:
                            metric_details[self.WEEK]['value'] = weekly_data.tip_metrics['earnings']['week']['value']
            
            elif metric_method == self.top_ten_active_groups:
                metric_details[self.WEEK] = {
                    'value': [],
                    'is_new': False
                }
                qs_metrics = Metric.objects.order_by('date_recorded')
                weekly_data = qs_metrics.exclude(group_metrics__top_ten_active_groups__week__value=[])
                if weekly_data.exists():
                    weekly_data = weekly_data.last()
                    metric_details[self.WEEK]['value'] = weekly_data.group_metrics['top_ten_active_groups']['week']['value']

        # MONTHLY
        if last_day == today.day:
            if self.is_parametrized_dwm_method(metric_method):
                metric_details[self.MONTH] = {
                    'value': self.qs_or_none(metric_method(last_day, operation)),
                    'is_new': True
                }
            else:
                metric_details[self.MONTH] = {
                    'value': self.qs_or_none(metric_method(last_day)),
                    'is_new': True
                }
        else:
            if self.is_weekly_monthly_allowed_method(metric_method):
                metric_details[self.MONTH] = {
                    'value': 0,
                    'is_new': False
                }
                qs_metrics = Metric.objects.order_by('date_recorded')

                if metric_method == self.total_new_users:
                    monthly_data = qs_metrics.exclude(user_metrics__total_new_users__month__value=0)
                elif metric_method == self.total_new_groups:
                    monthly_data = qs_metrics.exclude(group_metrics__total_new_groups__month__value=0)
                elif metric_method == self.total_bets:
                    if operation == self.WAGER:
                        monthly_data = qs_metrics.exclude(game_metrics__wagerbot_bets_count__month__value=0)
                    elif operation == self.JANKEN:
                        monthly_data = qs_metrics.exclude(game_metrics__jankenbot_bets_count__month__value=0)
                elif metric_method == self.game_earnings:
                    if operation == self.WAGER:
                        monthly_data = qs_metrics.exclude(game_metrics__wagerbot_earnings__month__value=0)
                    elif operation == self.JANKEN:
                        monthly_data = qs_metrics.exclude(game_metrics__jankenbot_earnings__month__value=0)
                elif metric_method == self.get_fee_earnings:
                    if operation == self.WITHDRAW:
                        monthly_data = qs_metrics.exclude(withdrawal_metrics__earnings__month__value=0)
                    elif operation == self.TIP:
                        monthly_data = qs_metrics.exclude(tip_metrics__earnings__month__value=0)

                if monthly_data.exists():
                    monthly_data = monthly_data.last()

                    if metric_method == self.total_new_users:
                        metric_details[self.MONTH]['value'] = monthly_data.user_metrics['total_new_users']['month']['value']
                    elif metric_method == self.total_new_groups:
                        metric_details[self.MONTH]['value'] = monthly_data.group_metrics['total_new_groups']['month']['value']
                    elif metric_method == self.total_bets:
                        if operation == self.WAGER:
                            metric_details[self.MONTH]['value'] = monthly_data.game_metrics['wagerbot_bets_count']['month']['value']
                        elif operation == self.JANKEN:
                            metric_details[self.MONTH]['value'] = monthly_data.game_metrics['jankenbot_bets_count']['month']['value']
                    elif metric_method == self.game_earnings:
                        if operation == self.WAGER:
                            metric_details[self.MONTH]['value'] = monthly_data.game_metrics['wagerbot_earnings']['month']['value']
                        elif operation == self.JANKEN:
                            metric_details[self.MONTH]['value'] = monthly_data.game_metrics['jankenbot_earnings']['month']['value']
                    elif metric_method == self.get_fee_earnings:
                        if operation == self.WITHDRAW:
                            metric_details[self.MONTH]['value'] = monthly_data.withdrawal_metrics['earnings']['month']['value']
                        elif operation == self.TIP:
                            metric_details[self.MONTH]['value'] = monthly_data.tip_metrics['earnings']['month']['value']

            elif metric_method == self.top_ten_active_groups:
                metric_details[self.MONTH] = {
                    'value': [],
                    'is_new': False,
                }
                qs_metrics = Metric.objects.order_by('date_recorded')
                monthly_data = qs_metrics.exclude(group_metrics__top_ten_active_groups__month__value=[])
                if monthly_data.exists():
                    monthly_data = monthly_data.last()
                    metric_details[self.MONTH]['value'] = monthly_data.group_metrics['top_ten_active_groups']['month']['value']
        
        return metric_details

    def get_game_manager_id(self):
        try:
            subscriber = Subscriber.objects.get(username=settings.MUTE_MANAGER_USERNAME)   
            if subscriber.token == settings.MUTE_MANAGER_TOKEN and subscriber.app_name == 'telegram':                         
                game_manager = User.objects.filter(telegram_id=subscriber.details['user_collector_id'])
                if game_manager.exists():
                    return game_manager.first().id
            
            logger.error("Subscriber info incorrect")
            return None
        except Subscriber.DoesNotExist as exc:
            logger.error("Subscriber does not exist")
            return None


    # DAILY, WEEKLY and MONTHLY fee earnings of certain operations
    # this function excludes games, since games have another way of computing earnings
    # this function only includes spicebot operations that have fees, such as tips and withdrawals
    def get_fee_earnings(self, days, operation):
        time = self.get_date_time(days, self.DAY)
        user_id = settings.TAX_COLLECTOR_USER_ID
        tax_collector = User.objects.get(id=user_id)
        operation = operation.upper()

        fees_received_by_collector = Transaction.objects.filter(
            operation=settings.TXN_OPERATION[operation],
            transaction_type='Incoming',
            user=tax_collector,
            slp_token=self.spice_token,
            date_created__gt=time
        )
        
        if fees_received_by_collector.exists():
            total_fees_collected = fees_received_by_collector.aggregate(Sum('amount'))['amount__sum']
        else:
            total_fees_collected = 0
            
        return self.round_or_zero(total_fees_collected)

    
#################### USERS #############################

    def get_user_metrics(self):
        return {
            'total_users': self.total_users(),
            'total_active_users': self.get_active_users(False),
            'total_new_users': self.get_daily_weekly_monthly_metric(
                self.total_new_users
            )
        }

    # DAILY total number of users
    def total_users(self):
        users = User.objects.filter(
            Q(transactions__isnull=False) |
            Q(last_private_message__isnull=False)
        )

        if users.exists():
            users = users.distinct('telegram_id')
        return users.count()

    # active users are described as users that have tipped, withdrawn, deposited, etc.
    # private messaged the spicebot or played a game within the past 1 WEEK.
    # set param return_qs to True if you want the queryset of the active_users
    # set param return_qs to False if you want to get the active users count
    def get_active_users(self, return_qs):
        past_week = self.get_date_time(7, self.DAY)
        active_users = User.objects.filter(
            transactions__date_created__gt=past_week,
            transactions__slp_token=self.spice_token,
        )

        if active_users.exists():
            active_users = active_users.distinct('telegram_id')
        else:
            active_users = User.objects.filter(last_private_message__gt=past_week)

        if return_qs:
            return active_users
        else:
            return active_users.count()

    # new users added (daily, weekly, and monthly)
    def total_new_users(self, days):
        time = self.get_date_time(days, self.DAY)
        
        metrics = Metric.objects.filter(
            date_recorded__gt=time
        )

        if metrics.exists():
            metric = metrics.order_by('date_recorded').first()
            return self.total_users() - metric.user_metrics['total_users']
        else:
            return 0


#################### GROUPS #############################

    def get_group_metrics(self):
        return {
            'total_groups': TelegramGroup.objects.count(),
            'total_active_groups': self.total_active_groups(),
            'top_ten_active_groups': self.get_daily_weekly_monthly_metric(
                self.top_ten_active_groups
            ),
            'total_new_groups': self.get_daily_weekly_monthly_metric(
                self.total_new_groups
            )
        }

    # active groups are described as groups that have spicebot transaction activities within a day
    def total_active_groups(self):
        past_day = self.get_date_time(24, self.HOUR)
        active_groups = TelegramGroup.objects.filter(
            transactions__date_created__gt=past_day
        )

        if active_groups.exists():
            active_groups = active_groups.distinct('chat_id')
            return active_groups.count()
        else:
            return 0

    # DAILY, WEEKLY, or MONTHLY top ten telegram groups with active spicebot users
    # Top ten is selected based on the number of active spicebot users
    def top_ten_active_groups(self, days):
        time = self.get_date_time(days, self.DAY)

        active_groups = TelegramGroup.objects.filter(
            transactions__date_created__gt=time 
        )

        if active_groups.exists():
            active_groups = active_groups.annotate(
                transactions_count=Count('transactions', filter=Q(transactions__date_created__gt=time)),
            ).order_by(
                '-transactions_count'
            )[:10]

            formatted_list = []
            for group in active_groups:
                formatted_list.append({
                    'title': group.title,
                    'users_count': group.users.count(),
                    'spicebot_transactions': group.transactions_count,
                    'date_created': group.date_created.strftime('%B %d %Y')
                })
            return formatted_list
        else:
            return []

    # new groups added (daily, weekly, and monthly)
    def total_new_groups(self, days):
        time = self.get_date_time(days, self.DAY)

        new_groups = TelegramGroup.objects.filter(
            date_created__gt=time,
        )

        return new_groups.count()



#################### WITHDRAWALS #############################

    def get_withdrawal_metrics(self):
        withdrawal_amounts = self.withdrawal_amounts()
        return {
            'total_withdrawals_count': self.total_withdrawal_count(),
            'total_successful_withdrawals': self.total_successful_withdrawals(),
            'total_failed_withdrawals': self.total_failed_withdrawals(),
            'avg_withdrawals_amount': withdrawal_amounts[self.AVG],
            'total_withdrawals_amount': withdrawal_amounts[self.TOTAL],
            'earnings': self.get_daily_weekly_monthly_metric(
                self.get_fee_earnings,
                **{
                    'operation': self.WITHDRAW
                }
            )
        }

    # DAILY total number of successful withdrawals
    def total_successful_withdrawals(self):
        past_day = self.get_date_time(24, self.HOUR)
        successful_withdrawals = Withdrawal.objects.filter(
            date_created__gt=past_day,
            date_completed__gt=past_day,
            slp_token=self.spice_token
        )
        return successful_withdrawals.count()

    # DAILY total number of failed withdrawals
    def total_failed_withdrawals(self):
        past_day = self.get_date_time(24, self.HOUR)
        failed_withdrawals = Withdrawal.objects.filter(
            date_created__gt=past_day,
            date_failed__gt=past_day,
            slp_token=self.spice_token
        )
        return failed_withdrawals.count()

    # DAILY average withdrawal amounts and
    # DAILY total withdrawals amount (both only for successful withdrawals)
    def withdrawal_amounts(self):
        past_day = self.get_date_time(24, self.HOUR)
        withdrawals_past_24_hrs = Withdrawal.objects.filter(
            date_created__gt=past_day,
            date_completed__gt=past_day,
            slp_token=self.spice_token
        )

        result_total = withdrawals_past_24_hrs.aggregate(Sum('amount'))['amount__sum']
        result_avg = withdrawals_past_24_hrs.aggregate(Avg('amount'))['amount__avg']

        return {
            self.TOTAL: self.round_or_zero(result_total),
            self.AVG: self.round_or_zero(result_avg)
        }

    # DAILY number of withdrawals (includes both successful and failed)
    def total_withdrawal_count(self):
        past_day = self.get_date_time(24, self.HOUR)
        withdrawals_past_24_hrs = Withdrawal.objects.filter(
            date_created__gt=past_day,
            slp_token=self.spice_token
        )
        return withdrawals_past_24_hrs.count()

#################### DEPOSITS #############################

    def get_deposit_metrics(self):
        deposits = self.deposits()
        big_deposits = self.big_deposits()
        
        return {
            'total_deposits_count': deposits[self.COUNT],
            'total_deposits_amount': deposits[self.TOTAL],
            'avg_deposits_amount': deposits[self.AVG],
            'total_big_deposits_count': big_deposits[self.COUNT],
            'total_big_deposits_amount': big_deposits[self.TOTAL],
            'avg_big_deposits_amount': big_deposits[self.AVG],
        }

    # DAILY total number of deposits,
    # DAILY total amount of deposits,
    # DAILY total average of deposits
    def deposits(self):
        past_day = self.get_date_time(24, self.HOUR)
        deposits_past_24_hrs = Deposit.objects.filter(
            date_created__gt=past_day,
            date_processed__gt=past_day,
            slp_token=self.spice_token
        )

        result_count = deposits_past_24_hrs.count()
        result_total = deposits_past_24_hrs.aggregate(Sum('amount'))['amount__sum']
        result_avg = deposits_past_24_hrs.aggregate(Avg('amount'))['amount__avg']
        
        return {
            self.COUNT: self.round_or_zero(result_count),
            self.TOTAL: self.round_or_zero(result_total),
            self.AVG: self.round_or_zero(result_avg)
        }

    # DAILY count of big deposits,
    # DAILY total amount of big deposits,
    # DAILY average of big deposits
    def big_deposits(self):
        past_day = self.get_date_time(24, self.HOUR)
        big_deposits = Deposit.objects.filter(
            date_created__gt=past_day,
            date_processed__gt=past_day,
            slp_token=self.spice_token,
            amount__gte=self.spice_token.big_deposit_threshold
        )
        
        result_count = big_deposits.count()
        result_total = big_deposits.aggregate(Sum('amount'))['amount__sum']
        result_avg = big_deposits.aggregate(Avg('amount'))['amount__avg']
        
        return {
            self.COUNT: self.round_or_zero(result_count),
            self.TOTAL: self.round_or_zero(result_total),
            self.AVG: self.round_or_zero(result_avg)
        }

#################### TIPPINGS #############################

    def get_tip_metrics(self):
        tip_metrics = self.tip()

        return {
            'total_tips_count': tip_metrics[self.COUNT],
            'total_tips_amount': tip_metrics[self.TOTAL],
            'avg_tips_amount': tip_metrics[self.AVG],
            'earnings': self.get_daily_weekly_monthly_metric(
                self.get_fee_earnings,
                **{
                    'operation': self.TIP
                }
            )
        }

    # DAILY total count of tips,
    # DAILY total amount of tip,
    # DAILY average amount,
    def tip(self):
        past_day = self.get_date_time(24, self.HOUR)
        tips = Transaction.objects.filter(
            operation=settings.TXN_OPERATION['TIP'],
            date_created__gt=past_day,
            slp_token=self.spice_token,
            transaction_type='Incoming'
        )

        result_count = tips.count()
        result_total = tips.aggregate(Sum('amount'))['amount__sum']
        result_avg = tips.aggregate(Avg('amount'))['amount__avg']
        
        return {
            self.COUNT: self.round_or_zero(result_count),
            self.TOTAL: self.round_or_zero(result_total),
            self.AVG: self.round_or_zero(result_avg)
        }
        
#################### RAINS #############################

    def get_rain_metrics(self):
        rain_metrics = self.rain()

        return {
            'total_rains_count': rain_metrics[self.COUNT],
            'total_rains_amount': rain_metrics[self.TOTAL],
            'avg_rains_amount': rain_metrics[self.AVG],
        }
    
    # DAILY total count of rains,
    # DAILY total amount of rain,
    # DAILY average amount,
    def rain(self):
        past_day = self.get_date_time(24, self.HOUR)
        rains = Rain.objects.filter(
            date_created__gt=past_day,
            slp_token=self.spice_token
        )

        result_count = rains.count()
        result_total = rains.aggregate(Sum('rain_amount'))['rain_amount__sum']
        result_avg = rains.aggregate(Avg('rain_amount'))['rain_amount__avg']
        
        return {
            self.COUNT: self.round_or_zero(result_count),
            self.TOTAL: self.round_or_zero(result_total),
            self.AVG: self.round_or_zero(result_avg)
        }

#################### WAGERBOT & JANKENBOT #############################

    def get_game_metrics(self):
        return {
            'jankenbot_earnings': self.get_daily_weekly_monthly_metric(
                self.game_earnings,
                **{
                    'operation': self.JANKEN
                }
            ),
            'jankenbot_bets_count': self.get_daily_weekly_monthly_metric(
                self.total_bets,
                **{
                    'operation': self.JANKEN
                }
            ),
            'jankenbot_avg_bet': self.average_bets(self.JANKEN),
            'wagerbot_earnings': self.get_daily_weekly_monthly_metric(
                self.game_earnings,
                **{
                    'operation': self.WAGER
                }
            ),
            'wagerbot_bets_count': self.get_daily_weekly_monthly_metric(
                self.total_bets,
                **{
                    'operation': self.WAGER
                }
            ),
            'wagerbot_avg_bet': self.average_bets(self.WAGER),
            'house_remaining_spice': self.total_house_spice(),
        }

    # DAILY, WEEKLY, MONTHLY bet counts
    def total_bets(self, days, game):
        time = self.get_date_time(days, self.DAY)
        user_id = self.get_game_manager_id()
        game_manager = User.objects.get(id=user_id)
        game = game.upper()

        win_txns_for_bot = Transaction.objects.filter(
            operation=settings.TXN_OPERATION[game],
            transaction_type='Incoming',
            user=game_manager,
            slp_token=self.spice_token,
            date_created__gt=time
        )

        return win_txns_for_bot.count()

    # DAILY, WEEKLY, MONTHLY earnings of wagerbot (dicemanagerbot) or jankenbot
    # specify game param as self.WAGER/settings.TXN_OPERATION['WAGER'] 
    # or self.JANKEN/settings.TXN_OPERATION['JANKEN'], respectively
    def game_earnings(self, days, game):
        time = self.get_date_time(days, self.DAY)
        user_id = self.get_game_manager_id()
        game_manager = User.objects.get(id=user_id)
        game = game.upper()

        win_txns_for_bot = Transaction.objects.filter(
            operation=settings.TXN_OPERATION[game],
            transaction_type='Incoming',
            user=game_manager,
            slp_token=self.spice_token,
            date_created__gt=time
        )

        lost_txns_for_bot = Transaction.objects.filter(
            operation=settings.TXN_OPERATION[game],
            transaction_type='Outgoing',
            user=game_manager,
            slp_token=self.spice_token,
            date_created__gt=time
        )
        
        total_win_amount = win_txns_for_bot.aggregate(Sum('amount'))['amount__sum']
        total_lose_amount = lost_txns_for_bot.aggregate(Sum('amount'))['amount__sum']
        result = 0

        try:
            result = total_win_amount - total_lose_amount
        except TypeError:
            if total_win_amount is None:
                result = total_lose_amount
            elif total_lose_amount is None:
                result = total_win_amount
            
        return self.round_or_zero(result)

    # DAILY game average bet amount
    # specify game param as self.WAGER/settings.TXN_OPERATION['WAGER'] 
    # or self.JANKEN/settings.TXN_OPERATION['JANKEN'], respectively
    def average_bets(self, game):
        past_day = self.get_date_time(24, self.HOUR)        
        user_id = self.get_game_manager_id()
        game_manager = User.objects.get(id=user_id)
        game = game.upper()

        game_txns = Transaction.objects.filter(
            operation=settings.TXN_OPERATION[game],
            transaction_type='Incoming',
            user=game_manager,
            slp_token=self.spice_token,
            date_created__gt=past_day
        )

        result = game_txns.aggregate(Avg('amount'))['amount__avg']
        return self.round_or_zero(result)

#################### HOUSE TOTAL SPICE LEFT #############################

    # DAILY total amount left in spice gamehouse
    def total_house_spice(self):
        game_manager_id = self.get_game_manager_id()
        balance = get_balance(game_manager_id, settings.SPICE_TOKEN_ID)
        return self.round_or_zero(balance)

    def compute_token_system_balance(self):
        text = f"""\n\n *Overall System Balances* :face_with_monocle:"""
        trs = Transaction.objects.order_by('user__id', 'slp_token_id','-date_created').distinct('user__id','slp_token__id')
        trs_ids = trs.values_list('id', flat=True)
        trans = Transaction.objects.filter(id__in=trs_ids)
        # Spice
        spice_balance = trans.filter(slp_token=1).aggregate(Sum('running_balance'))['running_balance__sum']
        text += f"""\n>• *SPICE*: `{spice_balance}`"""

        # HONK
        honk_balance = trans.filter(slp_token=3).aggregate(Sum('running_balance'))['running_balance__sum']    
        text += f"""\n>• *HONK*: `{honk_balance}`"""

        # ORB
        orb_balance = trans.filter(slp_token=17).aggregate(Sum('running_balance'))['running_balance__sum']    
        text += f"""\n>• *ORB*: `{orb_balance}`"""

        # DROP
        drop_balance = trans.filter(slp_token=4).aggregate(Sum('running_balance'))['running_balance__sum']    
        text += f"""\n>• *DROP*: `{drop_balance}`"""

        # MIST
        mist_balance = trans.filter(slp_token=10).aggregate(Sum('running_balance'))['running_balance__sum']
        text += f"""\n>• *MIST*: `{mist_balance}`"""

        # BCH
        bch_balance = trans.filter(slp_token=9).aggregate(Sum('running_balance'))['running_balance__sum']
        text += f"""\n>• *BCH*: `{bch_balance}`"""
        return  text    
