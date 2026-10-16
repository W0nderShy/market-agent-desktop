const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');

async function render(previous,events=[],older=[],probabilities=null){
 const html=fs.readFileSync(path.join(__dirname,'tracking.html'),'utf8');
 const script=fs.readFileSync(path.join(__dirname,'tracking.js'),'utf8');
 const dom=new JSDOM(html,{runScripts:'outside-only'});
 dom.window.setInterval=()=>0;
 dom.window.__historyCalls=0;
 dom.window.monitor={request:async action=>({ok:true,data:action==='tracking'?{worker_online:true,tasks:[{
  id:'USDT-FUTURES:ZECUSDT',symbol:'ZECUSDT',category:'USDT-FUTURES',interval:'15m',light:'green',phase:'waiting',enabled:true,
  previous,plan:{},events,history_total:events.length+older.length,last_data:0,last_research:0,probabilities
 }]}:action==='tracking-history'?(dom.window.__historyCalls++,{items:older,has_more:false,next_before:null}):null})};
 dom.window.eval(script);
 await new Promise(resolve=>setImmediate(resolve));
 return dom;
}

test('legacy long research is collapsed behind a concise conclusion and next step',async()=>{
 const dom=await render({cycle_state:'undetermined',summary:'很长的量价指标报告。'.repeat(30)});
 const document=dom.window.document;
 assert.match(document.querySelector('.tracking-verdict strong').textContent,/尚无足够证据/);
 assert.match(document.querySelector('.tracking-advice p').textContent,/等待更长周期/);
 assert.equal(document.querySelector('details[data-section="analysis"]').open,false);
 assert.equal(document.querySelector('.tracking-analysis').textContent.length>100,true);
 dom.window.close();
});

test('new research leads with its saved conclusion and recommendation',async()=>{
 const dom=await render({cycle_state:'undetermined',conclusion:'长期判断暂不变。',recommendation:'先核验日线量能。',summary:'完整依据。'});
 const document=dom.window.document;
 assert.equal(document.querySelector('.tracking-verdict strong').textContent,'长期判断暂不变。');
 assert.equal(document.querySelector('.tracking-advice p').textContent,'先核验日线量能。');
 dom.window.close();
});

test('role decision is visible, with evidence-limited judgment clearly marked',async()=>{
 const dom=await render({cycle_state:'undetermined',action:'insufficient',action_status:'missing_role_evidence',action_reason:'缺少基本面与估值证据。',conclusion:'长期判断待核验。'});
 const document=dom.window.document;
 assert.match(document.querySelector('.tracking-action').textContent,/证据不足/);
 assert.match(document.querySelector('.tracking-action-reason').textContent,/基本面与估值/);
 dom.window.close();
});

test('tactical buy is prominent without presenting it as a confirmed long-term cycle',async()=>{
 const dom=await render({cycle_state:'undetermined',action:'buy',action_status:'tactical',action_scope:'price_volume',action_reason:'突破后量能跟进。',conclusion:'短线偏强，长期仍待核验。'});
 const document=dom.window.document;
 assert.match(document.querySelector('.tracking-action').textContent,/BUY/);
 assert.match(document.querySelector('.tracking-action').textContent,/量价战术判断/);
 assert.match(document.querySelector('.tracking-state').textContent,/证据不足/);
 dom.window.close();
});

test('three dynamic outcome shares show their window and exact total',async()=>{
 const odds={percentages:{buy:42.3,sell:27.1,hold:30.6},horizon_bars:16,interval:'15m',observation_bars:208,effective_blocks:13,as_of:1800000000};
 const dom=await render({action:'hold',action_reason:'等待验证。'},[],[],odds);
 const task=dom.window.document.querySelector('.tracking-probabilities');
 assert.ok(task);
 assert.match(task.textContent,/42\.3%/);
 assert.match(task.textContent,/27\.1%/);
 assert.match(task.textContent,/30\.6%/);
 assert.match(task.textContent,/16 根/);
 dom.window.close();
});

test('tracking card keeps a visible timeline of prior research revisions',async()=>{
 const events=[
  {id:'new',created:2000,result:{conclusion:'当前判断维持。',change_vs_previous:'日线尚未确认',summary:'近期证据全文'}},
  {id:'old',created:1000,result:{conclusion:'首次建立观察。',summary:'初始证据全文'}}
 ];
 const dom=await render({cycle_state:'undetermined',conclusion:'当前判断维持。',summary:'当前分析'},events);
 const document=dom.window.document;
 assert.match(document.querySelector('.tracking-history-section h3').textContent,/研究历程/);
 assert.equal(document.querySelectorAll('.tracking-history-entry').length,2);
 assert.match(document.querySelector('.tracking-history-entry').textContent,/日线尚未确认/);
 assert.equal(document.querySelector('.tracking-history-entry details').open,false);
 dom.window.close();
});

test('older research remains accessible after the initial timeline',async()=>{
 const makeEvent=number=>({id:'event-'+number,created:2000+number,result:{conclusion:'第'+number+'轮判断',summary:'证据'}});
 const events=Array.from({length:8},(_,index)=>makeEvent(12-index));
 const older=[makeEvent(4),makeEvent(3)];
 const dom=await render({summary:'当前分析'},events,older);
 const document=dom.window.document;
 assert.equal(document.querySelectorAll('.tracking-history-entry').length,3);
 document.querySelector('.tracking-history-more').click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(document.querySelectorAll('.tracking-history-entry').length,8);
 document.querySelector('.tracking-history-more').click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(dom.window.__historyCalls,1);
 assert.equal(document.querySelectorAll('.tracking-history-entry').length,10);
 dom.window.close();
});
