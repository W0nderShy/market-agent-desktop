"""Run five audited market-skills analyzers against the terminal Bitget snapshot only."""
import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor' / 'market-skills'))
from analysis.skill_loader import load_skill

SKILLS = ('market-volume', 'market-trend', 'market-s-r', 'market-breakout', 'market-exhaustion')
SECONDS = {'1m':60,'5m':300,'15m':900,'1H':3600,'4H':14400,'1D':86400}
MINIMUM = {'market-volume':60,'market-trend':200,'market-s-r':60,'market-breakout':200,'market-exhaustion':60}

def analyze_snapshot(snapshot, skill='all', now_ms=None):
    if skill != 'all' and skill not in SKILLS:
        raise ValueError('unsupported_skill')
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    if not isinstance(snapshot, dict) or snapshot.get('available') is False:
        raise ValueError('chart_unavailable')
    stamp = snapshot.get('capturedAt')
    if not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or not 0 <= now_ms-stamp <= 180000:
        raise ValueError('chart_stale_refresh_terminal')
    interval = snapshot.get('interval')
    if interval not in SECONDS:
        raise ValueError('invalid_interval')
    if snapshot.get('category') not in ('SPOT','USDT-FUTURES','USDC-FUTURES','COIN-FUTURES') or not isinstance(snapshot.get('symbol'),str):
        raise ValueError('invalid_market')
    rows = snapshot.get('candles')
    if not isinstance(rows,list) or not 1 <= len(rows) <= 300:
        raise ValueError('invalid_candles')
    previous=0
    gaps=0
    for row in rows:
        if not isinstance(row,list) or len(row)!=6 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in row):
            raise ValueError('invalid_ohlcv')
        t,o,h,l,c,v=row
        if t<=previous or t>stamp/1000 or min(o,h,l,c)<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c):
            raise ValueError('invalid_ohlcv')
        if previous and t-previous!=SECONDS[interval]:gaps+=1
        previous=t
    if gaps:
        raise ValueError('non_contiguous_candles_refresh_terminal')
    if stamp/1000-rows[-1][0]>SECONDS[interval]+180:
        raise ValueError('exchange_candles_stale')
    closed=[row for row in rows if (row[0]+SECONDS[interval])*1000<=stamp]
    names=SKILLS if skill=='all' else (skill,)
    results={}
    for name in names:
        if len(closed)<MINIMUM[name]:
            results[name]={'error':'insufficient_closed_candles','required':MINIMUM[name],'available':len(closed)}
            continue
        module=load_skill(name)
        if module is None:raise ValueError('missing_vendored_analyzer')
        results[name]=module.analyze(closed,interval=interval.lower(),period='chart')
        if name=='market-exhaustion':
            vol=results[name].get('input_scores',{}).get('market-volatility')
            if isinstance(vol,dict):
                # Upstream annualizes with 252 daily samples; keep only relative regimes for crypto/intraday.
                vol.pop('realized_vol_7d',None);vol.pop('realized_vol_30d',None)
                if 'percentile_rank_30d' in vol:vol['percentile_rank_30bars']=vol.pop('percentile_rank_30d')
        if name=='market-breakout' and not results[name].get('signals',{}).get('volume_confirmation',{}).get('present'):
            results[name]['interpretation_warning']='Volume confirmation is absent. Do not describe the upstream label as a volume-confirmed breakout.'
    return {'source':'Bitget','symbol':snapshot['symbol'],'category':snapshot['category'],'interval':interval,
            'captured_at_ms':stamp,'snapshot_age_ms':now_ms-stamp,'input_bars':len(rows),'analyzed_bars':len(closed),
            'excluded_unclosed_bars':len(rows)-len(closed),'last_analyzed_time':closed[-1][0] if closed else None,
            'results':results,'limitations':['Scores are heuristic, not probabilities or trading instructions.',
            'All lookbacks refer to bars of the selected interval, not calendar days.',
            'Support/resistance uses upstream fixed clustering thresholds; verify against chart structure.',
            'Some upstream values are rounded to two decimals; use original candles for precise prices.']}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill',choices=['all',*SKILLS],nargs='?',default='all')
    args=parser.parse_args(argv)
    try:
        snapshot=json.loads((ROOT/'runtime'/'market-context.json').read_text(encoding='utf-8'))
        result=analyze_snapshot(snapshot,args.skill)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except (ValueError,OSError,TypeError) as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,ValueError) else 'chart_read_failed','action':'Refresh the selected chart in the terminal, then retry.'}))
        return 2

if __name__=='__main__':
    raise SystemExit(main())
