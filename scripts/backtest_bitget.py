"""Technical-rule experiment only; not a role-based BUY/SELL/HOLD backtest."""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from market_monitor.backtest import fetch_closed, replay
from market_monitor.bitget import Bitget

SHANGHAI=timezone(timedelta(hours=8))


def local(seconds):
    return datetime.fromtimestamp(seconds,SHANGHAI).strftime('%Y-%m-%d %H:%M')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('symbols',nargs='+',help='Bitget USDT-FUTURES symbols, e.g. ARMUSDT SOXXUSDT')
    parser.add_argument('--since',default='2026-06-01',help='YYYY-MM-DD at 00:00 Asia/Shanghai')
    parser.add_argument('--pages',type=int,default=8)
    args=parser.parse_args()
    since=int(datetime.fromisoformat(args.since+'T00:00:00+08:00').timestamp())
    feed=Bitget()
    outputs=[]
    try:
        for symbol in args.symbols:
            rows=fetch_closed(feed,symbol=symbol,pages=args.pages)
            result=replay(rows,trade_from=since)
            result.update(source='Bitget public v3 market candles',symbol=symbol,
                          category='USDT-FUTURES',interval='4H',requested_since=since,
                          first_available=rows[0][0],strategy_kind='technical_rule_experiment',
                          role_backtest=False)
            path=ROOT/'runtime'/f'backtest_{symbol.lower()}_{args.since}.json'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'input_rows':rows,'result':result},ensure_ascii=False,
                                       indent=2,allow_nan=False),encoding='utf-8')
            outputs.append({'symbol':symbol,'bars':len(rows),'first_available':local(rows[0][0]),
                            'first_decision_bar':local(result['first_decision_bar']),
                            'benchmark_from':local(result['buy_hold_start']),
                            'last_bar_close':local(result['end']+14400),
                            'net_return_pct':result['net_return_pct'],
                            'max_drawdown_pct':result['max_drawdown_pct'],
                            'buy_hold_pct':result['buy_hold_pct'],
                            'closed_trades':result['closed_trades'],
                            'win_rate_pct':result['win_rate_pct'],
                            'open_position':result['open_position'],
                            'next_bar_signal':result['next_bar_signal'],
                            'last_close':result['last_close'],
                            'last_trades':result['trades'][-5:],
                            'file':str(path)})
    finally:
        feed.close()
    print(json.dumps(outputs,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
