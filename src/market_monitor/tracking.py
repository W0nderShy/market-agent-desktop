"""Durable per-instrument research orchestration; no credentials or LLM network calls."""
import json
import math
import sqlite3
import re
import threading
import time
import uuid
import importlib.util
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .config import validate_items
from .probabilities import estimate_outcome_distribution

STEP = {'1m':60,'5m':300,'15m':900,'1H':3600,'4H':14400,'1D':86400}
ROOT = Path(__file__).resolve().parents[2]

def dumps(value): return json.dumps(value,ensure_ascii=False,allow_nan=False)

def normalize(rows,step,now):
    result={}
    for row in rows:
        if len(row)<6: raise ValueError('invalid_candles')
        t=int(row[0])//1000; o,h,l,c,v=map(float,row[1:6])
        if int(row[0])%1000 or (t%step not in ((0,57600) if step==86400 else (0,))) or not all(math.isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c): raise ValueError('invalid_candles')
        if t+step<=now: result[t]=[t,o,h,l,c,v]
    return [result[k] for k in sorted(result)]

class Cycle(TypedDict,total=False):
    task:dict
    data:dict

class Tracking:
    def __init__(self,runtime,feed,clock=time.time,external=None):
        self.feed,self.clock,self.external=feed,clock,external
        self.horizon_cache={}
        self.lock=threading.RLock();self.tick_lock=threading.Lock()
        self.db=sqlite3.connect(Path(runtime)/'tracking.sqlite3',check_same_thread=False,timeout=15)
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bars(task TEXT,t INTEGER,data TEXT,PRIMARY KEY(task,t));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,task TEXT,generation INTEGER,status TEXT,created REAL,lease TEXT,expires REAL,context TEXT);
        CREATE TABLE IF NOT EXISTS research(id TEXT PRIMARY KEY,task TEXT,created REAL,result TEXT,context TEXT);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value REAL);
        CREATE TABLE IF NOT EXISTS summaries(task TEXT,day TEXT,data TEXT,PRIMARY KEY(task,day));
        """)
        with self.lock,self.db:
            self.db.execute("UPDATE jobs SET status='cancelled' WHERE status IN ('pending','running')")
            for t in self._tasks():
                t.pop('daily_limit',None)
                t.pop('calls_day',None)
                if t['enabled']:
                    t.update(phase='recovering',reason='recovery',generation=t['generation']+1,error=None,next_check=0)
                elif t.get('phase')=='budget':t['phase']='paused'
                self._save(t)
        graph=StateGraph(Cycle)
        graph.add_node('collect_and_recover',lambda s:{'data':self.collect(s['task'])})
        graph.add_node('evaluate_and_queue',lambda s:self.evaluate(s['task'],s['data']))
        graph.add_edge(START,'collect_and_recover');graph.add_edge('collect_and_recover','evaluate_and_queue');graph.add_edge('evaluate_and_queue',END)
        self.graph=graph.compile()
        spec=importlib.util.spec_from_file_location('tracking_skills',ROOT/'scripts/run_market_skill.py')
        self.skills=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.skills)

    def _tasks(self): return [json.loads(r['data']) for r in self.db.execute('SELECT data FROM tasks')]
    def _get(self,key):
        row=self.db.execute('SELECT data FROM tasks WHERE id=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None
    def _save(self,t): self.db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?)',(t['id'],dumps(t)))
    def _valid(self,t):
        cur=self._get(t['id'])
        return cur if cur and cur['enabled'] and cur['generation']==t['generation'] else None

    def configure(self,body):
        validate_items([{'category':body.get('category'),'symbol':body.get('symbol')}])
        if type(body.get('enabled')) is not bool: raise ValueError('enabled_required')
        interval=body.get('interval');note=body.get('note')
        if interval is not None and interval not in STEP:raise ValueError('invalid_interval')
        if note is not None and (not isinstance(note,str) or len(note)>2000):raise ValueError('invalid_note')
        key=body['category']+':'+body['symbol']
        with self.lock,self.db:
            t=self._get(key)
            if t is None:
                if len(self._tasks())>=20:raise ValueError('task_limit')
                t=dict(id=key,category=body['category'],symbol=body['symbol'],interval=interval or '15m',enabled=False,generation=0,phase='paused',last_data=0,last_research=0,previous={},note='',next_review=0,verify_until=0,calls=0,failures=0,next_check=0,history=[])
            changed=(t['enabled']!=body['enabled'] or interval is not None and interval!=t['interval'] or note is not None and note!=t['note'])
            if not changed:return t
            if interval and interval!=t['interval']:
                self.horizon_cache.pop(key,None)
                self.db.execute('DELETE FROM bars WHERE task=?',(key,));self.db.execute('DELETE FROM summaries WHERE task=?',(key,));t.update(interval=interval,last_data=0,last_research=0,coverage_start=0,previous={},history=[])
            t.update(enabled=body['enabled'],generation=t['generation']+1,phase='recovering' if body['enabled'] else 'paused',reason='recovery' if t['last_research'] else 'initial',error=None,next_check=0,failures=0)
            if not body['enabled']:t['watch_signal']=None
            if note is not None:t['note']=note
            self.db.execute("UPDATE jobs SET status='cancelled' WHERE task=? AND status IN ('pending','running')",(key,))
            self._save(t)
            return t

    def collect(self,t):
        now=int(self.clock());step=STEP[t['interval']]
        raw=self.feed.candles(t['category'],t['symbol'],interval=t['interval'],limit=300)
        rows=normalize(raw,step,now)
        if len(rows)<200 or now-(rows[-1][0]+step)>step+180:raise ValueError('行情未完整或已过期')
        end=rows[-1][0]
        with self.lock,self.db:
            cur=self._valid(t)
            if not cur:return {}
            if not cur.get('coverage_start'):
                first=self.db.execute('SELECT min(t) FROM bars WHERE task=?',(t['id'],)).fetchone()[0]
                cur['coverage_start']=first or rows[0][0];self._save(cur)
            origin=cur['coverage_start']
        start=t['last_research']+step if t['last_research'] else origin
        start=min(start,end)
        def persist(batch):
            with self.lock,self.db:
                if not self._valid(t):return
                self.db.executemany('INSERT OR REPLACE INTO bars VALUES(?,?,?)',[(t['id'],r[0],dumps(r)) for r in batch])
        persist(rows)
        def missing():
            with self.lock:
                stamps={r[0] for r in self.db.execute('SELECT t FROM bars WHERE task=? AND t>=? AND t<=?',(t['id'],start,end))}
            # Find latest gap without materializing an unbounded timestamp range.
            cursor=end
            for stamp in sorted(stamps,reverse=True):
                if stamp!=cursor:return cursor
                cursor-=step
            return cursor if cursor>=start else None
        for _ in range(3):
            gap=missing()
            if gap is None:break
            batch=normalize(self.feed.history_candles(t['category'],t['symbol'],t['interval'],(gap+step)*1000,limit=100),step,now)
            persist([r for r in batch if start<=r[0]<=end])
        gap=missing()
        with self.lock,self.db:
            cur=self._valid(t)
            if not cur:return {}
            cur['last_data']=end;cur['checked_at']=now
            cur['gap_at']=gap;cur['collection_error']=None if gap is None else '历史行情尚未补齐';self._save(cur)
        if gap is not None:raise ValueError('正在补齐历史行情，尚有时间缺口')
        snapshot={'symbol':t['symbol'],'category':t['category'],'interval':t['interval'],'capturedAt':now*1000,'candles':normalize(raw,step,now+step)}
        metrics=self.skills.analyze_snapshot(snapshot,now_ms=now*1000)
        if any('error' in v for v in metrics['results'].values()):raise ValueError('分析所需已收盘 K 线不足')
        probabilities=estimate_outcome_distribution(rows,t['interval'])
        with self.lock,self.db:
            cur=self._valid(t)
            if cur:
                cur['probabilities']=probabilities
                self._save(cur)
        # Fixed-size segment summaries retain intermediate extremes across long gaps.
        with self.lock:
            count=self.db.execute('SELECT count(*) FROM bars WHERE task=? AND t>=? AND t<=?',(t['id'],start,end)).fetchone()[0]
            cursor=self.db.execute('SELECT data FROM bars WHERE task=? AND t>=? AND t<=? ORDER BY t',(t['id'],start,end))
            groups=[];size=max(1,math.ceil(count/20));group=[]
            for row in cursor:
                group.append(json.loads(row[0]))
                if len(group)==size:groups.append(self._segment(group));group=[]
            if group:groups.append(self._segment(group))
        return dict(rows=rows,metrics=metrics,probabilities=probabilities,coverage={'from':start,'through':end,'bars':count,'complete':True,'segments':groups})

    def _horizons(self,t,primary):
        """Sample several closed-bar horizons; missing horizons remain explicit gaps."""
        now=int(self.clock());key=t['id']
        cached=self.horizon_cache.get(key)
        if cached and now-cached[0]<3600:return cached[1]
        result={}
        for interval in dict.fromkeys((t['interval'],'1H','4H','1D')):
            step=STEP[interval]
            try:
                rows=primary if interval==t['interval'] else normalize(
                    self.feed.candles(t['category'],t['symbol'],interval=interval,limit=300),step,now)
                if len(rows)<50 or now-(rows[-1][0]+step)>2*step+180:raise ValueError('insufficient_or_stale')
                closes=[r[4] for r in rows]
                volumes=[r[5] for r in rows]
                result[interval]={
                    'as_of':rows[-1][0]+step,'bars':len(rows),'close':closes[-1],
                    'change_20_pct':round((closes[-1]/closes[-21]-1)*100,3),
                    'change_50_pct':round((closes[-1]/closes[-51]-1)*100,3) if len(rows)>50 else None,
                    'ma20':round(sum(closes[-20:])/20,6),
                    'ma50':round(sum(closes[-50:])/50,6),
                    'ma200':round(sum(closes[-200:])/200,6) if len(rows)>=200 else None,
                    'volume_20_vs_previous_20':round(sum(volumes[-20:])/sum(volumes[-40:-20]),3) if sum(volumes[-40:-20]) else None,
                    'high_20':max(r[2] for r in rows[-20:]),'low_20':min(r[3] for r in rows[-20:]),
                    'source':'Bitget public candles'}
            except Exception:
                result[interval]={'status':'unavailable','source':'Bitget public candles'}
        self.horizon_cache[key]=(now,result)
        return result

    @staticmethod
    def _segment(rows):
        peak=max(rows,key=lambda r:r[5])
        return dict(start=rows[0][0],end=rows[-1][0],open=rows[0][1],close=rows[-1][4],high=max(r[2] for r in rows),low=min(r[3] for r in rows),volume=sum(r[5] for r in rows),peak_volume_at=peak[0],peak_volume=peak[5])

    def evaluate(self,old,data):
        if not data:return {}
        now=self.clock();rows=data['rows'];last=rows[-1];step=STEP[old['interval']]
        with self.lock,self.db:
            t=self._valid(old)
            if not t:return {}
            if self.db.execute("SELECT 1 FROM jobs WHERE task=? AND status IN ('pending','running')",(t['id'],)).fetchone():return {}
            if t['next_check']>now:return {}
            reason=t.get('reason') if t['phase'] in ('recovering','error') else None
            prev=t.get('anchor',last[4]);change=abs(last[4]/prev-1)
            mean=sum(r[5] for r in rows[-21:-1])/20
            volume_ratio=last[5]/mean if mean else 0
            plan=t.get('plan',{})
            crossed=(plan.get('upper') and last[4]>plan['upper'] and prev<=plan['upper']) or (plan.get('lower') and last[4]<plan['lower'] and prev>=plan['lower'])
            fresh=last[0]>t['last_research']
            if fresh and (change>=0.008 or volume_ratio>=2):
                t['watch_signal']={'kind':'price_change' if change>=0.008 else 'volume_spike','as_of':last[0]+step,'price_change_pct':round(change*100,2),'volume_ratio':round(volume_ratio,2),'status':'awaiting_higher_timeframe_confirmation'}
            if not reason and fresh:
                if crossed:reason='price_level'
                elif change>=0.03:reason='price_change'
                elif volume_ratio>=3:reason='volume_spike'
                elif t['verify_until']>=now:reason='validation'
                elif now>=t['next_review']:reason='scheduled_review'
            if reason and (t.get('last_completed',0)+21600<=now or reason in ('initial','recovery','price_level')):
                stages=[json.loads(r[0]) for r in self.db.execute('SELECT data FROM summaries WHERE task=? ORDER BY day DESC LIMIT 3',(t['id'],))]
                try:external=self.external.snapshot() if self.external else None
                except Exception:external=None
                context=dict(research_mode='long_term',stage_memory=stages,task={k:t[k] for k in ('id','symbol','category','interval')},reason=reason,note=t['note'],previous=t['previous'],watch_signal=t.get('watch_signal'),recent_history=t['history'][-4:],coverage=data['coverage'],metrics=data['metrics'],probabilities=data['probabilities'],horizons=self._horizons(t,rows),external_evidence=external,recent_candles=rows[-60:],evidence_gaps={'macro':'部分 FRED 宏观序列可用，但市场隐含利率、DXY、MOVE 等仍缺失','cross_asset':'BTC 与黄金相关 Bitget 合约可作代理；铜、油、股票指数等仍缺失','fundamentals':'尚未接入该资产适用的基本面或链上数据','capex':'尚未接入产业投资数据','valuation_narrative':'尚未接入估值、期权和叙事数据'},decision_policy={'long_term_layers':['macro','cross_asset','fundamentals','capex','valuation_narrative','price_volume'],'tactical_layers':['price_volume','multi_timeframe_structure'],'allow_tactical_price_volume_actions':True,'allow_abstain':True,'actions':['buy','hold','sell','insufficient'],'skills':list(self.skills.SKILLS)},rules={'research_cadence':'daily_plus_material_events','cooldown_seconds':21600},limitations=['Bitget 公开 K 线可验证量价，不足以单独确认长期正反馈周期。','缺失的宏观、跨资产、基本面、叙事数据必须明确标为未验证，不得据量价推断。','K 线均已收盘；指标窗口以根数计；评分不是概率。'])
                if len(dumps(context))>60000:raise ValueError('研究上下文超过预算，需缩减输入')
                job=str(uuid.uuid4())
                self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(job,t['id'],t['generation'],'pending',now,None,0,dumps(context)))
                t.update(phase='queued',error=None,reason=reason)
            else:t.update(phase='validating' if now<t['verify_until'] else 'waiting',error=None)
            self._save(t)
        return {}

    def tick(self):
        if not self.tick_lock.acquire(False):return
        try:
            with self.lock,self.db:
                now=self.clock()
                for j in self.db.execute("SELECT * FROM jobs WHERE status='running' AND expires<?",(now,)).fetchall():self._fail(j,'研究执行超时或桌面端断开')
                tasks=self._tasks()
            for t in tasks:
                if not t['enabled']:continue
                try:self.graph.invoke({'task':t})
                except Exception as exc:
                    with self.lock,self.db:
                        cur=self._valid(t)
                        if cur:
                            message=str(exc) if isinstance(exc,ValueError) else '行情采集失败，等待重试'
                            cur.update(phase='error',reason='recovery',error=message,collection_error=message);self._save(cur)
        finally:self.tick_lock.release()

    def claim(self):
        now=self.clock()
        with self.lock,self.db:
            seen=self.db.execute("SELECT value FROM meta WHERE key='worker_seen'").fetchone()
            if seen and now-seen[0]>45:
                for task in self._tasks():
                    if task['enabled'] and not (task['phase'] in ('recovering','queued') and task.get('reason') in ('initial','recovery')):
                        task.update(phase='recovering',reason='recovery',generation=task['generation']+1,next_check=0)
                        self._save(task)
                        self.db.execute("UPDATE jobs SET status='cancelled' WHERE task=? AND status IN ('pending','running')",(task['id'],))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('worker_seen',?)",(now,))
            for j in self.db.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY created").fetchall():
                t=self._get(j['task'])
                if not t or not t['enabled'] or t['generation']!=j['generation']:continue
                # Never analyze a queued snapshot after a long worker outage.
                if now-j['created']>180:
                    self.db.execute("UPDATE jobs SET status='cancelled' WHERE id=?",(j['id'],));t.update(phase='recovering',reason='recovery',next_check=0);self._save(t);continue
                lease=str(uuid.uuid4())
                self.db.execute("UPDATE jobs SET status='running',lease=?,expires=? WHERE id=?",(lease,now+600,j['id']))
                t.update(phase='analyzing',calls=t['calls']+1);self._save(t)
                return dict(id=j['id'],lease=lease,context=json.loads(j['context']))
        return None

    def heartbeat(self,job,lease):
        with self.lock,self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('worker_seen',?)",(self.clock(),))
            j=self.db.execute('SELECT * FROM jobs WHERE id=? AND lease=? AND status=?',(job,lease,'running')).fetchone()
            t=self._get(j['task']) if j else None
            return {'active':bool(t and t['enabled'] and t['generation']==j['generation'])}

    def _fail(self,j,error):
        self.db.execute("UPDATE jobs SET status='failed' WHERE id=?",(j['id'],))
        t=self._get(j['task'])
        if t and t['enabled'] and t['generation']==j['generation']:
            failures=t['failures']+1
            t.update(phase='error',reason='recovery',error=error,failures=failures,next_check=self.clock()+(3600 if failures>=3 else 60*2**failures))
            self._save(t)

    def complete(self,job,lease,result=None,error=None):
        with self.lock,self.db:
            j=self.db.execute("SELECT * FROM jobs WHERE id=? AND lease=? AND status='running'",(job,lease)).fetchone()
            if not j:return {'accepted':False}
            if j['expires']<=self.clock():
                self._fail(j,'研究执行超时，结果未采纳');return {'accepted':False}
            t=self._get(j['task'])
            if not t or not t['enabled'] or t['generation']!=j['generation']:return {'accepted':False}
            if error:
                self._fail(j,'模型研究失败，稍后重试');return {'accepted':True}
            if not isinstance(result,dict) or not isinstance(result.get('summary'),str) or not 1<=len(result['summary'])<=5000:raise ValueError('invalid_research')
            if result.get('bias') not in ('bullish','bearish','neutral'):raise ValueError('invalid_bias')
            evidence=result.get('evidence',[])
            if not isinstance(evidence,list) or len(evidence)>6 or any(not isinstance(x,str) or len(x)>600 for x in evidence):raise ValueError('invalid_evidence')
            if not isinstance(result.get('invalidation',''),str) or len(result.get('invalidation',''))>1000:raise ValueError('invalid_invalidation')
            context=json.loads(j['context']);now=self.clock();last=context['recent_candles'][-1]
            clean={k:result.get(k) for k in ('summary','evidence','bias','invalidation')}
            for key,limit in (('conclusion',100),('recommendation',140)):
                value=result.get(key,'')
                if not isinstance(value,str) or len(value)>limit:raise ValueError('invalid_'+key)
                clean[key]=value.strip()
            allowed_states={'early_recovery','fundamental_confirmation','full_flywheel','narrative_expansion','bubble_formation','narrative_divergence','fundamental_divergence','cycle_deterioration','undetermined'}
            cycle_state=result.get('cycle_state','undetermined')
            if cycle_state not in allowed_states:raise ValueError('invalid_cycle_state')
            clean['cycle_state']=cycle_state
            for key in ('thesis','change_vs_previous'):
                value=result.get(key,'')
                if not isinstance(value,str) or len(value)>1000:raise ValueError('invalid_'+key)
                clean[key]=value
            for key in ('confirmations','contradictions','unknowns'):
                value=result.get(key,[])
                if not isinstance(value,list) or len(value)>8 or any(not isinstance(x,str) or len(x)>500 for x in value):raise ValueError('invalid_'+key)
                clean[key]=value
            action=result.get('action','insufficient')
            if action not in ('buy','hold','sell','insufficient'):raise ValueError('invalid_action')
            action_reason=result.get('action_reason','')
            if not isinstance(action_reason,str) or len(action_reason)>300:raise ValueError('invalid_action_reason')
            gaps=context.get('evidence_gaps') or {}
            if action in ('buy','sell') and (not action_reason.strip() or not evidence or not result.get('invalidation','').strip()):
                clean['action']='insufficient'
                clean['action_status']='missing_action_basis'
                clean['action_scope']='none'
                clean['action_reason']='方向判断缺少具体依据或失效条件，需重新核验。'
            else:
                clean['action']=action
                clean['action_status']='tactical' if gaps and action in ('buy','sell') else 'provisional' if gaps and action=='hold' else 'supported' if action!='insufficient' else 'missing_role_evidence'
                clean['action_scope']='price_volume' if gaps and action in ('buy','sell') else 'long_term' if action!='insufficient' and not gaps else 'none'
                clean['action_reason']=action_reason.strip() or ('长期判断仍需补齐关键证据。' if action=='insufficient' else '')
            clean['proposed_action']=None
            if context.get('evidence_gaps') and cycle_state!='undetermined':
                clean['cycle_state']='undetermined'
                clean['unknowns']=(clean['unknowns']+['长期阶段缺少宏观、跨资产或基本面证据，暂不能确认'])[:8]
            clean.update(as_of=context['coverage']['through'],source='Bitget',interval=t['interval'],probabilities=context.get('probabilities'))
            plan={}
            for key in ('upper','lower'):
                value=result.get(key)
                if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and last[4]*0.5<value<last[4]*1.5:plan[key]=value
            if plan.get('upper',float('inf'))<=last[4]:plan.pop('upper',None)
            if plan.get('lower',0)>=last[4]:plan.pop('lower',None)
            important=not t['previous'] or t['previous'].get('bias')!=clean['bias'] or t['previous'].get('cycle_state')!=clean['cycle_state'] or t['previous'].get('action')!=clean['action'] or context['reason'] in ('price_level','price_change','volume_spike','recovery')
            history=(t['history']+[{'id':job,'as_of':clean['as_of'],'bias':clean['bias'],'action':clean['action'],'cycle_state':clean['cycle_state'],'conclusion':clean['conclusion'],'thesis':clean['thesis'][:400],'summary':clean['summary'][:600]}])[-12:]
            t.update(previous=clean,last_research=clean['as_of'],last_completed=now,anchor=last[4],plan=plan,history=history,next_review=now+86400,next_check=0,failures=0,error=None,phase='validating',reason=None,watch_signal=None)
            if t.get('collection_error'):t.update(phase='error',reason='recovery',error=t['collection_error'])
            if context['reason'] in ('initial','recovery'):t['verify_until']=now+28800
            if important:t['notification']={'id':job,'created':now,'text':clean['conclusion'] or clean['summary'][:500]}
            self.db.execute('INSERT INTO research VALUES(?,?,?,?,?)',(job,t['id'],now,dumps(clean),j['context']))
            self.db.execute("UPDATE jobs SET status='done' WHERE id=?",(job,));self._save(t)
            day=time.strftime('%Y-%m-%d',time.gmtime(now))
            day_start=int(now)//86400*86400
            entries=self.db.execute('SELECT id,result FROM research WHERE task=? AND created>=? ORDER BY created',(t['id'],day_start)).fetchall()
            entries=[r for r in entries if json.loads(r['result']).get('interval')==t['interval']]
            stage={'interval':t['interval'],'day_utc':day,'research_count':len(entries),'latest_conclusion':clean['conclusion'],'latest_summary':clean['summary'][:600],'latest_thesis':clean['thesis'][:400],'cycle_sequence':[json.loads(r['result']).get('cycle_state','undetermined') for r in entries][-24:],'bias_sequence':[json.loads(r['result'])['bias'] for r in entries][-24:],'evidence_refs':[r['id'] for r in entries][-24:]}
            self.db.execute('INSERT OR REPLACE INTO summaries VALUES(?,?,?)',(t['id'],day,dumps(stage)))
            # Keep raw data at least from the last unreviewed point and 90 days of recent bars.
            self.db.execute('DELETE FROM bars WHERE task=? AND t<?',(t['id'],min(t['last_research'],now-90*86400)))
            self.db.execute("DELETE FROM jobs WHERE status IN ('done','failed','cancelled') AND created<?",(now-30*86400,))
            return {'accepted':True}

    def status(self):
        with self.lock:
            row=self.db.execute("SELECT value FROM meta WHERE key='worker_seen'").fetchone()
            worker=bool(row and self.clock()-row[0]<45)
            tasks=self._tasks()
            for t in tasks:
                stale=self.clock()-t.get('checked_at',0)>180
                t['light']='red' if not t['enabled'] else 'yellow' if (t['phase'] in ('recovering','error') or t.get('reason') in ('initial','recovery')) or not worker or stale or not t['last_research'] else 'green'
                t['worker_online']=worker
                t['history_total']=self.db.execute('SELECT count(*) FROM research WHERE task=?',(t['id'],)).fetchone()[0]
                t['events']=[{'id':r['id'],'created':r['created'],'result':json.loads(r['result'])} for r in self.db.execute('SELECT id,created,result FROM research WHERE task=? ORDER BY created DESC,id DESC LIMIT 8',(t['id'],))]
            return {'tasks':tasks,'worker_online':worker}

    def history(self,task,before=None,limit=10):
        if not isinstance(task,str) or not isinstance(limit,int) or not 1<=limit<=30:raise ValueError('invalid_history_request')
        with self.lock:
            if not self._get(task):raise ValueError('unknown_tracking_task')
            params=[task]
            where='task=?'
            if before is not None:
                if not isinstance(before,str) or '|' not in before:raise ValueError('invalid_history_cursor')
                stamp,record_id=before.split('|',1)
                try:created=float(stamp)
                except ValueError:raise ValueError('invalid_history_cursor') from None
                if not math.isfinite(created) or created<0 or not re.fullmatch(r'[A-Za-z0-9-]{1,64}',record_id):raise ValueError('invalid_history_cursor')
                where+=' AND (created<? OR (created=? AND id<?))'
                params.extend((created,created,record_id))
            rows=self.db.execute(f'SELECT id,created,result FROM research WHERE {where} ORDER BY created DESC,id DESC LIMIT ?',(*params,limit+1)).fetchall()
            has_more=len(rows)>limit
            items=[{'id':r['id'],'created':r['created'],'result':json.loads(r['result'])} for r in rows[:limit]]
            cursor=f"{items[-1]['created']}|{items[-1]['id']}" if has_more and items else None
            return {'items':items,'has_more':has_more,'next_before':cursor}

    def close(self):
        with self.lock:self.db.close()
