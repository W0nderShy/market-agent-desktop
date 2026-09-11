import time
import httpx
import pytest

from market_monitor.config import validate_items
from market_monitor.bitget import Bitget, MarketError
from market_monitor.service import Monitor

ITEM = {'symbol': 'BTCUSDT', 'category': 'SPOT'}

class Feed:
    def __init__(self):
        self.ts = int(time.time() * 1000)
        self.calls = 0
    def instruments(self, category, symbol=None):
        return [{**ITEM, 'status': 'online'}] if symbol in (None, 'BTCUSDT') else []
    def ticker(self, category, symbol):
        self.calls += 1
        if symbol == 'BADUSDT':
            raise MarketError('upstream_unavailable')
        return {'symbol': symbol, 'category': category, 'lastPrice': '123.45', 'volume24h': '9', 'ts': str(self.ts)}
    def candles(self, category, symbol):
        return [[str(self.ts), '120', '130', '110', '123.45', '9', '100']]
    def close(self): pass

def test_config_validation():
    assert validate_items([]) == []
    assert validate_items([ITEM, ITEM]) == [ITEM]
    for value in [[{'symbol': '../secret', 'category': 'SPOT'}], [{'symbol': 'BTCUSDT', 'category': 'MARGIN'}], 'bad']:
        with pytest.raises(ValueError): validate_items(value)

def test_transport_retry_and_sanitized_error():
    attempts = []
    def handler(request):
        attempts.append(request)
        if len(attempts) < 3: return httpx.Response(503, text='SECRET_SENTINEL')
        return httpx.Response(200, json={'code': '00000', 'data': [{**ITEM, 'lastPrice': '1'}]})
    client = Bitget(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    assert client.ticker('SPOT', 'BTCUSDT')['lastPrice'] == '1'
    assert len(attempts) == 3
    client = Bitget(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, text='SECRET_SENTINEL'))))
    with pytest.raises(MarketError) as error: client.instruments('SPOT')
    assert 'SECRET_SENTINEL' not in str(error.value)

def test_validation_persistence_dedup_and_stale(tmp_path):
    feed = Feed()
    monitor = Monitor(tmp_path, feed)
    assert monitor.status()['watchlist'] == []
    with pytest.raises(ValueError): monitor.set_watchlist([{'symbol': 'BADUSDT', 'category': 'SPOT'}])
    monitor.set_watchlist([ITEM])
    monitor.poll()
    assert len(monitor.status()['events']) == 1
    assert monitor.status()['watchlist'][0]['price'] == '123.45'
    last_poll = monitor.status()['service']['last_poll_ts']
    monitor.close()
    monitor = Monitor(tmp_path, feed)
    assert monitor.status()['service']['last_poll_ts'] == last_poll
    monitor.poll()
    assert len(monitor.status()['events']) == 1
    assert monitor.store.count_observations() == 1
    feed.ts -= 300000
    monitor.poll()
    assert monitor.status()['watchlist'][0]['error'] == 'stale_data'
    monitor.close()

def test_failure_isolation_and_persistent_checkpoint_resume(tmp_path):
    feed = Feed()
    monitor = Monitor(tmp_path, feed)
    monitor.store.set_watchlist([{'symbol': 'BADUSDT', 'category': 'SPOT'}, ITEM])
    monitor.poll()
    rows = monitor.status()['watchlist']
    assert rows[0]['error'] == 'upstream_unavailable'
    assert rows[1]['price'] == '123.45'
    config = {'configurable': {'thread_id': 'resume-test'}}
    monitor.graph.invoke({'item': ITEM}, config, interrupt_after=['collect'])
    assert monitor.graph.get_state(config).next == ('persist',)
    calls = feed.calls
    monitor.close()
    monitor = Monitor(tmp_path, feed)
    monitor.graph.invoke(None, config)
    assert feed.calls == calls
    assert monitor.graph.get_state(config).next == ()
    assert monitor.store.count_observations() == 1
    monitor.close()

def test_retry_after_bounded_and_removed_symbol_not_recreated(tmp_path):
    waits = []
    requests = []
    def handler(request):
        requests.append(request)
        if len(requests) == 1: return httpx.Response(429,headers={'Retry-After':'9999'})
        return httpx.Response(200,json={'code':'00000','data':[]})
    feed = Bitget(httpx.Client(transport=httpx.MockTransport(handler)),sleep=waits.append)
    feed.instruments('SPOT')
    assert waits == [5.0]
    monitor = Monitor(tmp_path,Feed())
    monitor.set_watchlist([ITEM])
    cfg = {'configurable':{'thread_id':'removed'}}
    monitor.graph.invoke({'item':ITEM},cfg,interrupt_after=['collect'])
    monitor.set_watchlist([])
    monitor.graph.invoke(None,cfg)
    assert monitor.store.events() == []
    monitor.close()
