import json
import threading
import httpx
import pytest
from market_monitor.api import make_server, InstanceLock
from market_monitor.service import Monitor
from test_foundation import Feed, ITEM

def test_token_origin_and_watchlist_api(tmp_path):
    monitor = Monitor(tmp_path, Feed())
    server = make_server(monitor, port=0)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    token = (tmp_path/'api-token').read_text()
    try:
        with httpx.Client(base_url=base, trust_env=False) as c:
            assert c.get('/api/status').status_code == 401
            assert c.get('/api/tracking').status_code == 401
            headers = {'X-Monitor-Token':token}
            assert c.get('/api/status',headers={**headers,'Origin':'https://evil.invalid'}).status_code == 403
            assert c.get('/api/status',headers=headers).json()['watchlist'] == []
            assert c.put('/api/watchlist',headers=headers,json={'items':[ITEM]}).status_code == 200
            assert c.put('/api/watchlist',headers=headers,json={'items':[{'symbol':'BADUSDT','category':'SPOT'}]}).status_code == 400
            assert c.get('/api/instruments?category=SPOT&symbol=BTCUSDT',headers=headers).json()['items'][0]['symbol'] == 'BTCUSDT'
            assert c.put('/api/tracking/configure',headers=headers,json={'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':'yes'}).status_code == 400
            assert c.put('/api/tracking/configure',headers=headers,json={'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':True}).status_code == 200
            assert c.get('/api/tracking',headers=headers).json()['tasks'][0]['enabled'] is True
            assert c.get('/api/tracking/history?task=USDT-FUTURES%3AZECUSDT',headers=headers).json()['items'] == []
            assert c.get('/api/tracking/history?task=USDT-FUTURES%3AZECUSDT').status_code == 401
            assert c.get('/api/tracking/history?task=bad',headers=headers).status_code == 400
            assert c.get('/api/wechat').status_code == 401
            assert c.get('/api/wechat',headers=headers).json()['connected'] is False
            assert c.put('/api/wechat/configure',headers=headers,json={'enabled':True}).status_code == 400
            assert c.put('/api/wechat/configure',headers=headers,json={'cadence_hours':3}).json()['cadence_hours'] == 3
            assert c.post('/api/wechat/login/status',headers=headers,json={}).json()['status']=='expired'
            assert c.post('/api/tracking/complete',headers=headers,json={'id':'missing','lease':'missing','result':{}}).json()['accepted'] is False
            assert c.post('/api/poll',headers=headers).status_code == 202
            assert c.post('/api/shutdown',headers=headers).status_code == 202
            thread.join(timeout=3)
            assert not thread.is_alive()
    finally:
        server.shutdown()
        server.server_close()
        monitor.close()

def test_exclusive_runtime_lock_and_release(tmp_path):
    with InstanceLock(tmp_path):
        with pytest.raises(RuntimeError):
            with InstanceLock(tmp_path): pass
    with InstanceLock(tmp_path): pass

def test_retention_expires_collection_events(tmp_path):
    monitor = Monitor(tmp_path, Feed())
    monitor.set_watchlist([ITEM])
    monitor.poll()
    monitor.store.db.execute('UPDATE observations SET collected_ts=1')
    monitor.store.db.execute('UPDATE events SET created_ts=1')
    monitor.store.db.commit()
    monitor.cleanup()
    assert monitor.store.count_observations() == 0
    assert len(monitor.store.events()) == 0
    monitor.store.db.execute("UPDATE events SET status='consumed'")
    monitor.store.db.commit()
    monitor.cleanup()
    assert monitor.store.events() == []
    monitor.close()
