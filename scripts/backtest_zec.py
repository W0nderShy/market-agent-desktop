"""Reproducible ZECUSDT Bitget 4H market-skill replay; simulation only."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from market_monitor.backtest import fetch_closed, replay
from market_monitor.bitget import Bitget


def stamp(seconds):
    return datetime.fromtimestamp(seconds,timezone.utc).isoformat(timespec='minutes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages',type=int,default=8)
    parser.add_argument('--output',type=Path,default=ROOT/'runtime'/'zec_backtest_4h.json')
    args = parser.parse_args()
    feed=Bitget()
    try:
        rows=fetch_closed(feed,pages=args.pages)
    finally:
        feed.close()
    result=replay(rows)
    result['source']='Bitget public v3 market candles'
    result['symbol']='ZECUSDT'
    result['category']='USDT-FUTURES'
    result['interval']='4H'
    result['assumptions']=['No leverage, all-in long or cash.',
                           'Decision on a closed 4H bar; fill at next bar open.',
                           'Taker fee and assumed slippage charged on both sides.',
                           'No funding, liquidation, spread history, tax, or capacity model.',
                           'Five installed skill libraries evaluated point-in-time; no macro/on-chain/valuation history.']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'input_rows':rows,'result':result},ensure_ascii=False,
                                      allow_nan=False,indent=2),encoding='utf-8')
    summary={k:v for k,v in result.items() if k not in ('trades','signals','current_state')}
    summary['start']=stamp(result['start'])
    summary['end']=stamp(result['end'])
    summary['last_trades']=result['trades'][-5:]
    summary['latest_skills']={k:{'signal':v.get('signal'),'pattern':v.get('pattern'),
                                 'volume_ratio':v.get('volume_ratio'),
                                 'nearest_support':v.get('nearest_support'),
                                 'nearest_resistance':v.get('nearest_resistance')}
                              for k,v in result['current_state'].items()}
    print(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
    print('Saved:',args.output)


if __name__=='__main__':
    main()
