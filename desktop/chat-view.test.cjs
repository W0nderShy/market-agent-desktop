const {test}=require('node:test');const assert=require('node:assert/strict');const {turns}=require('./chat-view.js');
const e=(type,data,seq)=>({event:{type,data,seq}});
test('only the final assistant answer escapes the collapsed process',()=>{const result=turns([e('turn/start',{turn:1},0),e('user/message',{content:[{type:'text',text:'分析'}]},1),e('assistant/message',{turn:1,message:{content:[{type:'text',text:'正在搜索'},{type:'tool-call',name:'web_search'}]}},2),e('tool/result',{turn:1,message:{content:[]}},3),e('assistant/message',{turn:1,message:{content:[{type:'text',text:'最终结论'}]}},4),e('turn/end',{turn:1,reason:{kind:'completed'}},5)]);assert.equal(result[0].answer,'最终结论');assert.equal(result[0].process.length,2);assert.equal(result[0].user,'分析')});
test('running and failed rounds do not label intermediate prose as final',()=>{for(const reason of [null,'error']){const records=[e('turn/start',{turn:2},1),e('assistant/message',{turn:2,message:{content:[{type:'text',text:'先检查'}]}},2)];if(reason)records.push(e('turn/end',{turn:2,reason:{kind:reason}},3));assert.equal(turns(records)[0].answer,'')}});

test('automatic context is not shown as a user message',()=>{const r=turns([e('user/message',{source:{kind:'user'},content:[{type:'text',text:'hello\n\n[终端上下文] hidden'}]},1),e('user/message',{source:{kind:'plugin'},content:[{type:'text',text:'runtime policy'}]},2)]);assert.equal(r[0].user,'hello')});

test('internal analyst instructions and chart context stay out of user bubbles',()=>{
 const content=[{type:'text',text:'分析 CPI 的影响'},{type:'text',text:'[终端分析师表达要求]\n内部要求\n[当前图表上下文] 数据'}];
 assert.equal(turns([e('user/message',{content},1)])[0].user,'分析 CPI 的影响');
 content[1].text='[当前图表未就绪，不得假称看到了 K 线。]';
 assert.equal(turns([e('user/message',{content},1)])[0].user,'分析 CPI 的影响');
 assert.equal(turns([e('user/message',{content:[{type:'text',text:'[终端分析师表达要求] 这是我输入的内容'}]},1)])[0].user,'[终端分析师表达要求] 这是我输入的内容');
});
