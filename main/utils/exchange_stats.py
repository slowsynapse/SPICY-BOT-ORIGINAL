from coinex.coinex import CoinEx
from django.conf import settings
import requests

coinex = CoinEx(settings.COINEX_ACCESS_ID, settings.COINEX_SECRET)


def get_price_change(token):
    if token == 'spice':
        url = 'https://api.coinex.com/v1/market/ticker?market=spiceusdt'
    elif token == 'bch':
        url = 'https://api.coinex.com/v1/market/ticker?market=bchusdt'
    resp = requests.get(url, timeout=300)
    data = resp.json()['data']['ticker']
    last = float(data['last'])
    open_24hr = float(data['open'])
    pct = ((last - open_24hr) / open_24hr) * 100
    pct_fmt = '{:0.2f}'.format(pct)
    if pct >= 0:
        pct_fmt = f'+{pct_fmt}%'
    else:
        pct_fmt = f'{pct_fmt}%'
    return pct_fmt


def get_stats(token_name='spice'):
    message = ''
    if token_name == 'spice':
        spice_stats = coinex.market_ticker('SPICEBCH')
        price_sats = float(spice_stats['ticker']['last']) * 100000000
        price_sats = int(round(price_sats, 0))
        price_bch = price_sats / 100000000
        price_bch_str = '{:.8f}'.format(price_bch)

        bch_stats = coinex.market_ticker('BCHUSDT')
        usd_per_bch = float(bch_stats['ticker']['last'])
        price_usd = usd_per_bch * price_bch
        price_usd_str = '{:.5f}'.format(price_usd)

        market_cap = 10**9 * price_usd
        market_cap_str = '{:,}'.format(int(round(market_cap)))

        last_24hrs = get_price_change('spice')

        message_1 = "SPICE @ <a href='https://www.coinex.com/exchange/spice-bch' style='text-decoration: none;'>Coinex</a>"
        message_2 = '\n--------<code>\n* Price:\n  BCH: {0}\n  USD: ${1}\n  24hr \u0394: {2}\n* Market cap:\n  ${3}</code>'.format(
            price_bch_str,
            price_usd_str,
            last_24hrs,
            market_cap_str
        )
        message_3 = "\n--------\nClick <a href='https://www.coinex.com/register?refer_code=drcmf&lang=en_US' style='text-decoration: none;'>here</a> to start trading"
        message = message_1 + message_2 + message_3

    if token_name == 'bch':
        bch_stats = coinex.market_ticker('BCHUSDT')
        usd_per_bch = float(bch_stats['ticker']['last'])

        url = 'https://api.diadata.org/v1/supply/BCH'
        resp = requests.get(url)
        if resp.status_code == 200:
            circulating_supply = resp.json()['CirculatingSupply']
            market_cap = int(circulating_supply) * usd_per_bch
            market_cap_str = '{:,}'.format(int(round(market_cap)))

            last_24hrs = get_price_change('bch')

            message_1 = "BCH @ <a href='https://www.coinex.com/exchange/bch-usdt' style='text-decoration: none;'>Coinex</a>"
            message_2 = '\n--------<code>\n* Price:\n  USD: ${0}\n  24hr \u0394: {1}\n* Market cap:\n  ${2}</code>'.format(
                str(usd_per_bch),
                last_24hrs,
                market_cap_str
            )
            message_3 = "\n--------\nClick <a href='https://www.coinex.com/register?refer_code=drcmf&lang=en_US' style='text-decoration: none;'>here</a> to start trading"
            message = message_1 + message_2 + message_3

    return message
