const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const {pickTask,renderOdds}=require('./market-tracking-view.js');

function dom(){
 return new JSDOM(`<section id="tracking-odds" hidden><span id="tracking-odds-symbol"></span><span id="tracking-odds-phase"></span><span id="tracking-odds-window"></span><strong id="tracking-buy"></strong><strong id="tracking-hold"></strong><strong id="tracking-sell"></strong></section>`).window.document;
}

test('corner odds follow the selected active tracking task',()=>{
 const tasks=[
  {id:'USDT-FUTURES:ZECUSDT',symbol:'ZECUSDT',enabled:true,last_data:100,probabilities:{percentages:{buy:30.1,hold:40.2,sell:29.7},horizon_bars:16,interval:'15m'}},
  {id:'USDT-FUTURES:BTCUSDT',symbol:'BTCUSDT',enabled:true,last_data:200,probabilities:{percentages:{buy:45.3,hold:25.1,sell:29.6},horizon_bars:6,interval:'4H'}}
 ];
 const task=pickTask(tasks,'USDT-FUTURES:ZECUSDT');
 assert.equal(task.symbol,'ZECUSDT');
 const document=dom();renderOdds(document,task);
 assert.equal(document.getElementById('tracking-odds').hidden,false);
 assert.equal(document.getElementById('tracking-buy').textContent,'30.1%');
 assert.equal(document.getElementById('tracking-hold').textContent,'40.2%');
 assert.equal(document.getElementById('tracking-sell').textContent,'29.7%');
 assert.match(document.getElementById('tracking-odds-window').textContent,/16 根 15m/);
});

test('corner odds use most recently sampled active task and hide when none remains',()=>{
 const tasks=[{id:'a',symbol:'A',enabled:false,last_data:300},{id:'b',symbol:'B',enabled:true,last_data:200},{id:'c',symbol:'C',enabled:true,last_data:100}];
 assert.equal(pickTask(tasks,'a').symbol,'B');
 const document=dom();renderOdds(document,tasks[1]);
 assert.equal(document.getElementById('tracking-buy').textContent,'—');
 renderOdds(document,null);
 assert.equal(document.getElementById('tracking-odds').hidden,true);
});

test('main terminal mounts monitor status in top bar and odds as a corner surface',()=>{
 const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
 const document=new JSDOM(html).window.document;
 assert.ok(document.querySelector('.topbar #monitor-mount #state'));
 assert.ok(document.querySelector('.terminal > #tracking-odds'));
 assert.equal(document.querySelector('.details-panel .agent-panel'),null);
 assert.ok(document.querySelector('script[src="market-tracking-view.js"]'));
});
