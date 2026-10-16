'use strict';
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.MarketTrackingView=api;
})(globalThis,()=>{
 const key=task=>task.id||`${task.category}:${task.symbol}`;
 function pickTask(tasks,selectedKey){
  const active=(tasks||[]).filter(task=>task.enabled);
  return active.find(task=>key(task)===selectedKey)||active.sort((a,b)=>(b.last_data||0)-(a.last_data||0))[0]||null;
 }
 function renderOdds(document,task){
  const card=document.getElementById('tracking-odds');
  card.hidden=!task;
  if(!task)return;
  const byId=id=>document.getElementById(id);
  byId('tracking-odds-symbol').textContent=task.symbol;
  byId('tracking-odds-phase').textContent=task.light==='green'?'追踪中':task.phase==='paused'?'已暂停':'等待恢复';
  byId('tracking-odds-phase').className='tracking-odds-phase '+(task.light||'yellow');
  const odds=task.probabilities;
  const shares=odds?.percentages;
  const valid=shares&&['buy','hold','sell'].every(name=>Number.isFinite(shares[name])&&shares[name]>=0&&shares[name]<=100)&&Math.abs(shares.buy+shares.hold+shares.sell-100)<0.001;
  for(const name of ['buy','hold','sell'])byId('tracking-'+name).textContent=valid?shares[name].toFixed(1)+'%':'—';
  const updated=valid&&Number.isFinite(odds.as_of)?new Date(odds.as_of*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}):'';
  byId('tracking-odds-window').textContent=valid?`未来 ${odds.horizon_bars} 根 ${odds.interval} · ${odds.effective_blocks||'—'} 个独立时段${updated?' · '+updated+'更新':''}`:'历史样本积累中';
 }
 return {pickTask,renderOdds};
});
