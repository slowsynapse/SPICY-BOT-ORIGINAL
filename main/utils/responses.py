
from main.models import SLPToken
from django.conf import settings
from django.utils import timezone


MESSAGES = {}


MESSAGES['deposit'] = """Depositing any tokens will credit your account with equivalent token points you can use for tipping other users.
\nTo proceed with deposit, you have to run this command again but include the <b>Token</b> you want to deposit. 
\nThe syntax for deposit command is:
\n<b>/deposit (token name).</b>
\n\nExample:
\n/deposit honk
\n\nThe bot will respond with an SLP address where you need to deposit your token. You can then deposit the token to that address any amount anytime.
\n\nImportant note!!! Make sure you only deposit the token you registered in the deposit command. Otherwise, the token you send will not be credited.
"""

MESSAGES['withdraw'] = """Withdrawing converts your SPICE Points to (Gifted) SPICE SLP Tokens. (Check /FAQs to learn more about gifted SPICE SLP Tokens)
\n\nThe proper syntax is:
\n/withdraw all "simpleledger_address"
\n\nExample:
\n/withdraw all simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
"""


WITHDRAW_TOKEN_FEES = '$WITHDRAW_TOKEN_FEES$'
MESSAGES['withdraw_telegram'] = f"""Withdrawing converts any of your cryptocurrency points to (Gifted) Tokens.
\n\nThe syntax for withdrawal command is:
\n<b>/withdraw (amount) (token name) (simpleledger address)</b>
\n\n<b>Examples:</b>
\n/withdraw 1000 SPICE simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
\n/withdraw 5,000 DROP simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer

\nWithdrawals require a small fee calculated from a percentage of the withdrawn amount. The fee differs from token to token as follows:
{WITHDRAW_TOKEN_FEES}
"""

RAIN_MIN = '$ALLOWED SYMBOLS HERE$'
MESSAGES['rain'] = f"""To rain any <b>Token</b>, simply type the following commands in any group that has Spicebot:
\nExamples:\n
<b>rain 5 people 100 (token name) each</b>\n(100 (token name) to each of 5 people)\n
<b>rain 5 people 500 (token name) total</b>\n(divides 500 tokens in total between 5 people)\n
<b>rain 5 people 100 (token name)</b>\n(defaults to "total", thus 5 people would get 100 tokens each)\n\nOR\n\n
Examples:\n\n<b>rain 5 people 100 (token name) each 3/5 pof</b>\n\n<b>rain 5 people 500 (token name) total 3/5 pof</b>
\n\nMinimum amount of tokens in total to invoke rain are: \n{RAIN_MIN}"""

MESSAGES['twitter'] = """To transfer SPICE from this account to a twitter account, simply type the following command below:
\ntwitter [twitter_username] [amount]

<b>Examples:</b>\n
twitter @luckyme99 34
twitter @luckyme99 100.25
twitter @luckyme99 .77
"""

MESSAGES['reddit'] = """To transfer SPICE to from this account to a reddit account, simply type the following command below:
\nreddit [reddit_username] [amount]

<b>Examples:</b>\n
reddit myusername 34
reddit myusername 100.25
reddit myusername .77
"""

MESSAGES['telegram'] = """To transfer SPICE from this account to a telegram account, simply type the following comand below:
\ntelegram [telegram_username] [amount]

<b>Examples:</b>\n
telegram @chillyiceberg 34
telegram @chillyiceberg 100.25
telegram @chillyiceberg .77
"""

MESSAGES['enablefeature'] = """To enable a feature, type the following command:
\nenable [feature]

<b>List of features that can be enabled:</b>\n
withdraw
tipping
deposit
transfer
"""

MESSAGES['disablefeature'] = """To disable a feature, type the following command:
\ndisable [feature]

<b>List of features that can be disabled:</b>\n
withdraw
tipping
deposit
transfer
"""

PILLORY_EMOJIS = '$PILLORY EMOJIS HERE$'
UNMUTE_EMOJIS = '$UNMUTE EMOJIS HERE$'

MESSAGES['pillory'] = f"""<b>Pillory</b>, gives the community the ability to mute annoying users.
\nMuting someone in a group requires two things:
\n1. I, @{settings.TELEGRAM_BOT_USER}, must be an admin of the group
2. The group must be a <b>supergroup</b>

-----------------------------------

Admin commands:

<b>default pillory [amount] spice</b>
(sets the group default pillory fee)

<b>default pillory [time] [mins/hrs/days]</b>
(sets the group default pillory time. minimum of 5 for mins, and 1 for hrs & days)

<b>set pillory @username [amount] spice</b> 
(sets the amount required to pillory that user)

<b>unmute @username</b> 
(unmute user override without payment. rains the unmuted payment if there is any.)

<b>pillory [on/off]</b>
(enable or disable pillory feature in a group)

-----------------------------------

General (public) pillory commands:

<b>pillory list</b>
(shows those who have money thrown towards them to be muted)

<b>mute list</b>
(shows users currently muted and remaining time)

<b>default pillory fee</b>
(see the default pillory cost for the group)

<b>default pillory time</b>
(see the default pillory time for the group)

<b>pillory @username [amount] spice</b>
(contribute spice towards muting them)

<b>unmute @username [amount] spice</b>
(contribute spice towards unmuting a user)

<b>throw [emoji] @username</b>
(throw selected food emojis to prolong a muted user's mute duration)
{PILLORY_EMOJIS}
(throw selected heart emojis to lessen a muted user's mute duration)
{UNMUTE_EMOJIS}
-----------------------------------


Default mute fee for every user is {settings.INITIAL_MUTE_PRICE} \U0001f336 SPICE \U0001f336. The collected SPICE is rained to the group, except for muted users.


<b>Note</b>: No one can do any mute operations to any admin.
"""

MESSAGES['tap'] = MESSAGES['faucet'] = """ test """
MESSAGES['commands'] = """What can I help you with?\n
Here are a list of my commands:  \U0000270f

\n<b>Spicebot Tipping in Telegram Groups</b>\n
There are two ways to reward other people with SPICE -- tip and rain. Click on the commands below to know more:
<b>/tip</b> = for information on tipping SLP tokens to others
<b>/rain</b> = for information on raining SLP tokens on others

\n<b>Balance Inquiry</b>\n
Command formats for balance inquiry:
<b>/balance</b> = to show balances of all SLP tokens
<b>/balance (token)</b> = to show balance on a specific SLP token
<b>/balance all</b> = to show balances of all SLP tokens

\n<b>Token Management</b>\n
<b>/tokens</b> = list all supported tokens
<b>/deposit</b> = for information on depositing
<b>/withdraw</b> = for information on withdrawing SLP tokens

<b>(for admins only)</b>
<b>/tipswitch</b> = for information how to disable tipping on a specified token in a group

\n<b>Faucet</b>\n
<b>/tap faucet [name of token]</b> = Redeem daily bounty from any preferred tokens. \n

\n<b>Buy Tokens</b>\n
Command format:
<b>/buy [amount] [token]</b>

\n<b>SLP-SEP20 Bridge</b>\n
Command format:
<b>/bridge swap [amount] [token] [sep20-address]</b>

\n<a href='https://spicetoken.org/bot_faq/'>Learn more about SpiceBot!</a>
"""
if 'sphere' in settings.INSTALLED_APPS:
    MESSAGES['commands'] += """\n<a href='https://enter-the-sphere.com/assets/EntertheSphereHandbook.pdf'>How To Play Enter the Sphere?</a>"""

MESSAGES['commands'] += """\n<a href='https://t.me/spicetoken'>Need further assistance?</a>"""

ALLOWED_SYMBOLS = '$ALLOWED SYMBOLS HERE$'
TOKEN_TIP_FEES = '$TOKEN_TIP_FEES$'
MESSAGES['tip'] = f"""To tip someone with any accepted token points,  simply <b>reply</b> to any of their messages with any of this command:

<b>.... tip [amount] [token] ...</b>
\n<b>... [amount] spice ... </b>

\n(Note that if token is not specified in the first command, your <b>SPICE</b> points will be used to tip the user.)

\n You can also tip users with <b>SPICE</b> by replying with the following emojis:
{ALLOWED_SYMBOLS}

\n Tipping deducts a fee if the tip amount exceeds a certain limit per token. The fee is based upon a percentage of the amount tipped:
{TOKEN_TIP_FEES}

(As of now, you could only tip with emoji using your <b>SPICE</b> tokens.)
"""

MESSAGES['tip_token_switch'] = f"""If you want to disable tipping of a specific SLP Token in your group, simply run the command:

<b>[slp_token] tipping [on/off]</b>

Example:
<b>drop tipping off</b>
<b>honk tipping on</b>
"""

def get_response(key):
    if key in MESSAGES.keys():
        return MESSAGES[key]

def get_maintenance_response(feature):
    feature = feature.lower().capitalize()
    return f"""\U000026a0   <b>{feature}</b> is temporarily disabled.  \U000026a0\n\n"""

def get_slp_token_list(user):
    slp_tokens = SLPToken.objects.all()
    if slp_tokens:
        counter = 1
        response = "💰  Tokens Currently Supported:  💰\n"
        for slp_token in slp_tokens:
            if slp_token.publish or (not slp_token.publish and user.telegram_id in slp_token.allowed_devs):
                if slp_token.date_delisted:
                    if slp_token.date_delisted < timezone.now():
                        continue
                response += f"\n<b>{counter}. {slp_token.name}  {slp_token.emoji}</b>"
                counter = counter + 1
    else:
        response = "There are no tokens that we support as of now."

    return response

def get_rain_response():
    message = MESSAGES['rain']
    slp_tokens = SLPToken.objects.all()
    token_list = ''

    if slp_tokens:
        
        counter = 1
        for slp_token in slp_tokens:
            token_list+=f'\n<b>{counter}. {slp_token.name} = {slp_token.min_rain_amount} {slp_token.emoji}</b>'
            counter = counter + 1
    else:
        token_list = "(There are no tokens that we support as of now.)"

    message = message.replace(RAIN_MIN, token_list)

    return message 

def get_pillory_faq():
    message = MESSAGES['pillory']
    unmute_emojis_text = '\n'
    pillory_emojis_text = '\n'

    for emoji in settings.ALLOWED_PILLORY_EMOJIS:
        time_text = f"{settings.ALLOWED_PILLORY_EMOJIS[emoji]} minutes"
        if emoji == "\U0001f987":
            time_text = "1 week"
            
        pillory_emojis_text += f"{emoji}  (+{time_text})\n"

    for emoji in settings.ALLOWED_UNMUTE_EMOJIS:
        unmute_emojis_text += f"{emoji}  (-{settings.ALLOWED_UNMUTE_EMOJIS[emoji]} minutes)\n"

    message = message.replace(PILLORY_EMOJIS, pillory_emojis_text)
    message = message.replace(UNMUTE_EMOJIS, unmute_emojis_text)
    return message 


def get_int_or_float(amount):
    if type(amount) is float:
        if amount.is_integer():
            amount = int(amount)
    return amount


def get_tip_response():
    message = MESSAGES['tip']
    accepted_symbols_text = '\n'
    token_fees = '\n'

    allowed_symbols = SLPToken.objects.get(name='SPICE').tip_emojis
    for symbol in allowed_symbols:
        if allowed_symbols[symbol] != 0:
            amount_text = f"{allowed_symbols[symbol]} tokens"

            if allowed_symbols[symbol] == 'undefined':
                amount_text = f"tips random amount of tokens"

            accepted_symbols_text += f"{symbol} = {amount_text}\n"

    for token in SLPToken.objects.filter(publish=True, date_delisted__isnull=True):
        perc_fee = get_int_or_float(token.tip_percentage_fee * 100)
        threshold = get_int_or_float(token.tip_threshold)
        token_fees += f"{token.name} = {perc_fee}%  (Starts on: {threshold})\n"

    message = message.replace(ALLOWED_SYMBOLS, accepted_symbols_text)
    message = message.replace(TOKEN_TIP_FEES, token_fees)

    return message 

def get_withdraw_response():
    message = MESSAGES['withdraw_telegram']
    token_fees = '\n'

    for token in SLPToken.objects.all():
        perc_fee = get_int_or_float(token.withdrawal_percentage_fee * 100)
        token_fees += f'{token.name} = {perc_fee}%\n'
    
    message = message.replace(WITHDRAW_TOKEN_FEES, token_fees)
    
    return message
