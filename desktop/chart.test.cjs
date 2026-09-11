const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const chart = fs.existsSync(__dirname + '/chart.js') ? require('./chart.js') : {};
const candle = (time,price=100) => ({time,open:price,high:price+2,low:price-1,close:price+1,volume:12});
test('normalizes numeric strings, milliseconds and reverse ordered candles',()=>{
  assert.equal(typeof chart.normalize,'function');
  const rows=chart.normalize([{...candle(1700000060000),open:'100'},candle(1700000000)]);
  assert.deepEqual(rows.map(x=>x.time),[1700000000,1700000060]);
  assert.equal(rows[1].open,100);
});
test('empty and flat single candle have safe finite chart bounds',()=>{
  assert.equal(typeof chart.bounds,'function');
  assert.equal(chart.bounds([]),null);
  const b=chart.bounds([{time:1,open:10,high:10,low:10,close:10,volume:0}]);
  assert.ok(b.max>10 && b.min<10 && b.volume>0);
});
test('rejects corrupt, nonfinite, inconsistent and duplicate candle data',()=>{
  assert.equal(typeof chart.normalize,'function');
  for(const rows of [[{...candle(1),close:null}],[{...candle(1),volume:-1}],[{...candle(1),high:1}],[{...candle(1),open:Infinity}],[candle(1),candle(1)],{}]) assert.throws(()=>chart.normalize(rows));
});
test('visible bars remain bounded for zoom and few samples',()=>{
  assert.equal(typeof chart.visible,'function');
  assert.equal(chart.visible([candle(1)],80,0).length,1);
  assert.equal(chart.visible([],80,0).length,0);
  const rows=Array.from({length:100},(_,i)=>candle(i+1));
  assert.deepEqual(chart.visible(rows,20,10).map(x=>x.time),rows.slice(70,90).map(x=>x.time));
});
test('a failed update clears previous prices instead of drawing a false chart',()=>{
  const view=Object.create(chart.CandleChart.prototype);
  view.rows=[candle(1)];view.offset=0;
  let drawn;
  view.draw=()=>{drawn=[...view.rows];};
  assert.throws(()=>view.setData([{...candle(2),close:null}]));
  assert.deepEqual(drawn,[]);
  assert.deepEqual(view.rows,[]);
  view.setData([]);
  assert.deepEqual(view.rows,[]);
});
