import time
import math
from email.utils import parsedate_to_datetime
import httpx
from .config import CATEGORIES, validate_items

CHART_INTERVALS = {'1m','5m','15m','1H','4H','1D'}

def chart_candles(feed, category, symbol, interval='1m'):
    """Normalize public market candles; the latest bar can still be forming."""
    validate_items([{'category':category,'symbol':symbol}])
    if interval not in CHART_INTERVALS:
        raise ValueError('invalid_interval')
    rows = feed.candles(category,symbol,interval=interval,limit=300)
    items = {}
    try:
        for row in rows:
            if not isinstance(row,(list,tuple)) or len(row) < 6:
                raise ValueError()
            stamp = int(row[0])
            values = [float(value) for value in row[1:6]]
            opening,high,low,close,volume = values
            if (stamp <= 0 or stamp % 1000 != 0 or stamp > int(time.time()*1000)+30000
                    or not all(math.isfinite(value) for value in values)
                    or min(opening,high,low,close) <= 0 or volume < 0
                    or high < max(opening,close,low) or low > min(opening,close,high)):
                raise ValueError()
            seconds = stamp // 1000
            items[seconds] = dict(zip(('time','open','high','low','close','volume'),[seconds,*values]))
    except (ValueError,TypeError,OverflowError):
        raise MarketError('invalid_candles') from None
    return {'items':[items[key] for key in sorted(items)],'symbol':symbol,'category':category,
            'interval':interval,'latest_candle_may_change':True}

class MarketError(Exception):
    pass

class Bitget:
    def __init__(self, client=None, sleep=time.sleep):
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)
        self.sleep = sleep

    def _get(self, endpoint, category, symbol=None, **extra):
        if category not in CATEGORIES:
            raise ValueError('invalid_category')
        if symbol:
            validate_items([{'category': category, 'symbol': symbol}])
        params = {'category': category, **extra}
        if symbol: params['symbol'] = symbol
        for attempt in range(3):
            try:
                response = self.client.get('https://api.bitget.com/api/v3/market/' + endpoint, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        delay = 0.5 * 2 ** attempt
                        retry_after = response.headers.get('Retry-After')
                        if retry_after:
                            try: delay = float(retry_after)
                            except ValueError:
                                try: delay = parsedate_to_datetime(retry_after).timestamp()-time.time()
                                except (ValueError,TypeError,OverflowError): pass
                        self.sleep(max(0,min(5,delay)) if math.isfinite(delay) else 5)
                        continue
                    raise MarketError('upstream_unavailable')
                if response.status_code != 200:
                    raise MarketError('upstream_rejected')
                body = response.json()
                if body.get('code') != '00000':
                    raise MarketError('upstream_rejected')
                if not isinstance(body.get('data'), list):
                    raise MarketError('invalid_response')
                return body['data']
            except httpx.TransportError:
                if attempt == 2: raise MarketError('network_error') from None
                self.sleep(0.5 * 2 ** attempt)
            except (ValueError, AttributeError):
                raise MarketError('invalid_response') from None

    def instruments(self, category, symbol=None):
        return self._get('instruments', category, symbol)

    def ticker(self, category, symbol):
        rows = self._get('tickers', category, symbol)
        for row in rows:
            if isinstance(row,dict) and row.get('symbol') == symbol and row.get('category') == category:
                return row
        raise MarketError('symbol_unavailable')

    def candles(self, category, symbol, interval='1m', limit=60):
        if interval not in CHART_INTERVALS or not isinstance(limit,int) or not 1 <= limit <= 1000:
            raise ValueError('invalid_candle_parameters')
        return self._get('candles', category, symbol, interval=interval, limit=str(limit))

    def close(self):
        self.client.close()
