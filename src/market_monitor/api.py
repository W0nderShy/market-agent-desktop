import hmac
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .bitget import MarketError, chart_candles

class InstanceLock:
    """OS advisory lock released even after a process crash."""
    def __init__(self, runtime):
        self.path = Path(runtime)/'service.lock'
        self.file = None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file = self.path.open('a+b')
        try:
            self.file.seek(0,2)
            if self.file.tell() == 0:
                self.file.write(b'0')
                self.file.flush()
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('runtime_already_in_use') from None
        return self
    def __exit__(self,*args):
        self.file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
        self.file.close()

def make_server(monitor, port=8765):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def setup(self):
            super().setup()
            self.connection.settimeout(20)
        def reply(self,status,value):
            data = json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(data)
        def dispatch(self):
            if self.headers.get('Origin') is not None:
                self.reply(403,{'error':'origin_rejected'}); return
            supplied = self.headers.get('X-Monitor-Token','')
            if not hmac.compare_digest(supplied.encode(),token.encode()):
                self.reply(401,{'error':'unauthorized'}); return
            route = urlparse(self.path)
            try:
                if self.command == 'GET' and route.path == '/api/status':
                    self.reply(200,monitor.status())
                elif self.command == 'GET' and route.path == '/api/instruments':
                    query = parse_qs(route.query)
                    self.reply(200,{'items':monitor.feed.instruments(query.get('category',['SPOT'])[0],query.get('symbol',[None])[0])})
                elif self.command == 'GET' and route.path == '/api/candles':
                    query = parse_qs(route.query,keep_blank_values=True)
                    if any(len(values) != 1 for values in query.values()): raise ValueError()
                    self.reply(200,chart_candles(monitor.feed,query.get('category',['SPOT'])[0],
                                                query.get('symbol',[None])[0],query.get('interval',['1m'])[0]))
                elif self.command == 'PUT' and route.path == '/api/watchlist':
                    length = int(self.headers.get('Content-Length','0'))
                    if not 0 < length <= 65536: raise ValueError()
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body,dict) or set(body) != {'items'}: raise ValueError()
                    self.reply(200,{'items':monitor.set_watchlist(body['items'])})
                elif self.command == 'POST' and route.path == '/api/poll':
                    accepted = monitor.trigger_poll()
                    self.reply(202 if accepted else 409,{'accepted':accepted})
                elif self.command == 'POST' and route.path == '/api/shutdown':
                    monitor.stop_event.set()
                    self.reply(202,{'accepted':True})
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                else: self.reply(404,{'error':'not_found'})
            except (ValueError,TypeError,KeyError): self.reply(400,{'error':'invalid_configuration'})
            except MarketError: self.reply(502,{'error':'upstream_unavailable'})
            except Exception: self.reply(500,{'error':'internal_error'})
        do_GET = dispatch
        do_PUT = dispatch
        do_POST = dispatch
        do_OPTIONS = dispatch
    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    token_path = monitor.runtime/'api-token'
    token_path.write_text(token,encoding='utf-8')
    token_path.chmod(0o600)
    return server
