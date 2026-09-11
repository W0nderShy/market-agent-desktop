import threading
import httpx
import pytest
from market_monitor.bitget import Bitget
from market_monitor.api import make_server
from market_monitor.service import Monitor

@pytest.fixture
def candle_api(tmp_path):
    state = {'rows': [
        ['1788954660000','10','12','9','11','5','50'],
        ['1788954600000','9','11','8','10','3','30'],
        ['1788954660000','10','13','9','12','6','60'],
    ], 'requests': []}
    def handler(request):
        state['requests'].append(request)
        return httpx.Response(200,json={'code':'00000','data':state['rows']})
    monitor = Monitor(tmp_path, Bitget(httpx.Client(transport=httpx.MockTransport(handler))))
    server = make_server(monitor,port=0)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}',headers={'X-Monitor-Token':(tmp_path/'api-token').read_text()},trust_env=False) as client:
        yield client,state
    server.shutdown()
    server.server_close()
    monitor.close()

@pytest.mark.parametrize('interval',['1m','5m','15m','1H','4H','1D'])
def test_chart_sorted_deduplicated_and_interval_forwarded(candle_api,interval):
    client,state = candle_api
    result = client.get('/api/candles',params={'category':'USDT-FUTURES','symbol':'BTCUSDT','interval':interval})
    assert result.status_code == 200
    body = result.json()
    assert body['symbol'] == 'BTCUSDT'
    assert body['category'] == 'USDT-FUTURES'
    assert body['interval'] == interval
    assert body['latest_candle_may_change'] is True
    assert body['items'] == [
        {'time':1788954600,'open':9.0,'high':11.0,'low':8.0,'close':10.0,'volume':3.0},
        {'time':1788954660,'open':10.0,'high':13.0,'low':9.0,'close':12.0,'volume':6.0},
    ]
    assert state['requests'][0].url.params['interval'] == interval

@pytest.mark.parametrize('query',['category=SPOT&symbol=BTCUSDT&interval=2m','category=SPOT','category=SPOT&symbol=../SECRET','category=BAD&symbol=BTCUSDT'])
def test_bad_chart_request_rejected_without_upstream(candle_api,query):
    client,state = candle_api
    assert client.get('/api/candles?'+query).status_code == 400
    assert state['requests'] == []

@pytest.mark.parametrize('row',[
    ['1788954660000','NaN','12','9','11','5','50'],
    ['1788954660000','10','12','9','Infinity','5','50'],
    ['1788954660000','10','8','9','11','5','50'],
    ['1788954660000','10','12','9','11','-5','50'],
    ['bad','10','12','9','11','5','50'],
    {'bad':'data'},
])
def test_invalid_upstream_chart_data_fails_safely(candle_api,row):
    client,state = candle_api
    state['rows'] = [row]
    result = client.get('/api/candles?category=SPOT&symbol=BTCUSDT')
    assert result.status_code == 502
    assert result.json() == {'error':'upstream_unavailable'}
