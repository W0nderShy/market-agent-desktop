'use strict';
const $ = id=>document.getElementById(id);
let watchlist=[],selectedKey=null,busy=false,fetching=false,interval='1m',chartGeneration=0,chartLoading=false,lastChartFetch=0;
let currentChart=null;
const key=item=>`${item.category}:${item.symbol}`;
const fmt=value=>value==null?'—':Number(value).toLocaleString('en-US',{maximumFractionDigits:8});
const time=value=>{if(!value)return '—';let n=typeof value==='string'&&/^\d+$/.test(value)?Number(value):value;return new Date(typeof n==='number'&&n<1e12?n*1000:n).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});};
const status=item=>item.error?'采集错误':item.stale?'行情过期':item.price==null?'等待采集':'行情正常';
let marketRows=[],marketMode="turnover",marketLoading=false,marketEpoch=0;
const selected=()=>watchlist.find(item=>key(item)===selectedKey)||marketRows.find(item=>key(item)===selectedKey);
const chart=new MarketChart.CandleChart($('chart'),row=>{$('ohlc').textContent=row?`${time(row.time)}   O ${fmt(row.open)}   H ${fmt(row.high)}   L ${fmt(row.low)}   C ${fmt(row.close)}   V ${fmt(row.volume)}`:'O —　 H —　 L —　 C —　 V —';});
async function request(action,payload){const response=await window.monitor.request(action,payload);if(!response.ok)throw Error(response.error||'请求失败');return response.data;}
function details(){
 const item=selected();
 $('agent-context').textContent=item?`${item.symbol} · ${interval} · ${currentChart?.rows.length||0} 根 K 线`:'未选择品种';
 $('chart-symbol').textContent=item?.symbol||'选择交易品种';$('chart-market').textContent=item?.category||'BITGET';
 $('chart-caption').textContent=item?'Bitget · 真实 K 线与基础币成交量':'从自选列表打开真实 K 线';
 $('headline-price').textContent=fmt(item?.price);$('quote-status').textContent=item?status(item):'等待选择';
 $('quote-status').className=item&&(item.error||item.stale)?'warn':'';
 $('detail-symbol').textContent=item?.symbol||'未选择品种';$('detail-price').textContent=fmt(item?.price);$('detail-category').textContent=item?`${item.category} · Bitget`:'—';
 $('detail-volume').textContent=fmt(item?.volume_24h);$('detail-exchange').textContent=time(item?.exchange_ts);$('detail-collected').textContent=time(item?.collected_ts);
 $('detail-status').textContent=item?status(item):'等待选择';$('detail-status').className=item&&(item.error||item.stale)?'warn':item?'good':'';$('remove').disabled=!item||busy;
}
function renderWatchlist(){
 $('watchlist').replaceChildren();$('count').textContent=watchlist.length;
 const search=$('market-search').value.trim().toUpperCase();
 let rows=(marketMode==='favorites'?watchlist:marketRows).filter(x=>x.symbol.includes(search));
 if(marketMode!=='favorites')rows=[...rows].sort((a,b)=>marketMode==='heat'?Math.abs(b.change)-Math.abs(a.change):b.turnover-a.turnover);
 $('empty').hidden=rows.length>0;$('empty').textContent=marketLoading?'加载中…':'暂无品种';
 rows.forEach(item=>{
 const row=document.createElement('div');row.className='market-row'+(key(item)===selectedKey?' active':'');
 const star=document.createElement('button');const saved=watchlist.some(x=>key(x)===key(item));star.textContent=saved?'★':'☆';star.className='favorite';star.disabled=busy;star.setAttribute('aria-label',(saved?'移除自选 ':'添加自选 ')+item.symbol);star.onclick=()=>mutate(saved?watchlist.filter(x=>key(x)!==key(item)):[...watchlist,item]);
 const button=document.createElement('button');button.className='market-select';button.onclick=()=>selectItem(key(item));
 const name=document.createElement('span'),price=document.createElement('span');name.textContent=item.symbol;price.textContent=fmt(item.price);
 const volume=document.createElement('small'),change=document.createElement('small');volume.textContent=item.turnover==null?item.category:new Intl.NumberFormat('zh-CN',{notation:'compact',maximumFractionDigits:1}).format(item.turnover);
 change.textContent=item.change==null?status(item):`${item.change>=0?'+':''}${(item.change*100).toFixed(2)}%`;change.className=item.change<0?'negative':'good';name.append(volume);price.append(change);button.append(name,price);row.append(star,button);$('watchlist').append(row);
 });details();
}
async function loadMarkets(){
 const epoch=++marketEpoch;marketLoading=true;const category=$('market-category').value;
 $('market-summary').textContent='加载中…';
 try{const data=await request('markets',{category});if(epoch!==marketEpoch)return;
 marketRows=data.items.filter(x=>x.category===category&&(category!=='SPOT'||x.symbol.endsWith('USDT'))&&Number(x.lastPrice)>0).map(x=>({symbol:x.symbol,category:x.category,price:x.lastPrice,turnover:Number(x.turnover24h)||0,change:Number(x.price24hPcnt)||0,volume_24h:x.volume24h,exchange_ts:Number(x.ts),collected_ts:Date.now(),stale:Date.now()-Number(x.ts)>180000}));
 $('market-summary').textContent=marketMode==='heat'?'24h 波动热度':`${marketRows.length} 个品种`;renderWatchlist();
 }catch(e){if(epoch===marketEpoch){marketRows=[];$('market-summary').textContent='行情加载失败';renderWatchlist();}}
 finally{if(epoch===marketEpoch){marketLoading=false;renderWatchlist();}}
}
$('market-search').oninput=renderWatchlist;
$('market-category').onchange=()=>{marketRows=[];renderWatchlist();loadMarkets();};
$('market-tabs').querySelectorAll('button').forEach(b=>b.onclick=()=>{marketMode=b.dataset.mode;$('market-tabs').querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));$('market-summary').textContent=marketMode==='heat'?'24h 波动热度':marketMode==='favorites'?'本机自选':`${marketRows.length} 个品种`;renderWatchlist();});
loadMarkets();setInterval(loadMarkets,30000);
function selectItem(value){if(value===selectedKey)return;selectedKey=value;chartGeneration++;chartLoading=false;chart.reset();renderWatchlist();loadCandles(true);}
async function loadCandles(clear=false){
 const item=selected();
 if(!item){currentChart=null;request('agent-context',null).catch(()=>{});chart.clear('添加并选择品种后查看真实 K 线');$('chart-status').textContent='尚未加载 K 线';return;}
 if(chartLoading&&!clear)return;
 const generation=++chartGeneration;chartLoading=true;
 if(clear){currentChart=null;request('agent-context',null).catch(()=>{});chart.clear('正在向 Bitget 请求 K 线…');}$('chart-status').textContent='正在加载交易所数据…';
 try{
  const data=await request('candles',{symbol:item.symbol,category:item.category,interval});
  if(generation!==chartGeneration)return;
  if(data.symbol!==item.symbol||data.category!==item.category||data.interval!==interval)throw Error('K 线品种或周期不匹配');
  chart.setData(data.items);
  currentChart={symbol:item.symbol,category:item.category,interval,capturedAt:Date.now(),rows:data.items};
  request('agent-context',currentChart).catch(()=>{});
  $('chart-status').textContent=data.items.length?`${data.items.length} 根 K 线 · 更新 ${time(Date.now())}`:'该品种暂无此周期 K 线';
 }catch(error){if(generation!==chartGeneration)return;chart.clear('K 线加载失败，请稍后重试');$('chart-status').textContent=error.message;}
 finally{if(generation===chartGeneration){chartLoading=false;lastChartFetch=Date.now();}}
}
async function refresh(){
 if(fetching)return;fetching=true;
 try{
  const data=await request('status');watchlist=data.watchlist||[];
  $('connection').textContent='本地服务已连接';$('connection').className='connection good';
  $('state').textContent=data.service.error?'采集异常':data.service.polling?'采集中':'等待下一轮';$('state').className=data.service.error?'warn':'good';
  $('agent-dot').classList.toggle('warning-dot',Boolean(data.service.error));
  $('monitor-mount').title=`最近采集 ${time(data.service.last_poll_ts)} · 间隔 ${data.service.poll_interval} 秒`;
  if(!selected()){
   selectedKey=watchlist.length?key(watchlist[0]):null;chartGeneration++;chartLoading=false;chart.reset();loadCandles(true);
  }else if(Date.now()-lastChartFetch>30000)loadCandles();
  renderWatchlist();$('events').replaceChildren();
  (data.events||[]).slice(0,8).forEach(event=>{
   const row=document.createElement('div');row.className='event-row';
   [time(event.created_ts||event.exchange_ts),event.symbol||'—',event.category||'—',event.status||'—'].forEach(value=>{const span=document.createElement('span');span.textContent=value;row.append(span);});$('events').append(row);
  });
  if(!data.events?.length){const empty=document.createElement('p');empty.className='events-empty';empty.textContent='尚无采集事件';$('events').append(empty);}
 }catch(error){$('connection').textContent='服务未连接';$('connection').className='connection warn';$('state').textContent='服务未连接';$('state').className='warn';$('agent-dot').classList.add('warning-dot');$('message').textContent=error.message;}
 finally{fetching=false;}
}
async function mutate(items){
 if(busy)return;busy=true;$('add-button').disabled=true;details();
 try{await request('watchlist',{items:items.map(({symbol,category})=>({symbol,category}))});$('message').textContent='自选列表已保存到本机。';$('symbol').value='';}
 catch(error){$('message').textContent=error.message;}
 finally{busy=false;$('add-button').disabled=false;await refresh();details();}
}
$('add').onsubmit=event=>{event.preventDefault();const item={symbol:$('symbol').value.trim().toUpperCase(),category:$('category').value};if(watchlist.some(row=>key(row)===key(item))){selectItem(key(item));$('message').textContent='该品种已经在自选列表中。';return;}mutate([...watchlist,item]);};
$('remove').onclick=()=>{if(selected())mutate(watchlist.filter(item=>key(item)!==selectedKey));};
$('poll').onclick=async()=>{$('poll').disabled=true;try{await request('poll');$('message').textContent='已请求采集，请等待本地服务更新。';}catch(error){$('message').textContent=error.message;}finally{$('poll').disabled=false;await refresh();loadCandles();}};
function toggleConversation(open){$('conversation-panel').hidden=!open;document.querySelector('.terminal').classList.toggle('with-agent',open);$('conversation').setAttribute('aria-expanded',String(open));if(open){$('agent-draft').focus();$('agent-messages').scrollTop=$('agent-messages').scrollHeight;}}
$('conversation').onclick=()=>toggleConversation($('conversation-panel').hidden);
$('conversation-close').onclick=()=>toggleConversation(false);
$('intervals').querySelectorAll('button').forEach(button=>{button.onclick=()=>{if(interval===button.dataset.interval)return;interval=button.dataset.interval;$('intervals').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===button));chart.reset();loadCandles(true);};});
$('chart-reset').onclick=()=>chart.reset();
refresh();setInterval(refresh,4000);

let agentRecords=[];
let agentConfigured=false,agentSession=false,agentSending=false,agentReading=false;
function agentError(e){$('agent-status').textContent=e.message||'Agent 请求失败';}
async function agentSetup(){
 try{const state=await request('agent-status');agentConfigured=!!state?.DEEPSEEK_API_KEY?.configured;$('agent-key').placeholder=agentConfigured?'已配置，输入可替换':'输入 DeepSeek API Key';
 const catalog=await request('agent-models');$('agent-model').replaceChildren();for(const g of catalog.groups||[]){if(!/deepseek/i.test(g.id+' '+g.name))continue;for(const m of g.models){const o=document.createElement('option');o.value=JSON.stringify({provider:g.id,model:m.id});o.textContent=m.name||m.id;$('agent-model').append(o);}}
 $('agent-status').textContent=agentConfigured?'密钥已配置':'请先配置 DeepSeek 密钥';await agentRead();
 if(agentSession){const catalog=await request('agent-skills');const wanted=['market-volume','market-trend','market-s-r','market-breakout','market-exhaustion'];const installed=(catalog.skills||[]).filter(s=>wanted.includes(s.name)&&s.modelInvocable);$('agent-skill-list').textContent=`金融分析 Skill · ${installed.length}/5 已启用`;$('agent-skill-list').title=installed.map(s=>s.name).join(' · ');}
 }catch(e){agentError(e);}
}
$('agent-save').onclick=async()=>{const secret=$('agent-key').value;$('agent-key').value='';$('agent-save').disabled=true;try{await request('agent-key',{key:secret});await agentSetup();}catch(e){agentError(e);}finally{$('agent-save').disabled=false;}};
async function agentCreate(){if(!$('agent-model').value)throw Error('暂无可用的 DeepSeek 模型');await request('agent-create',JSON.parse($('agent-model').value));agentSession=true;$('agent-messages').replaceChildren();$('agent-status').textContent='会话已创建';}
$('agent-new').onclick=async()=>{try{await agentCreate();await agentRead();}catch(e){agentError(e);}};
function messageText(event){const data=event.data||{};const content=data.message?.content||data.content;const plain=blocks=>(blocks||[]).flatMap(b=>b.type==='tool-result'?plain(b.content):b.type==='text'&&!b.text?.startsWith('[当前图表')?[b.text]:[]);return Array.isArray(content)?plain(content).join('\n'):'';}
async function agentRead(){
 if(agentReading)return;agentReading=true;
 try{const snapshot=await request('agent-read');agentSession=!!snapshot;
 if(snapshot){agentRecords=snapshot.records||[];const box=$('agent-messages');ChatView.render(box,snapshot);
 const active=snapshot.assistantStream?.activeAttempt;const partial=false;
 const events=(snapshot.records||[]).map(r=>r.event).filter(Boolean);const terminal=[...events].reverse().find(e=>e.type==='turn/start'||e.type==='turn/end');
 if(active)$('agent-status').textContent=partial?'正在回复…':'正在思考…';
 else if(terminal?.type==='turn/end'){$('agent-status').textContent=terminal.data?.reason?.kind==='error'?'本轮失败，请检查密钥、余额或网络':terminal.data?.reason?.kind==='cancelled'?'已停止':'本轮已结束';}
 else if(terminal?.type==='turn/start')$('agent-status').textContent='运行中…';
 else $('agent-status').textContent=agentConfigured?'可以发送消息':'请先配置 DeepSeek 密钥';

 }
 await readInteractions();
 $('agent-send').disabled=!agentConfigured||agentSending;
 }catch(e){agentError(e);}finally{agentReading=false;}
}
$('agent-send').onclick=async()=>{const text=$('agent-draft').value.trim();if(!text||agentSending)return;agentSending=true;$('agent-send').disabled=true;
 try{if(!agentSession)await agentCreate();const item=selected();
 const target=item?key(item):null;const period=interval;
 if(item && (!currentChart || Date.now()-currentChart.capturedAt>30000))await loadCandles(true);
 if(target!==(selected()?key(selected()):null)||period!==interval)throw Error('图表已切换，请重新发送');
 if(item&&(!currentChart||currentChart.symbol!==item.symbol||currentChart.category!==item.category||currentChart.interval!==interval))throw Error('K 线尚未加载完成，请稍后发送');
 await request('agent-send',{text,chart:currentChart});$('agent-draft').value='';$('agent-status').textContent='已提交至 dsh，等待回复…';document.querySelector('.agent-settings').open=false;await agentRead();
 }catch(e){agentError(e);}finally{agentSending=false;$('agent-send').disabled=!agentConfigured;}};
$('agent-stop').onclick=async()=>{try{await request('agent-cancel');$('agent-status').textContent='已请求停止';await agentRead();}catch(e){agentError(e);}};
agentSetup();setInterval(()=>{if(!$('conversation-panel').hidden)agentRead();},1500);

let interactionSignature='';
async function readInteractions(){
 const pending=await request('agent-interactions');const signature=JSON.stringify(pending.map(p=>p.eventId));if(signature===interactionSignature)return;interactionSignature=signature;
 const container=$('agent-interactions');container.replaceChildren();
 for(const item of pending){const card=document.createElement('section');card.className='interaction-card';const title=document.createElement('strong');title.textContent=item.event==='approval/request'?'需要批准':'Agent 提问';card.append(title);
 const answer=async value=>{try{await request('agent-answer',{eventId:item.eventId,value});interactionSignature='';await readInteractions();}catch(e){agentError(e);}};
 if(item.event==='approval/request'){const pre=document.createElement('pre');const callId=item.request.callId;const related=agentRecords.flatMap(r=>r.event?.data?.message?.content||[]).find(b=>b.callId===callId||b.id===callId);pre.textContent=JSON.stringify({request:item.request,operation:related},null,2);card.append(pre);for(const [label,value] of [['拒绝','rejected'],['仅允许一次','allowed-once']]){const b=document.createElement('button');b.textContent=label;b.onclick=()=>answer(value);card.append(b);}}
 else {const fields=[];for(const q of item.request.questions||[]){const label=document.createElement('label');label.textContent=q.question+(q.detail?'\n'+q.detail:'');card.append(label);const inputs=[];for(const option of q.options||[]){const line=document.createElement('label');const input=document.createElement('input');input.type=q.multiSelect?'checkbox':'radio';input.name=item.eventId+q.id;input.value=option.label;line.append(input,document.createTextNode(option.label));card.append(line);inputs.push(input);}const text=document.createElement('textarea');text.placeholder='输入回答';card.append(text);fields.push({q,inputs,text});}const button=document.createElement('button');button.textContent='提交回答';button.onclick=()=>answer({answers:fields.map(f=>({id:f.q.id,selected:f.inputs.filter(i=>i.checked).map(i=>i.value),custom:f.text.value}))});card.append(button);}
 container.append(card);
 }
}

// Keep pane width across launches; clamp again whenever the window changes size.
(()=>{
 const panel=document.getElementById('conversation-panel'),terminal=panel.parentElement;
 const handle=document.createElement('div');handle.className='agent-resizer';
 handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');
 handle.setAttribute('aria-label','调整 Agent 面板宽度');panel.prepend(handle);
 let preferred=400,drag=null;
 try{const saved=Number(localStorage.getItem('agent-pane-width'));if(saved>=360)preferred=saved;}catch{}
 const maximum=()=>Math.max(360,Math.min(720,terminal.clientWidth-(window.innerWidth<=1100?210:260)-302));
 const apply=()=>{const width=Math.max(360,Math.min(maximum(),preferred));terminal.style.setProperty('--agent-width',width+'px');handle.setAttribute('aria-valuemin','360');handle.setAttribute('aria-valuemax',String(maximum()));handle.setAttribute('aria-valuenow',String(Math.round(width)));};
 const save=()=>{try{localStorage.setItem('agent-pane-width',String(preferred));}catch{}};
 handle.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();drag={x:e.clientX,width:panel.getBoundingClientRect().width};handle.setPointerCapture(e.pointerId);handle.classList.add('dragging');document.body.classList.add('resizing-agent');});
 handle.addEventListener('pointermove',e=>{if(!drag)return;preferred=Math.max(360,Math.min(maximum(),drag.width+drag.x-e.clientX));apply();});
 const finish=()=>{if(!drag)return;drag=null;handle.classList.remove('dragging');document.body.classList.remove('resizing-agent');save();};
 handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);handle.addEventListener('lostpointercapture',finish);
 handle.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();preferred=e.key==='Home'?360:e.key==='End'?maximum():Math.max(360,Math.min(maximum(),panel.getBoundingClientRect().width+(e.key==='ArrowLeft'?20:-20)));apply();save();});
 handle.addEventListener('dblclick',()=>{preferred=400;apply();save();});
 new ResizeObserver(apply).observe(terminal);apply();
})();

let trackingFeatured=null;
async function openTracking(item){try{await request('tracking-window',item||selected()||{symbol:'ZECUSDT',category:'USDT-FUTURES'});}catch(e){$('message').textContent=e.message;}}
$('tracking-open').onclick=()=>openTracking(selected());
$('tracking-odds-open').onclick=()=>openTracking(trackingFeatured);
async function trackingBadge(){
 try{
  const state=await request('tracking');const active=(state.tasks||[]).filter(t=>t.enabled);
  for(const task of active){if(task.notification){try{const k='tracking-notification-'+task.id;if(localStorage.getItem(k)!==task.notification.id){$('message').textContent=task.symbol+' 研究更新：'+task.notification.text;localStorage.setItem(k,task.notification.id);}}catch{}}}
  $('tracking-open').textContent='持续跟踪'+(active.length?' · '+active.length:'');
  $('tracking-open').classList.toggle('tracking-active',active.length>0);
  $('tracking-open').classList.toggle('tracking-warning',active.some(t=>t.light==='yellow'));
  trackingFeatured=MarketTrackingView.pickTask(state.tasks,selectedKey);
  MarketTrackingView.renderOdds(document,trackingFeatured);
 }catch{trackingFeatured=null;MarketTrackingView.renderOdds(document,null);}
}
trackingBadge();setInterval(trackingBadge,5000);
