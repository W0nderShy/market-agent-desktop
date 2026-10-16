import json
import pytest
from market_monitor.tracking import Tracking, normalize

class Feed:
    def __init__(self): self.end=1800000000; self.fail=False
    def candles(self,category,symbol,interval='15m',limit=300):
        if self.fail: raise RuntimeError('offline')
        return [[str((self.end-i*900)*1000),'100','102','99','101','10'] for i in reversed(range(limit))]
    def history_candles(self,category,symbol,interval,end_time,limit=200):
        end=int(end_time)//1000//900*900-900
        return [[str((end-i*900)*1000),'100','102','99','101','10'] for i in reversed(range(limit))]

@pytest.fixture
def setup(tmp_path):
    feed=Feed(); clock=[feed.end+901]
    tracker=Tracking(tmp_path,feed,clock=lambda:clock[0])
    yield tracker,feed,clock,tmp_path
    tracker.close()

def enable(t): return t.configure({'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':True})
def result(): return {'summary':'量价处于震荡，等待收盘确认。','evidence':['近20根量能平稳'],'invalidation':'放量离开区间后复核','bias':'neutral','important':False}

def test_pause_discards_inflight_and_is_idempotent(setup):
    t,f,c,p=setup; task=enable(t); t.tick(); j=t.claim(); assert j
    t.configure({'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':False})
    assert not t.complete(j['id'],j['lease'],result())['accepted']
    assert t.status()['tasks'][0]['phase']=='paused'

def test_research_wait_and_restart_recovery(setup):
    t,f,c,p=setup; enable(t);t.tick();j=t.claim()
    assert t.complete(j['id'],j['lease'],result())['accepted']
    assert not t.complete(j['id'],j['lease'],result())['accepted']
    t.tick(); assert t.claim() is None
    t2=Tracking(p,f,clock=lambda:c[0])
    try:
        assert t2.status()['tasks'][0]['phase']=='recovering'
        t2.tick();j2=t2.claim();assert j2['context']['reason']=='recovery'
        assert t2.status()['tasks'][0]['light']=='yellow'
        assert j2['context']['previous']['summary']==result()['summary']
    finally:t2.close()

def test_failure_stays_yellow_and_no_job(setup):
    t,f,c,p=setup;enable(t);f.fail=True;t.tick()
    assert t.claim() is None
    assert t.status()['tasks'][0]['light']=='yellow'

def test_recovery_covers_more_than_chart_window(setup):
    t,f,c,p=setup;enable(t);t.tick();j=t.claim();t.complete(j['id'],j['lease'],result())
    t.configure({'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':False})
    f.end+=400*900;c[0]=f.end+901;enable(t);t.tick();j=t.claim()
    assert j['context']['coverage']['bars']==400
    assert j['context']['coverage']['complete'] is True

def test_note_invalidate_old_job(setup):
    t,f,c,p=setup; enable(t);t.tick();j=t.claim()
    t.configure({'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':True,'note':'重点看放量是否延续'})
    assert not t.complete(j['id'],j['lease'],result())['accepted']
    t.tick();j=t.claim();assert j['context']['note']=='重点看放量是否延续'
    assert t.complete(j['id'],j['lease'],result())['accepted']


def test_price_trigger_has_no_arbitrary_daily_limit(setup):
    t,f,c,p=setup;task=enable(t);t.tick();j=t.claim();t.complete(j['id'],j['lease'],result())
    f.end+=900;c[0]+=900;t.heartbeat(j['id'],j['lease'])
    # A new closed bar crosses the previous model's observation level.
    with t.lock,t.db:
        state=t._get(task['id']);state['anchor']=99;state['plan']={'upper':100};t._save(state)
    t.tick();j=t.claim();assert j['context']['reason']=='price_level'
    t.complete(j['id'],j['lease'],result())
    with t.lock,t.db:
        state=t._get(task['id']);state['calls']=24;state['anchor']=99;state['plan']={'upper':100};t._save(state)
    f.end+=900;c[0]+=900;t.heartbeat(j['id'],j['lease']);t.tick()
    assert t.claim()['context']['reason']=='price_level'

def test_stale_lease_and_paused_restart(setup):
    t,f,c,p=setup;enable(t);t.tick();j=t.claim();c[0]+=601
    t.tick();assert not t.complete(j['id'],j['lease'],result())['accepted']
    assert t.status()['tasks'][0]['failures']==1
    t.configure({'category':'USDT-FUTURES','symbol':'ZECUSDT','enabled':False})
    t2=Tracking(p,f,clock=lambda:c[0])
    try:assert t2.status()['tasks'][0]['light']=='red'
    finally:t2.close()

def test_incomplete_history_never_advances_research(setup):
    t,f,c,p=setup;enable(t);t.tick();j=t.claim();t.complete(j['id'],j['lease'],result())
    old=t.status()['tasks'][0]['last_research'];f.end+=1000*900;c[0]=f.end+901
    f.history_candles=lambda *a,**k:[]
    t.tick();assert t.claim() is None
    current=t.status()['tasks'][0];assert current['last_research']==old and current['light']=='yellow'

def test_current_forming_bar_is_excluded_without_false_staleness(setup):
    t,f,c,p=setup;c[0]=f.end+600;enable(t);t.tick();j=t.claim()
    assert j and j['context']['recent_candles'][-1][0]==f.end-900
    assert j['context']['metrics']['excluded_unclosed_bars']==1


def test_desktop_outage_forces_recovery_even_when_backend_stays_alive(setup):
    t,f,c,p=setup;enable(t);t.tick();j=t.claim();t.complete(j['id'],j['lease'],result())
    c[0]+=60
    assert t.claim() is None
    assert t.status()['tasks'][0]['phase']=='recovering'
    t.tick();assert t.claim()['context']['reason']=='recovery'


def test_late_completion_is_rejected_even_before_scheduler_tick(setup):
    t,f,c,p=setup;enable(t);t.tick();j=t.claim();c[0]+=601
    assert not t.complete(j['id'],j['lease'],result())['accepted']
    assert t.status()['tasks'][0]['last_research']==0


def test_initial_interruption_retains_original_coverage(setup):
    t,f,c,p=setup;enable(t);t.tick();j=t.claim();original=j['context']['coverage']['from']
    f.end+=1000*900;c[0]=f.end+901
    t2=Tracking(p,f,clock=lambda:c[0])
    try:
        recovered=None
        for _ in range(6):
            t2.tick();recovered=t2.claim()
            if recovered:break
        assert recovered and recovered['context']['coverage']['from']==original
        assert recovered['context']['coverage']['bars']==1300
    finally:t2.close()

def test_result_cannot_clear_newer_collection_failure(setup):
    t,f,c,p=setup;enable(t);t.tick();j=t.claim();c[0]+=30;f.fail=True;t.tick()
    assert t.complete(j['id'],j['lease'],result())['accepted']
    current=t.status()['tasks'][0]
    assert current['light']=='yellow' and current['error']


def test_long_term_context_uses_multiple_horizons_when_available(tmp_path):
    class MultiFeed(Feed):
        def candles(self,category,symbol,interval='15m',limit=300):
            step={'15m':900,'1H':3600,'4H':14400,'1D':86400}[interval]
            end=self.end//step*step
            return [[str((end-i*step)*1000),'100','102','99',str(100+i/1000),'10'] for i in reversed(range(limit))]
    feed=MultiFeed();now=[feed.end+901]
    tracker=Tracking(tmp_path,feed,clock=lambda:now[0])
    try:
        enable(tracker);tracker.tick();job=tracker.claim()
        assert job['context']['research_mode']=='long_term'
        assert set(job['context']['horizons'])=={'15m','1H','4H','1D'}
        assert job['context']['horizons']['1D']['bars']>=200
        assert job['context']['evidence_gaps']['fundamentals']
        assert job['context']['evidence_gaps']['macro']
    finally:tracker.close()


def test_long_term_state_survives_next_research_and_not_every_bar(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    answer=result()|{'cycle_state':'undetermined','thesis':'尚无长期循环证据',
                     'change_vs_previous':'初次建档','confirmations':[],
                     'contradictions':['缺少基本面'],'unknowns':['宏观数据未接入']}
    assert t.complete(job['id'],job['lease'],answer)['accepted']
    f.end+=900;c[0]+=900;t.heartbeat(job['id'],job['lease']);t.tick();assert t.claim() is None
    f.end+=24*3600;c[0]+=24*3600;t.heartbeat(job['id'],job['lease']);t.tick();later=t.claim()
    assert later['context']['reason']=='scheduled_review'
    assert later['context']['previous']['thesis']=='尚无长期循环证据'
    assert later['context']['previous']['cycle_state']=='undetermined'


def test_minor_price_move_does_not_start_another_model_round(setup):
    t,f,c,p=setup;task=enable(t);t.tick();job=t.claim();t.complete(job['id'],job['lease'],result())
    with t.lock,t.db:
        state=t._get(task['id']);state['anchor']=100;t._save(state)
    f.end+=3600;c[0]+=3600;t.heartbeat(job['id'],job['lease']);t.tick()
    assert t.claim() is None
    assert t.status()['tasks'][0]['watch_signal']['kind']=='price_change'


def test_price_data_alone_cannot_confirm_long_term_cycle(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    claimed=result()|{'cycle_state':'full_flywheel','thesis':'长期正反馈已形成'}
    assert t.complete(job['id'],job['lease'],claimed)['accepted']
    state=t.status()['tasks'][0]['previous']
    assert state['cycle_state']=='undetermined'
    assert state['unknowns']


def test_external_evidence_is_sent_with_research_context(tmp_path):
    class Sources:
        def snapshot(self):return {'macro':{'DGS10':{'value':4.05,'as_of':'2026-09-23'}},'cross_asset':{}}
    feed=Feed();tracker=Tracking(tmp_path,feed,clock=lambda:feed.end+901,external=Sources())
    try:
        enable(tracker);tracker.tick();job=tracker.claim()
        assert job['context']['external_evidence']['macro']['DGS10']['value']==4.05
    finally:tracker.close()


def test_research_saves_conclusion_before_full_analysis(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    answer=result()|{'conclusion':'长期阶段仍待确认，短期反弹尚未得到更长周期支持。',
                     'recommendation':'先观察 4 小时结构和成交量能否延续，再修订判断。'}
    assert t.complete(job['id'],job['lease'],answer)['accepted']
    previous=t.status()['tasks'][0]['previous']
    assert previous['conclusion']==answer['conclusion']
    assert previous['recommendation']==answer['recommendation']


def test_research_rejects_oversized_topline(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    with pytest.raises(ValueError,match='invalid_conclusion'):
        t.complete(job['id'],job['lease'],result()|{'conclusion':'字'*101})


def test_tracking_context_exposes_five_skills_and_role_decision_rules(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    context=job['context']
    assert set(context['metrics']['results'])=={'market-trend','market-volume','market-s-r','market-breakout','market-exhaustion'}
    assert context['decision_policy']['long_term_layers']==['macro','cross_asset','fundamentals','capex','valuation_narrative','price_volume']
    assert context['decision_policy']['tactical_layers']==['price_volume','multi_timeframe_structure']
    assert context['decision_policy']['allow_tactical_price_volume_actions'] is True
    assert context['decision_policy']['allow_abstain'] is True


def test_odds_update_on_closed_bar_without_starting_a_new_model_round(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    first=t.status()['tasks'][0]['probabilities']
    assert sum(first['percentages'].values())==100.0
    assert t.complete(job['id'],job['lease'],result())['accepted']
    f.end+=900;c[0]+=900;t.tick()
    current=t.status()['tasks'][0]
    assert current['probabilities']['as_of']>first['as_of']
    assert t.claim() is None


def test_model_cannot_replace_measured_outcome_shares(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    measured=job['context']['probabilities']
    assert measured and sum(measured['percentages'].values())==100.0
    assert t.complete(job['id'],job['lease'],result()|{'probabilities':{'buy':100}})['accepted']
    assert t.status()['tasks'][0]['previous']['probabilities']==measured


def test_price_volume_action_remains_tactical_when_long_term_evidence_is_missing(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    answer=result()|{'action':'buy','action_reason':'突破后成交量跟进，等待 4 小时收盘确认。'}
    assert t.complete(job['id'],job['lease'],answer)['accepted']
    previous=t.status()['tasks'][0]['previous']
    assert previous['action']=='buy'
    assert previous['action_status']=='tactical'
    assert previous['action_scope']=='price_volume'
    assert previous['action_reason']==answer['action_reason']
    assert previous['cycle_state']=='undetermined'


def test_directional_action_without_specific_evidence_or_invalidation_abstains(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    answer=result()|{'action':'sell','action_reason':'', 'evidence':[], 'invalidation':''}
    assert t.complete(job['id'],job['lease'],answer)['accepted']
    previous=t.status()['tasks'][0]['previous']
    assert previous['action']=='insufficient'
    assert previous['action_status']=='missing_action_basis'


def test_hold_is_recorded_as_provisional_when_role_evidence_is_missing(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    answer=result()|{'action':'hold','action_reason':'量价尚未确认，维持观察。'}
    assert t.complete(job['id'],job['lease'],answer)['accepted']
    previous=t.status()['tasks'][0]['previous']
    assert previous['action']=='hold'
    assert previous['action_status']=='provisional'
    assert previous['action_reason']==answer['action_reason']


def test_invalid_action_is_rejected(setup):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    with pytest.raises(ValueError,match='invalid_action'):
        t.complete(job['id'],job['lease'],result()|{'action':'strong_buy'})


@pytest.mark.parametrize('action',['buy','sell'])
def test_full_role_evidence_can_record_directional_research_action(setup,action):
    t,f,c,p=setup;enable(t);t.tick();job=t.claim()
    with t.lock,t.db:
        raw=t.db.execute('SELECT context FROM jobs WHERE id=?',(job['id'],)).fetchone()[0]
        context=json.loads(raw);context['evidence_gaps']={}
        t.db.execute('UPDATE jobs SET context=? WHERE id=?',(json.dumps(context),job['id']))
    answer=result()|{'action':action,'action_reason':'多层证据与反证核验完成。','evidence':['宏观来源','基本面来源']}
    assert t.complete(job['id'],job['lease'],answer)['accepted']
    previous=t.status()['tasks'][0]['previous']
    assert previous['action']==action
    assert previous['action_status']=='supported'


def test_history_paginates_completed_research_without_dropping_same_time(setup):
    t,f,c,p=setup;task=enable(t)
    with t.lock,t.db:
        for number in range(12):
            t.db.execute('INSERT INTO research VALUES(?,?,?,?,?)',
                         (f'event-{number:02}',task['id'],1000+number//2,
                          '{"conclusion":"历史判断","summary":"历史分析"}','{}'))
    first=t.history(task['id'],limit=5)
    second=t.history(task['id'],before=first['next_before'],limit=5)
    third=t.history(task['id'],before=second['next_before'],limit=5)
    ids=[item['id'] for page in (first,second,third) for item in page['items']]
    assert len(ids)==len(set(ids))==12
    assert first['has_more'] and second['has_more'] and not third['has_more']
    assert ids[0]=='event-11' and ids[-1]=='event-00'
    with pytest.raises(ValueError):t.history(task['id'],before='bad cursor')


def test_bitget_daily_candle_uses_exchange_day_boundary():
    stamp=1800000000//86400*86400+57600
    row=[str(stamp*1000),'100','102','99','101','10']
    assert normalize([row],86400,stamp+86401)[0][0]==stamp
