"""Official Tencent iLink personal-WeChat bridge for tracking notifications.

Protocol reference: https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol_zh_CN.md
This deliberately handles text only. The service must never claim delivery on a
nonzero business return code, including an expired context token (ret=-2).
"""
import base64
import ctypes
import io
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

API = 'https://ilinkai.weixin.qq.com'
VERSION = '2.4.9'
CLIENT_VERSION = (2 << 16) | (4 << 8) | 9


def _protect(data, decrypt=False):
    """Bind the local bot credential to the current Windows account via DPAPI."""
    if os.name!='nt':return data
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]
    source=ctypes.create_string_buffer(data)
    incoming=Blob(len(data),ctypes.cast(source,ctypes.POINTER(ctypes.c_byte)))
    outgoing=Blob()
    crypt=ctypes.windll.crypt32
    method=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    method.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    method.restype=wintypes.BOOL
    if not method(ctypes.byref(incoming),None,None,None,None,0,ctypes.byref(outgoing)):
        raise OSError('local_credential_protection_failed')
    try:return ctypes.string_at(outgoing.data,outgoing.size)
    finally:
        free=ctypes.windll.kernel32.LocalFree
        free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
        free(ctypes.cast(outgoing.data,ctypes.c_void_p))


def _base_url(value):
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('invalid_ilink_endpoint')
    if parsed.hostname != 'ilinkai.weixin.qq.com' and not parsed.hostname.endswith('.weixin.qq.com'):
        raise ValueError('invalid_ilink_endpoint')
    return value.rstrip('/')


class WeChatBridge:
    def __init__(self, runtime, clock=time.time, transport=None):
        self.runtime = Path(runtime);self.runtime.mkdir(parents=True,exist_ok=True)
        self.clock = clock
        self.lock = threading.RLock()
        self.transport = transport or httpx.Client(timeout=40,trust_env=False,follow_redirects=False)
        self.owns_transport = transport is None
        self.secret_path = self.runtime/('wechat-ilink.dpapi' if os.name=='nt' else 'wechat-ilink.json')
        self.db = sqlite3.connect(self.runtime/'wechat.sqlite3',check_same_thread=False,timeout=15)
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,task TEXT,created REAL,due REAL,status TEXT,attempts INTEGER,body TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY,created REAL,text TEXT);
        """)
        with self.db:
            self.db.execute("UPDATE outbox SET status='unknown',error='delivery_unknown' WHERE status='pending' AND error IS NOT NULL AND error!='context_expired'")
        self.login=None

    def _get(self,key,default=None):
        row=self.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _put(self,key,value):
        self.db.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))

    def _credentials(self):
        try:return json.loads(_protect(self.secret_path.read_bytes(),decrypt=True).decode())
        except (OSError,ValueError):return None

    def _headers(self,token=None,qr_status=False):
        headers={'iLink-App-Id':'bot','iLink-App-ClientVersion':str(CLIENT_VERSION)}
        if not qr_status:
            headers.update({'Content-Type':'application/json','AuthorizationType':'ilink_bot_token',
                            'X-WECHAT-UIN':base64.b64encode(str(int.from_bytes(os.urandom(4),'big')).encode()).decode()})
            if token:headers['Authorization']='Bearer '+token
        return headers

    def _post(self,base,path,body,token=None,timeout=15):
        response=self.transport.post(_base_url(base)+path,json=body,headers=self._headers(token),timeout=timeout)
        response.raise_for_status()
        data=response.json()
        if not isinstance(data,dict):raise ValueError('invalid_ilink_response')
        return data

    def start_login(self):
        data=self._post(API,'/ilink/bot/get_bot_qrcode?bot_type=3',{'local_token_list':[]})
        qr=data.get('qrcode');content=data.get('qrcode_img_content')
        if not isinstance(qr,str) or not qr or not isinstance(content,str) or not content:raise ValueError('invalid_qr_response')
        self.login={'qrcode':qr,'content':content,'started':self.clock(),'base':API}
        return {'status':'wait','image':self._qr_png(content)}

    @staticmethod
    def _qr_png(content):
        import qrcode
        image=qrcode.make(content)
        stream=io.BytesIO();image.save(stream,format='PNG')
        return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()

    def poll_login(self,verify_code=None):
        login=self.login
        if not login or self.clock()-login['started']>300:return {'status':'expired'}
        if verify_code is not None and (not isinstance(verify_code,str) or not verify_code.isdigit() or len(verify_code)>10):raise ValueError('invalid_verify_code')
        params={'qrcode':login['qrcode']}
        if verify_code:params['verify_code']=verify_code
        response=self.transport.get(_base_url(login['base'])+'/ilink/bot/get_qrcode_status',params=params,headers=self._headers(qr_status=True),timeout=36)
        response.raise_for_status();data=response.json();state=data.get('status')
        if state=='scaned_but_redirect':
            host=data.get('redirect_host','')
            login['base']=_base_url('https://'+host)
        if state=='confirmed':
            token=data.get('bot_token');user=data.get('ilink_user_id');bot=data.get('ilink_bot_id')
            if not all(isinstance(x,str) and x for x in (token,user,bot)):raise ValueError('incomplete_ilink_credentials')
            base=_base_url(data.get('baseurl') or login['base'])
            secret=json.dumps({'token':token,'user':user,'bot':bot,'base':base}).encode()
            self.secret_path.write_bytes(_protect(secret))
            self.secret_path.chmod(0o600)
            self.login=None
        if state in ('expired','verify_code_blocked'):self.login=None
        return {'status':state if state in ('wait','scaned','confirmed','expired','need_verifycode','verify_code_blocked','scaned_but_redirect','binded_redirect') else 'wait',
                'connected':state=='confirmed'}

    def configure(self,body):
        if not isinstance(body,dict) or set(body)-{'enabled','cadence_hours'}:raise ValueError('invalid_wechat_configuration')
        if 'enabled' in body and type(body['enabled']) is not bool:raise ValueError('invalid_wechat_switch')
        if 'cadence_hours' in body and (type(body['cadence_hours']) is not int or not 1<=body['cadence_hours']<=24):raise ValueError('invalid_cadence')
        with self.lock,self.db:
            if body.get('enabled') and not self._credentials():raise ValueError('wechat_login_required')
            for key,value in body.items():self._put(key,value)
        return self.status()

    def status(self):
        with self.lock:
            records=self.db.execute('SELECT id,task,created,status,attempts,error FROM outbox ORDER BY created DESC LIMIT 12').fetchall()
            inbound=self.db.execute('SELECT created,text FROM inbox ORDER BY created DESC LIMIT 3').fetchall()
            return {'connected':bool(self._credentials()),'enabled':self._get('enabled',False),
                    'cadence_hours':self._get('cadence_hours',6),'last_inbound':self._get('last_inbound',0),
                    'awaiting_inbound':self._get('enabled',False) and not self._get('context_token'),
                    'last_error':self._get('last_error'),
                    'messages':[dict(row) for row in records], 'inbound':[dict(row) for row in inbound]}

    def record_error(self,error=None):
        with self.lock,self.db:self._put('last_error',error)

    def queue_reply(self,text):
        if not isinstance(text,str) or not 1<=len(text)<=1200:raise ValueError('invalid_reply')
        with self.lock,self.db:
            now=self.clock()
            self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),'wechat:reply',now,now,'pending',0,text,None))

    def handle_inbound(self, messages, tracking):
        """Give the owner a compact status and accept scoped research directions."""
        for raw in messages:
            content=raw.strip()
            if not content:continue
            tasks=[task for task in tracking.status()['tasks'] if task.get('enabled')]
            if content in ('状态','追踪状态','status'):
                if not tasks:self.queue_reply('当前没有开启持续追踪任务。请在交易终端开启标的追踪。')
                else:
                    lines=[]
                    for task in tasks[:8]:
                        shares=(task.get('probabilities') or {}).get('percentages') or {}
                        odds=('BUY {buy:.1f}% · HOLD {hold:.1f}% · SELL {sell:.1f}%'.format(**shares) if shares else '动态比例待采集')
                        lines.append(f"{task['symbol']}：{odds}；{(task.get('previous') or {}).get('conclusion') or '研究中'}")
                    self.queue_reply('\n'.join(lines)[:1200])
                continue
            match=re.fullmatch(r'研究\s+([A-Za-z0-9]{1,40})\s+(.{1,500})',content,re.S)
            if match:
                symbol=match.group(1).upper();matches=[task for task in tasks if task['symbol']==symbol]
                if len(matches)==1:
                    task=matches[0]
                    tracking.configure({'category':task['category'],'symbol':symbol,'enabled':True,'note':match.group(2).strip()})
                    self.queue_reply(f'已将你的研究方向加入 {symbol}。下一轮研究会复核，完成后发回结论和 BUY / HOLD / SELL 比例。')
                else:self.queue_reply(f'没有唯一的已开启 {symbol} 追踪任务，请在终端确认市场和状态。')
                continue
            self.queue_reply('已收到。发送“状态”查看追踪结果；发送“研究 ZECUSDT 你的问题”补充研究方向。')

    @staticmethod
    def _message(task):
        p=(task.get('probabilities') or {}).get('percentages')
        if not p:return None
        result=task.get('previous') or {}
        return (f"{task['symbol']} · {task['category']}\n"
                f"BUY {p['buy']:.1f}%  HOLD {p['hold']:.1f}%  SELL {p['sell']:.1f}%\n"
                f"结论：{result.get('conclusion') or '持续观察中'}\n"
                f"建议：{result.get('recommendation') or '等待下一次有效复核'}\n"
                f"Bitget 已收盘 K 线 · {task['interval']}；三项比例为历史相似行情占比，不是交易收益率。")

    def observe(self,tasks):
        with self.lock,self.db:
            if not self._get('enabled',False):return
            now=self.clock()
            for task in tasks:
                if not task.get('enabled'):continue
                body=self._message(task)
                if not body:continue
                latest=self.db.execute("SELECT * FROM outbox WHERE task=? ORDER BY created DESC LIMIT 1",(task['id'],)).fetchone()
                if latest and latest['status'] in ('unknown','rejected') and latest['body']==body:continue
                previous=self._get('last_snapshot:'+task['id'],{})
                shares=task['probabilities']['percentages']
                revision=(task.get('notification') or {}).get('id')
                material=bool(previous and max(abs(shares[k]-previous['shares'][k]) for k in ('buy','hold','sell'))>=8)
                changed=bool(previous and revision and revision!=previous.get('revision'))
                first=not previous
                if not (first or material or changed):continue
                if latest and now-latest['created']<1800:continue
                if material and not changed and latest and now-latest['created']<self._get('cadence_hours',6)*3600:continue
                self.db.execute("UPDATE outbox SET status='superseded' WHERE task=? AND status='pending'",(task['id'],))
                marker=task['id']+'|'+str(now)+'|'+str(task['probabilities']['as_of'])
                self.db.execute('INSERT OR IGNORE INTO outbox VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid5(uuid.NAMESPACE_URL,marker)),task['id'],now,now,'pending',0,body,None))
                self._put('last_snapshot:'+task['id'],{'shares':shares,'revision':revision})

    def receive_once(self):
        creds=self._credentials()
        if not creds or not self._get('enabled',False):return []
        with self.lock:cursor=self._get('cursor','')
        response=self._post(creds['base'],'/ilink/bot/getupdates',{'get_updates_buf':cursor,'base_info':{'channel_version':VERSION,'bot_agent':'DSH/1.0'}},creds['token'],timeout=36)
        if response.get('ret') not in (None,0) or response.get('errcode') not in (None,0):raise ValueError('ilink_getupdates_rejected')
        self.record_error(None)
        messages=[]
        with self.lock,self.db:
            if response.get('get_updates_buf'):self._put('cursor',response['get_updates_buf'])
            for msg in response.get('msgs') or []:
                if msg.get('from_user_id')!=creds['user'] or msg.get('message_type') not in (None,1) or not msg.get('context_token'):continue
                ident=str(msg.get('message_id') or msg.get('client_id') or '')
                if not ident or self.db.execute('SELECT 1 FROM inbox WHERE id=?',(ident,)).fetchone():continue
                content=' '.join(item.get('text_item',{}).get('text','') for item in msg.get('item_list') or [] if item.get('type')==1).strip()
                recent=self.db.execute('SELECT created,text FROM inbox ORDER BY created DESC LIMIT 1').fetchone()
                duplicate=bool(recent and recent['text']==content and self.clock()-recent['created']<30)
                self.db.execute('INSERT INTO inbox VALUES(?,?,?)',(ident,self.clock(),content[:2000]))
                self._put('context_token',msg['context_token']);self._put('last_inbound',self.clock())
                self.db.execute("UPDATE outbox SET due=? WHERE status='pending' AND error='context_expired'",(self.clock(),))
                if not duplicate:messages.append(content)
        return messages

    def dispatch(self):
        creds=self._credentials()
        if not creds or not self._get('enabled',False):return False
        with self.lock,self.db:
            row=self.db.execute("SELECT * FROM outbox WHERE status='pending' AND due<=? ORDER BY created LIMIT 1",(self.clock(),)).fetchone()
            context=self._get('context_token')
            if not row or not context:return False
            sent=self.db.execute("SELECT count(*) FROM outbox WHERE status='sent' AND created>=?",(self.clock()-86400,)).fetchone()[0]
            if sent>=8 and row['task']!='wechat:reply':return False
            payload={'msg':{'from_user_id':'','to_user_id':creds['user'],'client_id':row['id'],
                            'message_type':2,'message_state':2,'context_token':context,
                            'item_list':[{'type':1,'text_item':{'text':row['body']}}]},
                     'base_info':{'channel_version':VERSION,'bot_agent':'DSH/1.0'}}
            try:
                result=self._post(creds['base'],'/ilink/bot/sendmessage',payload,creds['token'])
                if result.get('ret') not in (None,0):raise ValueError('ilink_ret_'+str(result['ret']))
            except Exception as exc:
                error='context_expired' if str(exc)=='ilink_ret_-2' else 'delivery_unknown'
                # Only ret=-2 is known to be safely retryable after new inbound.
                # Other failures may have delivered despite an ambiguous response.
                status='pending' if error=='context_expired' else 'unknown'
                self.db.execute('UPDATE outbox SET status=?,attempts=attempts+1,due=?,error=? WHERE id=?',
                                (status,self.clock()+3600,error,row['id']))
                return False
            self.db.execute("UPDATE outbox SET status='sent',attempts=attempts+1,error=NULL WHERE id=?",(row['id'],))
            return True

    def close(self):
        with self.lock:self.db.close()
        if self.owns_transport:self.transport.close()
