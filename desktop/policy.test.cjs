const { test } = require('node:test');
const assert = require('node:assert/strict');
const { requestSpec } = require('./policy.cjs');
test('only narrow monitor operations are exposed to renderer', () => {
  assert.deepEqual(requestSpec('status'), { method: 'GET', path: '/api/status' });
  assert.throws(() => requestSpec('https://evil.test'));
  assert.throws(() => requestSpec('watchlist', {items:'bad'}));
});
test('instrument query cannot escape the allowed path', () => {
  const spec = requestSpec('instruments', {category:'SPOT',symbol:'BTCUSDT&token=secret'});
  assert.equal(spec.path, '/api/instruments?category=SPOT&symbol=BTCUSDT%26token%3Dsecret');
});
test('candles are restricted to the candle endpoint',()=>{
  assert.equal(requestSpec('candles',{category:'SPOT',symbol:'BTCUSDT',interval:'5m'}).path,'/api/candles?category=SPOT&symbol=BTCUSDT&interval=5m');
});
