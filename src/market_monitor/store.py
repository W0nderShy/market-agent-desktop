import json
import sqlite3
import threading
import time

class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS watchlist(category TEXT, symbol TEXT, position INTEGER, error TEXT, PRIMARY KEY(category,symbol));
        CREATE TABLE IF NOT EXISTS observations(category TEXT,symbol TEXT,exchange_ts INTEGER,collected_ts INTEGER,price TEXT,volume_24h TEXT,candles TEXT,PRIMARY KEY(category,symbol,exchange_ts));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,category TEXT,symbol TEXT,exchange_ts INTEGER,created_ts INTEGER,status TEXT DEFAULT 'pending',UNIQUE(category,symbol,exchange_ts));
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,status TEXT,created_ts INTEGER);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
        ''')

    def set_watchlist(self, items):
        with self.lock, self.db:
            self.db.execute('DELETE FROM watchlist')
            self.db.executemany('INSERT INTO watchlist(category,symbol,position) VALUES(?,?,?)', [(i['category'],i['symbol'],n) for n,i in enumerate(items)])

    def items(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT category,symbol,error FROM watchlist ORDER BY position')]

    def record(self, item, observation, error):
        with self.lock, self.db:
            if not self.db.execute('SELECT 1 FROM watchlist WHERE category=? AND symbol=?',(item['category'],item['symbol'])).fetchone():
                return
            self.db.execute('UPDATE watchlist SET error=? WHERE category=? AND symbol=?',(error,item['category'],item['symbol']))
            if observation:
                args = (item['category'],item['symbol'],observation['exchange_ts'],observation['collected_ts'])
                self.db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?)',args+(observation['price'],observation['volume_24h'],json.dumps(observation['candles'])))
                self.db.execute('INSERT OR IGNORE INTO events(category,symbol,exchange_ts,created_ts) VALUES(?,?,?,?)',args)

    def latest(self, item):
        with self.lock:
            row = self.db.execute('SELECT exchange_ts,collected_ts,price,volume_24h FROM observations WHERE category=? AND symbol=? ORDER BY exchange_ts DESC LIMIT 1',(item['category'],item['symbol'])).fetchone()
            return dict(row) if row else {}

    def events(self):
        with self.lock: return [{**dict(r),'type':'observation'} for r in self.db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]

    def last_poll(self, value=None):
        with self.lock, self.db:
            if value is not None:
                self.db.execute("INSERT OR REPLACE INTO metadata VALUES('last_poll_ts',?)",(str(value),))
            row = self.db.execute("SELECT value FROM metadata WHERE key='last_poll_ts'").fetchone()
            return int(row[0]) if row else None

    def count_observations(self):
        with self.lock: return self.db.execute('SELECT count(*) FROM observations').fetchone()[0]

    def run_start(self, run_id):
        with self.lock, self.db: self.db.execute('INSERT INTO runs VALUES(?,?,?)',(run_id,'running',int(time.time()*1000)))

    def run_done(self, run_id):
        with self.lock, self.db: self.db.execute("UPDATE runs SET status='done' WHERE id=?",(run_id,))

    def pending_runs(self):
        with self.lock: return [r[0] for r in self.db.execute("SELECT id FROM runs WHERE status='running'")]

    def cleanup(self, cutoff):
        with self.lock, self.db:
            self.db.execute('DELETE FROM observations WHERE collected_ts < ?',(cutoff,))
            # These are expiring market observations, not long-lived research jobs.
            self.db.execute('DELETE FROM events WHERE created_ts < ?',(cutoff,))
            runs = [r[0] for r in self.db.execute("SELECT id FROM runs WHERE status='done' AND created_ts < ?",(cutoff,))]
            return runs

    def delete_run(self, run_id):
        with self.lock, self.db: self.db.execute('DELETE FROM runs WHERE id=?',(run_id,))

    def close(self):
        with self.lock: self.db.close()
