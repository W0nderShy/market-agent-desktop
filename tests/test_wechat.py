import json

from market_monitor.wechat import WeChatBridge, _base_url


class Response:
    def __init__(self, data): self.data=data
    def raise_for_status(self): pass
    def json(self): return self.data


class Transport:
    def __init__(self): self.calls=[];self.send_ret=-2;self.messages=[]
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if 'get_bot_qrcode' in url:return Response({'qrcode':'private-code','qrcode_img_content':'https://example.invalid/qr'})
        if 'getupdates' in url:return Response({'ret':0,'msgs':self.messages,'get_updates_buf':'next-cursor'})
        if 'sendmessage' in url:return Response({'ret':self.send_ret})
        raise AssertionError(url)
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return Response({'status':'confirmed','bot_token':'private-bot-token','ilink_user_id':'my-user','ilink_bot_id':'my-bot','baseurl':'https://ilinkai.weixin.qq.com'})


def task(as_of=1000, buy=60):
    return {'id':'USDT-FUTURES:ZECUSDT','symbol':'ZECUSDT','category':'USDT-FUTURES','interval':'15m','enabled':True,
            'probabilities':{'as_of':as_of,'percentages':{'buy':buy,'hold':30,'sell':100-buy-30}},
            'previous':{'conclusion':'尚待验证','recommendation':'观察放量确认'},'notification':{'id':'research-1'}}


def test_qr_pairing_and_secret_never_returned(tmp_path):
    wire=Transport();clock=[1800000000]
    bridge=WeChatBridge(tmp_path,clock=lambda:clock[0],transport=wire)
    try:
        login=bridge.start_login()
        assert login['image'].startswith('data:image/png;base64,')
        assert 'private-code' not in str(login)
        assert bridge.poll_login()=={'status':'confirmed','connected':True}
        assert 'private-bot-token' not in json.dumps(bridge.status())
        assert bridge._credentials()['token']=='private-bot-token'
        if __import__('os').name=='nt':assert b'private-bot-token' not in bridge.secret_path.read_bytes()
        assert bridge.configure({'enabled':True})['enabled']
    finally:bridge.close()


def test_pending_survives_expired_context_and_sends_after_new_message(tmp_path):
    wire=Transport();clock=[1800000000]
    bridge=WeChatBridge(tmp_path,clock=lambda:clock[0],transport=wire)
    try:
        bridge.start_login();bridge.poll_login();bridge.configure({'enabled':True})
        bridge.observe([task()]);bridge.observe([task()])
        assert len(bridge.status()['messages'])==1
        assert bridge.dispatch() is False  # no user context yet
        wire.messages=[{'message_id':123,'from_user_id':'my-user','context_token':'fresh-context',
                        'item_list':[{'type':1,'text_item':{'text':'状态'}}]}]
        assert bridge.receive_once()==['状态']
        assert bridge.receive_once()==[]  # inbox idempotency
        assert bridge.dispatch() is False
        assert bridge.status()['messages'][0]['error']=='context_expired'
        assert bridge.status()['messages'][0]['status']=='pending'
        clock[0]+=10
        wire.messages=[{'message_id':124,'from_user_id':'my-user','context_token':'new-context','item_list':[]}]
        bridge.receive_once();wire.send_ret=0
        assert bridge.dispatch() is True
        assert bridge.status()['messages'][0]['status']=='sent'
        outbound=[call for call in wire.calls if 'sendmessage' in call[0]][-1][1]['json']['msg']
        assert outbound['context_token']=='new-context'
        assert 'BUY 60.0%' in outbound['item_list'][0]['text_item']['text']
    finally:bridge.close()


def test_rejects_untrusted_redirect():
    import pytest
    with pytest.raises(ValueError):_base_url('https://evil.invalid')


def test_owner_message_can_request_status_and_set_research_direction(tmp_path):
    class Tracking:
        def __init__(self):self.notes=[]
        def status(self):return {'tasks':[task()]}
        def configure(self,body):self.notes.append(body)
    wire=Transport();bridge=WeChatBridge(tmp_path,transport=wire)
    try:
        tracking=Tracking()
        bridge.handle_inbound(['状态','研究 ZECUSDT 核验量能能否延续'],tracking)
        assert tracking.notes==[{'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':True,'note':'核验量能能否延续'}]
        rows=bridge.db.execute('SELECT body FROM outbox ORDER BY rowid').fetchall()
        assert 'BUY 60.0%' in rows[0]['body']
        assert '已将你的研究方向' in rows[1]['body']
    finally:bridge.close()


def test_ambiguous_send_is_not_retried_or_requeued(tmp_path):
    wire=Transport();wire.send_ret=1;clock=[1800000000]
    bridge=WeChatBridge(tmp_path,clock=lambda:clock[0],transport=wire)
    try:
        bridge.start_login();bridge.poll_login();bridge.configure({'enabled':True})
        wire.messages=[{'message_id':1,'from_user_id':'my-user','message_type':1,
                        'context_token':'context','item_list':[]}]
        bridge.receive_once();bridge.observe([task()])
        assert bridge.dispatch() is False
        assert bridge.status()['messages'][0]['status']=='unknown'
        send_count=sum('sendmessage' in url for url,_ in wire.calls)
        clock[0]+=3600
        bridge.observe([task(as_of=1900)])
        assert len(bridge.status()['messages'])==1
        assert bridge.dispatch() is False
        assert sum('sendmessage' in url for url,_ in wire.calls)==send_count
    finally:bridge.close()


def test_only_user_messages_enter_inbox(tmp_path):
    wire=Transport();bridge=WeChatBridge(tmp_path,transport=wire)
    try:
        bridge.start_login();bridge.poll_login();bridge.configure({'enabled':True})
        wire.messages=[{'message_id':2,'from_user_id':'my-user','message_type':2,'context_token':'context',
                        'item_list':[{'type':1,'text_item':{'text':'echo'}}]}]
        assert bridge.receive_once()==[]
    finally:bridge.close()


def test_repeated_user_text_with_new_message_id_does_not_repeat_reply(tmp_path):
    wire=Transport();clock=[1800000000]
    bridge=WeChatBridge(tmp_path,clock=lambda:clock[0],transport=wire)
    try:
        bridge.start_login();bridge.poll_login();bridge.configure({'enabled':True})
        wire.messages=[{'message_id':1,'from_user_id':'my-user','message_type':1,'context_token':'a',
                        'item_list':[{'type':1,'text_item':{'text':'状态'}}]}]
        assert bridge.receive_once()==['状态']
        clock[0]+=5
        wire.messages=[{'message_id':2,'from_user_id':'my-user','message_type':1,'context_token':'b',
                        'item_list':[{'type':1,'text_item':{'text':'状态'}}]}]
        assert bridge.receive_once()==[]
        assert bridge.db.execute('SELECT count(*) FROM inbox').fetchone()[0]==2
    finally:bridge.close()
