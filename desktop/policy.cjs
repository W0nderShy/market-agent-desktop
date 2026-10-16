function requestSpec(action, payload) {
  if(action==='tracking')return {method:'GET',path:'/api/tracking'};
  if(action==='tracking-history'&&/^[A-Z0-9]{1,40}$/.test(payload?.symbol||'')&&/^(SPOT|USDT-FUTURES|USDC-FUTURES|COIN-FUTURES)$/.test(payload?.category||'')&&(payload?.before===undefined||/^[0-9]+(?:\.[0-9]+)?\|[A-Za-z0-9-]{1,64}$/.test(payload.before))){const query=new URLSearchParams({task:payload.category+':'+payload.symbol,limit:'10'});if(payload.before)query.set('before',payload.before);return {method:'GET',path:'/api/tracking/history?'+query};}
  if(action==='tracking-configure'&&typeof payload?.enabled==='boolean')return {method:'PUT',path:'/api/tracking/configure',body:{category:payload.category,symbol:payload.symbol,enabled:payload.enabled,interval:payload.interval,note:payload.note}};
  if (action === 'status') return {method:'GET', path:'/api/status'};
  if (action === 'poll') return {method:'POST', path:'/api/poll'};
  if (action === 'candles') {
    const q = new URLSearchParams({category:payload?.category||'SPOT',symbol:payload?.symbol||'',interval:payload?.interval||'1m'});
    return {method:'GET',path:`/api/candles?${q}`};
  }
  if (action === 'markets') return {method:'GET',path:'/api/markets?'+new URLSearchParams({category:payload?.category||'USDT-FUTURES'})};
  if (action === 'instruments') {
    const q = new URLSearchParams({category:payload?.category || 'SPOT', symbol:payload?.symbol || ''});
    return {method:'GET', path:`/api/instruments?${q}`};
  }
  if (action === 'watchlist' && Array.isArray(payload?.items) && payload.items.length <= 50) {
    return {method:'PUT',path:'/api/watchlist',body:{items:payload.items.map(({symbol,category})=>({symbol,category}))}};
  }
  throw new Error('Unsupported monitor operation');
}
module.exports = {requestSpec};
