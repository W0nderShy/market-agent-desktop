import os
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from .bitget import Bitget
from .config import validate_items
from .graph import build_graph
from .store import Store
from .tracking import Tracking
from .research_sources import ExternalEvidence
from .wechat import WeChatBridge

class Monitor:
    def __init__(self, runtime='runtime', feed=None, poll_interval=60):
        if not 10 <= poll_interval <= 86400: raise ValueError('poll_interval_out_of_range')
        self.runtime = Path(runtime)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.feed = feed or Bitget()
        self.store = Store(self.runtime/'market.sqlite3')
        self.checkpoint_db = sqlite3.connect(self.runtime/'checkpoints.sqlite3',check_same_thread=False)
        self.saver = SqliteSaver(self.checkpoint_db)
        self.graph = build_graph(self.store,self.feed,self.saver)
        self.poll_interval = poll_interval
        self.poll_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.last_poll_ts = self.store.last_poll()
        self.error = None
        self.external_evidence = ExternalEvidence(self.feed) if feed is None else None
        self.tracking = Tracking(self.runtime,self.feed,external=self.external_evidence)
        self.wechat = WeChatBridge(self.runtime)
        self.tracking_thread = None
        self.wechat_thread = None

    def set_watchlist(self, items):
        items = validate_items(items)
        for item in items:
            rows = self.feed.instruments(item['category'],item['symbol'])
            if not any(isinstance(r,dict) and r.get('symbol') == item['symbol'] and r.get('category') == item['category'] and r.get('status') == 'online' for r in rows):
                raise ValueError('symbol_not_online')
        self.store.set_watchlist(items)
        return items

    def poll(self):
        if not self.poll_lock.acquire(blocking=False): return False
        try:
            for run_id in self.store.pending_runs():
                cfg = {'configurable':{'thread_id':run_id}}
                if self.graph.get_state(cfg).next: self.graph.invoke(None,cfg)
                self.store.run_done(run_id)
            for row in self.store.items():
                item = {'category':row['category'],'symbol':row['symbol']}
                run_id = str(uuid.uuid4())
                self.store.run_start(run_id)
                self.graph.invoke({'item':item},{'configurable':{'thread_id':run_id}})
                self.store.run_done(run_id)
            self.last_poll_ts = int(time.time()*1000)
            self.store.last_poll(self.last_poll_ts)
            self.error = None
            self.cleanup()
            return True
        finally: self.poll_lock.release()

    def trigger_poll(self):
        if self.poll_lock.locked(): return False
        threading.Thread(target=self._safe_poll,daemon=True).start()
        return True

    def _safe_poll(self):
        try: self.poll()
        except Exception: self.error = 'poll_failed'

    def start(self):
        def loop():
            while not self.stop_event.is_set():
                self._safe_poll()
                self.stop_event.wait(self.poll_interval)
        self.thread = threading.Thread(target=loop,daemon=True)
        self.thread.start()
        def research_loop():
            while not self.stop_event.is_set():
                self.tracking.tick()
                self.stop_event.wait(30)
        self.tracking_thread=threading.Thread(target=research_loop,daemon=True)
        self.tracking_thread.start()
        def wechat_loop():
            while not self.stop_event.is_set():
                try:
                    self.wechat.observe(self.tracking.status()['tasks'])
                    self.wechat.dispatch()
                    if self.wechat.status()['enabled']:
                        messages=self.wechat.receive_once()
                        if messages:self.wechat.handle_inbound(messages,self.tracking)
                except Exception as exc:
                    # Delivery state stays pending and the next pass can retry.
                    self.wechat.record_error(type(exc).__name__)
                self.stop_event.wait(5)
        self.wechat_thread=threading.Thread(target=wechat_loop,daemon=True)
        self.wechat_thread.start()

    def cleanup(self):
        cutoff = int((time.time()-30*86400)*1000)
        for run_id in self.store.cleanup(cutoff):
            self.saver.delete_thread(run_id)
            self.store.delete_run(run_id)

    def status(self):
        rows = []
        now = int(time.time()*1000)
        for item in self.store.items():
            latest = self.store.latest(item)
            rows.append({**item, 'price':None,'volume_24h':None,'exchange_ts':None,'collected_ts':None,**latest,'stale':not latest or now-latest['exchange_ts']>180000})
        return {'service':{'state':'running','poll_interval':self.poll_interval,'last_poll_ts':self.last_poll_ts,'polling':self.poll_lock.locked(),'error':self.error},'watchlist':rows,'events':self.store.events()}

    def close(self):
        self.stop_event.set()
        if self.thread: self.thread.join()
        if self.tracking_thread: self.tracking_thread.join()
        if self.wechat_thread: self.wechat_thread.join(timeout=40)
        self.tracking.close()
        self.wechat.close()
        if self.external_evidence:self.external_evidence.close()
        with self.poll_lock:
            self.store.close()
            self.checkpoint_db.close()
            self.feed.close()
