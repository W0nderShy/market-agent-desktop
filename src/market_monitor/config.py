import re

CATEGORIES = {'SPOT', 'USDT-FUTURES', 'COIN-FUTURES', 'USDC-FUTURES'}

def validate_items(items):
    if not isinstance(items, list) or len(items) > 50:
        raise ValueError('watchlist_requires_list_max_50')
    result = []
    for item in items:
        if (not isinstance(item, dict) or set(item) != {'symbol', 'category'}
                or item['category'] not in CATEGORIES
                or not isinstance(item['symbol'], str)
                or not re.fullmatch(r'[A-Z0-9]{3,32}', item['symbol'])):
            raise ValueError('invalid_watchlist_item')
        if item not in result:
            result.append(dict(item))
    return result
