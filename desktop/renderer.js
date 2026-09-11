'use strict';
const $ = id=>document.getElementById(id);
let watchlist=[],selectedKey=null,busy=false,fetching=false,interval='1m',chartGeneration=0,chartLoading=false,lastChartFetch=0;
const key=item=>`${item.category}:${item.symbol}`;
const fmt=value=>value==null?'—':Number(value).toLocaleString('en-US',{maximumFractionDigits:8});
const time=value=>{if(!value)return '—';let n=typeof value==='string'&&/^\d+$/.test(value)?Number(value):value;return new Date(typeof n==='number'&&n<1e12?n*1000:n).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});};
const status=item=>item.error?'采集错误':item.stale?'行情过期':item.price==null?'等待采集':'行情正常';
const selected=()=>watchlist.find(item=>key(item)===selectedKey);
const chart=new MarketChart.CandleChart($('chart'),row=>{$('ohlc').textContent=row?`${time(row.time)}   O ${fmt(row.open)}   H ${fmt(row.high)}   L ${fmt(row.low)}   C ${fmt(row.close)}   V ${fmt(row.volume)}`:'O —　 H —　 L —　 C —　 V —';});
async function request(action,payload){const response=await window.monitor.request(action,payload);if(!response.ok)throw Error(response.error||'请求失败');return response.data;}
function details(){
 const item=selected();
 $('chart-symbol').textContent=item?.symbol||'选择交易品种';$('chart-market').textContent=item?.category||'BITGET';
 $('chart-caption').textContent=item?'Bitget · 真实 K 线与基础币成交量':'从自选列表打开真实 K 线';
 $('headline-price').textContent=fmt(item?.price);$('quote-status').textContent=item?status(item):'等待选择';
 $('quote-status').className=item&&(item.error||item.stale)?'warn':'';
 $('detail-symbol').textContent=item?.symbol||'未选择品种';$('detail-price').textContent=fmt(item?.price);$('detail-category').textContent=item?`${item.category} · Bitget`:'—';
 $('detail-volume').textContent=fmt(item?.volume_24h);$('detail-exchange').textContent=time(item?.exchange_ts);$('detail-collected').textContent=time(item?.collected_ts);
 $('detail-status').textContent=item?status(item):'等待选择';$('detail-status').className=item&&(item.error||item.stale)?'warn':item?'good':'';$('remove').disabled=!item||busy;
}
function renderWatchlist(){
 $('watchlist').replaceChildren();$('count').textContent=watchlist.length;$('empty').hidden=watchlist.length>0;
 watchlist.forEach(item=>{
  const button=document.createElement('button');button.type='button';button.className='watch-item'+(key(item)===selectedKey?' active':'');button.setAttribute('aria-pressed',String(key(item)===selectedKey));
  const name=document.createElement('span'),symbol=document.createElement('strong'),category=document.createElement('small');symbol.textContent=item.symbol;category.textContent=item.category;name.append(symbol,category);
  const price=document.createElement('span');price.className='watch-price';price.textContent=fmt(item.price);const state=document.createElement('small');state.textContent=status(item);state.className=item.error||item.stale?'warn':'good';price.append(state);button.append(name,price);
  button.onclick=()=>selectItem(key(item));$('watchlist').append(button);
 });details();
}
function selectItem(value){if(value===selectedKey)return;selectedKey=value;chartGeneration++;chartLoading=false;chart.reset();renderWatchlist();loadCandles(true);}
async function loadCandles(clear=false){
 const item=selected();
 if(!item){chart.clear('添加并选择品种后查看真实 K 线');$('chart-status').textContent='尚未加载 K 线';return;}
 if(chartLoading&&!clear)return;
 const generation=++chartGeneration;chartLoading=true;
 if(clear)chart.clear('正在向 Bitget 请求 K 线…');$('chart-status').textContent='正在加载交易所数据…';
 try{
  const data=await request('candles',{symbol:item.symbol,category:item.category,interval});
  if(generation!==chartGeneration)return;
  if(data.symbol!==item.symbol||data.category!==item.category||data.interval!==interval)throw Error('K 线品种或周期不匹配');
  chart.setData(data.items);
  $('chart-status').textContent=data.items.length?`${data.items.length} 根 K 线 · 更新 ${time(Date.now())} · 最新一根可能尚未收盘`:'该品种暂无此周期 K 线';
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
  $('last').textContent=time(data.service.last_poll_ts);$('poll-interval').textContent=`${data.service.poll_interval} 秒`;
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
$('conversation').onclick=async()=>{try{await request('conversation');}catch(error){$('message').textContent=error.message;}};
$('intervals').querySelectorAll('button').forEach(button=>{button.onclick=()=>{if(interval===button.dataset.interval)return;interval=button.dataset.interval;$('intervals').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===button));chart.reset();loadCandles(true);};});
$('chart-reset').onclick=()=>chart.reset();
refresh();setInterval(refresh,4000);
