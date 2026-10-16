'use strict';
const $=id=>document.getElementById(id);
const selected=()=>({symbol:$('tracking-symbol').value.trim().toUpperCase(),category:$('tracking-category').value});
const time=value=>value?new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}):'—';
const compact=(value,max)=>{const clean=String(value||'').replace(/\s+/g,' ').trim();const chars=Array.from(clean);return chars.length>max?chars.slice(0,max).join('')+'…':clean;};
const line=(tag,text,className)=>{const element=document.createElement(tag);element.textContent=text;if(className)element.className=className;return element;};
const cycleNames={early_recovery:'早期复苏',fundamental_confirmation:'基本面确认',full_flywheel:'正反馈形成',narrative_expansion:'叙事扩张',bubble_formation:'泡沫形成',narrative_divergence:'叙事背离',fundamental_divergence:'基本面背离',cycle_deterioration:'周期恶化',undetermined:'证据不足'};
const trackingLabels={paused:'未跟踪',recovering:'恢复中',queued:'等待研究',analyzing:'正在研究',validating:'持续验证',waiting:'等待触发',error:'等待恢复'};
const actionNames={buy:'BUY · 买入观察',hold:'HOLD · 维持观察',sell:'SELL · 卖出观察',insufficient:'证据不足'};
let trackingState={tasks:[]},trackingLoading=false,trackingSignature='';
const historyPages=new Map();
let wechatState=null,wechatPolling=false;

async function request(action,payload){const response=await window.monitor.request(action,payload);if(!response.ok)throw Error(response.error||'请求失败');return response.data;}
async function trackingConfigure(item,enabled,extra={}){
 try{await request('tracking-configure',{category:item.category,symbol:item.symbol,enabled,...extra});trackingSignature='';await trackingRefresh();}
 catch(error){$('tracking-message').textContent=error.message;}
}

function historyFor(task){
 let state=historyPages.get(task.id);
 if(!state){state={items:[],visible:3,total:0,loading:false};historyPages.set(task.id,state);}
 const records=new Map([...state.items,...(task.events||[])].map(item=>[item.id,item]));
 state.items=Array.from(records.values()).sort((a,b)=>b.created-a.created||b.id.localeCompare(a.id));
 state.total=task.history_total??state.items.length;
 return state;
}

async function loadMoreHistory(task,button){
 const state=historyPages.get(task.id);
 if(!state||state.loading)return;
 if(state.visible<state.items.length){state.visible+=5;trackingSignature='';await trackingRefresh();return;}
 if(state.items.length>=state.total)return;
 const oldest=state.items.at(-1);
 if(!oldest)return;
 state.loading=true;button.disabled=true;button.textContent='读取中…';
 try{
  const page=await request('tracking-history',{category:task.category,symbol:task.symbol,before:oldest.created+'|'+oldest.id});
  const records=new Map([...state.items,...page.items].map(item=>[item.id,item]));
  state.items=Array.from(records.values()).sort((a,b)=>b.created-a.created||b.id.localeCompare(a.id));
  state.visible+=5;
  if(!page.has_more)state.total=state.items.length;
  trackingSignature='';
 }catch(error){$('tracking-message').textContent='历史记录暂不可用：'+error.message;}
 finally{state.loading=false;button.disabled=false;await trackingRefresh();}
}

function renderHistory(task,openSections){
 const state=historyFor(task),section=line('section','','tracking-history-section');
 const heading=line('div','','tracking-history-heading');heading.append(line('h3','研究历程'),line('small',state.total+' 条记录'));section.append(heading);
 if(!state.items.length){section.append(line('p','研究完成后，这里会保留每次判断和修订。','tracking-history-empty'));return section;}
 for(const event of state.items.slice(0,state.visible)){
  const entry=line('article','','tracking-history-entry');const detail=document.createElement('details');detail.dataset.section='history-'+event.id;detail.open=openSections.includes(detail.dataset.section);
  const heading=document.createElement('summary');heading.append(line('time',time(event.created*1000)));
  if(event.result.action)heading.append(line('span',actionNames[event.result.action]||'证据不足','tracking-history-action'));
  heading.append(line('strong',compact(event.result.conclusion||event.result.summary,110)||'研究记录'));
  if(event.result.change_vs_previous)heading.append(line('small','变化：'+compact(event.result.change_vs_previous,90)));
  detail.append(heading);
  detail.append(line('p',event.result.summary||'无详细分析。','tracking-history-analysis'));
  const evidence=[...(event.result.evidence||[]),...(event.result.contradictions||[]).map(value=>'反证：'+value),event.result.invalidation&&'失效条件：'+event.result.invalidation].filter(Boolean).join('\n');
  if(evidence)detail.append(line('p',evidence,'tracking-history-evidence'));
  entry.append(detail);section.append(entry);
 }
 if(state.visible<state.total){const more=line('button','查看更多记录','tracking-history-more');more.onclick=()=>loadMoreHistory(task,more);section.append(more);}
 return section;
}

function renderProbabilities(probabilities){
 const section=line('section','','tracking-probabilities');
 section.append(line('h3','动态胜率 · 历史相似行情'));
 if(!probabilities){section.append(line('small','历史样本不足，暂不计算。'));return section;}
 const shares=line('div','','tracking-probability-grid');
 for(const [key,label] of [['buy','BUY'],['sell','SELL'],['hold','HOLD']]){
  const item=line('div','','tracking-probability probability-'+key);
  item.append(line('span',label),line('strong',Number(probabilities.percentages[key]).toFixed(1)+'%'));
  shares.append(item);
 }
 section.append(shares);
 section.append(line('small','未来 '+probabilities.horizon_bars+' 根 '+probabilities.interval+' K 线 · 历史 '+probabilities.observation_bars+' 窗 / 约 '+probabilities.effective_blocks+' 个独立时段 · 更新 '+time(probabilities.as_of*1000)));
 section.append(line('small','三项合计 100%；表示涨、跌、震荡的历史条件占比，不是交易收益率。'));
 return section;
}

function renderCard(task,openSections){
 const card=document.createElement('article');card.className='tracking-card';card.dataset.task=task.id;
 const head=document.createElement('header');const lamp=line('span','','tracking-light '+task.light);lamp.title=trackingLabels[task.phase]||task.phase;
 const title=line('strong',task.symbol+' · '+task.interval);
 const toggle=line('button',task.enabled?'暂停':'开启');toggle.onclick=()=>trackingConfigure(task,!task.enabled);
 head.append(lamp,title,toggle);card.append(head);
 card.append(line('small',(trackingLabels[task.phase]||task.phase)+'  ·  长期阶段：'+(cycleNames[task.previous?.cycle_state]||'待建立'),'tracking-state'));
 if(task.error)card.append(line('p',task.error,'tracking-error'));
 card.append(renderProbabilities(task.probabilities));

 const previous=task.previous||{};
 if(previous.action){
  const action=line('div',actionNames[previous.action]||'证据不足','tracking-action action-'+previous.action);
  if(previous.action_status==='provisional')action.append(line('small','暂定判断'));
  if(previous.action_status==='tactical')action.append(line('small','量价战术判断'));
  card.append(action);
  if(previous.action_reason)card.append(line('p',compact(previous.action_reason,120),'tracking-action-reason'));
 }
 const legacyConclusion=previous.cycle_state==='undetermined'?'长期循环尚无足够证据，维持观察。':compact(previous.thesis,80);
 const conclusion=compact(previous.conclusion,90)||legacyConclusion||'正在建立长期判断。';
 const levels=[task.plan?.upper&&'上方 '+task.plan.upper,task.plan?.lower&&'下方 '+task.plan.lower].filter(Boolean).join('、');
 const recommendation=compact(previous.recommendation,110)||(levels?'关注'+levels+'的确认或失效，再修订判断。':'等待更长周期和外部证据确认，再修订判断。');
 const verdict=line('div','','tracking-verdict');verdict.append(line('span','结论'),line('strong',conclusion));card.append(verdict);
 const advice=line('div','','tracking-advice');advice.append(line('span','建议'),line('p',recommendation));card.append(advice);
 if(task.watch_signal)card.append(line('small','观察中：'+(task.watch_signal.kind==='price_change'?'价格变化':'成交量放大')+'，待更长周期验证','tracking-watch'));

 const more=document.createElement('details');more.dataset.section='analysis';more.open=openSections.includes('analysis');more.append(line('summary','展开分析与依据'));
 more.append(line('p',previous.summary||'尚无研究结果。','tracking-analysis'));
 const evidence=[previous.change_vs_previous&&'相比上次：'+previous.change_vs_previous,...(previous.evidence||[]),...(previous.contradictions||[]).map(value=>'反证：'+value),...(previous.unknowns||[]).map(value=>'未验证：'+value),previous.invalidation&&'失效条件：'+previous.invalidation].filter(Boolean).join('\n');
 if(evidence)more.append(line('p',evidence,'tracking-evidence'));
 more.append(line('small','行情 '+time(task.last_data*1000)+' · 研究 '+time(task.last_research*1000)+(task.next_review?' · 下次复核 '+time(task.next_review*1000):'')));
 card.append(more);

 card.append(renderHistory(task,openSections));

 const settings=document.createElement('details');settings.dataset.section='settings';settings.open=openSections.includes('settings');settings.append(line('summary','研究方向'));
 const note=document.createElement('textarea');note.value=task.note||'';note.maxLength=2000;note.placeholder='补充需要核验的问题';note.setAttribute('aria-label',task.symbol+' 研究备注');settings.append(note);
 const save=line('button','保存研究方向');save.onclick=()=>trackingConfigure(task,task.enabled,{note:note.value});settings.append(save);card.append(settings);
 return card;
}

async function trackingRefresh(){
 if(trackingLoading)return;trackingLoading=true;
 try{
  trackingState=await request('tracking');
  const item=selected();$('tracking-selected').textContent=item?item.symbol+' · '+item.category:'先选择品种，或直接关注 ZEC';$('tracking-enable').disabled=!item;
  $('tracking-message').textContent=trackingState.worker_online?'':'研究执行器尚未连接，已开启任务会在连接后恢复。';
  const signature=JSON.stringify(trackingState);if(signature===trackingSignature)return;
  if($('tracking-tasks').contains(document.activeElement)&&document.activeElement.tagName==='TEXTAREA')return;
  const scrollTop=$('tracking-console').scrollTop;
  const openSections=new Map(Array.from($('tracking-tasks').querySelectorAll('.tracking-card')).map(card=>[card.dataset.task,Array.from(card.querySelectorAll('details[open]')).map(detail=>detail.dataset.section)]));
  trackingSignature=signature;
  const nodes=(trackingState.tasks||[]).map(task=>renderCard(task,openSections.get(task.id)||[]));
  if(!nodes.length){const empty=line('p','尚无跟踪任务。开启后，切换图表也会继续跟踪。');empty.style.padding='18px';nodes.push(empty);}
  $('tracking-tasks').replaceChildren(...nodes);
  $('tracking-console').scrollTop=scrollTop;
 }catch(error){$('tracking-message').textContent='跟踪服务暂不可用：'+error.message;}
 finally{trackingLoading=false;}
}

async function wechatRefresh(){
 try{
  wechatState=await request('wechat');
  $('wechat-state').textContent=wechatState.enabled?(wechatState.awaiting_inbound?'等待微信消息':'通知已开启'):wechatState.connected?'已连接 · 通知关闭':'未连接';
  $('wechat-toggle').disabled=!wechatState.connected;
  $('wechat-toggle').textContent=wechatState.enabled?'关闭通知':'开启通知';
  $('wechat-cadence').value=String(wechatState.cadence_hours);
  if(wechatState.last_error)$('wechat-help').textContent='连接暂不可用：'+wechatState.last_error+'；等待自动重试。';
  const recent=(wechatState.messages||[]).slice(0,3);
  $('wechat-delivery').replaceChildren(...recent.map(item=>line('small',item.task+' · '+({sent:'接口已接受',pending:'待发送',unknown:'结果未确认，已停止重试',rejected:'接口拒收，已停止重试',superseded:'已被新消息取代'}[item.status]||item.status))));
 }catch(error){$('wechat-help').textContent='微信状态暂不可用：'+error.message;}
}

async function pollWechatLogin(code){
 if(wechatPolling)return;wechatPolling=true;
 try{
  const state=await request('wechat-login-status',code?{verify_code:code}:{});
  if(state.connected){$('wechat-qr').hidden=true;$('wechat-verify').hidden=true;$('wechat-help').textContent='已连接。给 ClawBot 发一条消息以建立主动通知会话。';await wechatRefresh();return;}
  if(state.status==='need_verifycode'){$('wechat-verify').hidden=false;$('wechat-help').textContent='输入手机微信显示的验证码。';return;}
  if(state.status==='expired'||state.status==='verify_code_blocked'){$('wechat-qr').hidden=true;$('wechat-help').textContent='二维码已失效，请重新连接。';return;}
  if(state.status==='binded_redirect'){$('wechat-qr').hidden=true;$('wechat-help').textContent='该微信已绑定现有 ClawBot；如本机未连接，请先在原实例解除绑定。';return;}
  $('wechat-help').textContent=state.status==='scaned'?'已扫码，等待手机确认…':'等待扫码确认…';
  setTimeout(()=>pollWechatLogin(),1000);
 }catch(error){$('wechat-help').textContent='连接失败：'+error.message;}
 finally{wechatPolling=false;}
}

$('wechat-login').onclick=async()=>{try{const state=await request('wechat-login');$('wechat-qr').src=state.image;$('wechat-qr').hidden=false;$('wechat-help').textContent='请用个人微信扫描二维码。';pollWechatLogin();}catch(error){$('wechat-help').textContent='生成二维码失败：'+error.message;}};
$('wechat-verify-submit').onclick=()=>{const value=$('wechat-verify-code').value.trim();if(/^\d{1,10}$/.test(value))pollWechatLogin(value);};
$('wechat-toggle').onclick=async()=>{try{await request('wechat-configure',{enabled:!wechatState.enabled});await wechatRefresh();}catch(error){$('wechat-help').textContent=error.message;}};
$('wechat-cadence').onchange=async()=>{try{await request('wechat-configure',{cadence_hours:Number($('wechat-cadence').value)});await wechatRefresh();}catch(error){$('wechat-help').textContent=error.message;}};

$('tracking-enable').onclick=()=>{const item=selected();if(item)trackingConfigure(item,true,{interval:$('tracking-interval').value});};
$('tracking-zec').onclick=()=>trackingConfigure({category:'USDT-FUTURES',symbol:'ZECUSDT'},true,{interval:'15m'});
request('tracking-selection').then(item=>{if(item){$('tracking-symbol').value=item.symbol;$('tracking-category').value=item.category;trackingRefresh();}}).catch(()=>{});
trackingRefresh();setInterval(trackingRefresh,5000);
wechatRefresh();setInterval(wechatRefresh,10000);
