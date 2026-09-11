function requestSpec(action, payload) {
  if (action === 'status') return {method:'GET', path:'/api/status'};
  if (action === 'poll') return {method:'POST', path:'/api/poll'};
  if (action === 'candles') {
    const q = new URLSearchParams({category:payload?.category||'SPOT',symbol:payload?.symbol||'',interval:payload?.interval||'1m'});
    return {method:'GET',path:`/api/candles?${q}`};
  }
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
