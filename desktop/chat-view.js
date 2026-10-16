(function(root){
'use strict';
const blocks=e=>e.data?.message?.content||e.data?.content||[];
const text=e=>blocks(e).filter(b=>b.type==='text').map(b=>b.text).join('\n');
const userText=e=>blocks(e).filter((b,i)=>b.type==='text'&&!(i>0&&(/^\[(?:当前图表|终端分析师表达要求)/).test(b.text||''))).map(b=>b.text).join('\n');
function turns(records){
 const result=[];let current;
 const ensure=id=>{if(!current||String(current.id)!==String(id)){current=result.find(t=>String(t.id)===String(id));if(!current){current={id,user:'',process:[],answer:'',state:'running'};result.push(current);}}return current;};
 for(const {event:e} of records){if(!e)continue;const t=ensure(e.data?.turn??current?.id??'history');
 if(e.type==='user/message'&&(!e.data?.source?.kind||e.data.source.kind==='user'))t.user+=(t.user?'\n':'')+userText(e).split('\n\n[终端上下文]')[0];
 if(e.type==='assistant/message'||e.type==='tool/result')t.process.push(e);
 if(e.type==='turn/end'){t.state=e.data?.reason?.kind||'completed';if(t.state==='completed'){const last=t.process.at(-1);if(last?.type==='assistant/message'&&!blocks(last).some(b=>b.type==='tool-call')){t.answer=text(last);if(t.answer)t.process.pop();}}}
 }
 return result.filter(t=>t.user||t.process.length||t.answer);
}
function inline(node,value){
 const pattern=/(\*\*([^*]+)\*\*|`([^`]+)`)/g;let at=0,match;
 while((match=pattern.exec(value))){node.append(document.createTextNode(value.slice(at,match.index)));const tag=document.createElement(match[2]?'strong':'code');tag.textContent=match[2]||match[3];node.append(tag);at=pattern.lastIndex;}node.append(document.createTextNode(value.slice(at)));
}
function markdown(value){const out=document.createElement('div');out.className='answer-markdown';let list=null,code=null;
 for(const line of value.split('\n')){if(line.startsWith('```')){if(code)code=null;else{code=document.createElement('pre');out.append(code);}list=null;continue;}if(code){code.textContent+=line+'\n';continue;}if(!line.trim()){list=null;continue;}
 const heading=line.match(/^#{1,6}\s+(.+)/),bullet=line.match(/^\s*(?:[-*]|\d+[.)])\s+(.+)/);
 if(bullet){if(!list){list=document.createElement(/^\s*\d/.test(line)?'ol':'ul');out.append(list);}const li=document.createElement('li');inline(li,bullet[1]);list.append(li);continue;}
 list=null;const p=document.createElement(heading?'h4':'p');inline(p,heading?heading[1]:line);out.append(p);
 }return out;}
const opened=new Map();let lastSignature='';
function render(box,snapshot){const signature=JSON.stringify([snapshot.header?.id,snapshot.cursor,snapshot.assistantStream?.revision]);if(signature===lastSignature)return;lastSignature=signature;
 const near=box.scrollHeight-box.scrollTop-box.clientHeight<80,scroll=box.scrollTop,nodes=[];
 for(const t of turns(snapshot.records||[])){
 if(t.user){const user=document.createElement('div');user.className='chat-user';const role=document.createElement('div');role.className='message-role user-role';role.textContent='你';const body=document.createElement('div');body.textContent=t.user;user.append(role,body);nodes.push(user);}
 if(t.process.length||t.state==='running'){
 const group=document.createElement('details');group.className='turn-process';const key=`${snapshot.header?.id}:${t.id}`;group.open=opened.get(key)||false;group.addEventListener('toggle',()=>opened.set(key,group.open));const label=document.createElement('summary');label.textContent=t.state==='running'?'正在处理…':t.state==='completed'?'查看处理过程':'处理过程 · 本轮未完成';group.append(label);
 for(const event of t.process){const item=document.createElement('div');item.className='process-item';if(event.type==='tool/result'){const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent='工具结果';const pre=document.createElement('pre');const content=blocks(event).flatMap(b=>b.type==='tool-result'?b.content||[]:[b]);pre.textContent=content.filter(b=>b.type==='text').map(b=>b.text).join('\n');detail.append(summary,pre);item.append(detail);}else{const commentary=text(event);if(commentary)item.append(markdown(commentary));for(const b of blocks(event).filter(b=>b.type==='tool-call')){const title=document.createElement('p');title.textContent='调用 '+b.name;const pre=document.createElement('pre');pre.textContent=typeof b.arguments==='string'?b.arguments:JSON.stringify(b.arguments);item.append(title,pre);}}group.append(item);}
 nodes.push(group);}
 if(t.answer){const answer=document.createElement('div');answer.className='chat-assistant final-answer';const role=document.createElement('div');role.className='message-role assistant-role';role.textContent='Agent';answer.append(role,markdown(t.answer));nodes.push(answer);}
 }
 box.replaceChildren(...nodes);box.scrollTop=near?box.scrollHeight:scroll;
}
const api={turns,render,markdown};if(typeof module!=='undefined')module.exports=api;else root.ChatView=api;
})(globalThis);
