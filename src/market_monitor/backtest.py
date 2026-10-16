"""Point-in-time technical-rule experiment; not a long-term role backtest."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .tracking import normalize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'vendor' / 'market-skills'))
from analysis.skill_loader import load_skill  # noqa: E402

STEP = 14400
NAMES = ('market-trend', 'market-volume', 'market-s-r', 'market-breakout', 'market-exhaustion')
FEE = 0.0006  # Standard Bitget futures taker fee per side; actual account rate may vary.
SLIPPAGE = 0.0002  # Explicit scenario assumption, not measured execution slippage.


def fetch_closed(feed, symbol='ZECUSDT', interval='4H', pages=8, now=None):
    """Fetch recent and older public bars; reject gaps instead of silently bridging them."""
    if interval != '4H' or not 0 <= pages <= 30:
        raise ValueError('invalid_backtest_parameters')
    now = int(time.time() if now is None else now)
    step = STEP
    latest = feed.candles('USDT-FUTURES', symbol, interval, 1000)
    if not latest:
        raise ValueError('no_market_history')
    rows = {int(row[0]): row for row in latest}
    cursor = min(rows)
    for _ in range(pages):
        older = feed.history_candles('USDT-FUTURES', symbol, interval, cursor, 100)
        if not older:
            break
        new_cursor = min(int(row[0]) for row in older)
        if new_cursor >= cursor:
            break
        rows.update((int(row[0]), row) for row in older)
        cursor = new_cursor
    closed = normalize([rows[k] for k in sorted(rows)], step, now)
    if len(closed) < 260:
        raise ValueError('insufficient_closed_history')
    if any(b[0] - a[0] != step for a, b in zip(closed, closed[1:])):
        raise ValueError('historical_candle_gap')
    return closed


def _atr(rows, period=14):
    tail = rows[-period:]
    if len(rows) < period + 1:
        raise ValueError('insufficient_atr_history')
    start = len(rows) - period
    return sum(max(rows[i][2]-rows[i][3], abs(rows[i][2]-rows[i-1][4]),
                   abs(rows[i][3]-rows[i-1][4])) for i in range(start, len(rows))) / period


def skill_state(closed):
    """Calculate each installed skill from bars available at this historical instant."""
    window = closed[-300:]
    return {name: load_skill(name).analyze(window, interval='4h', period='chart')
            for name in NAMES}


def _decision(state):
    trend = state['market-trend']
    volume = state['market-volume']
    breakout = state['market-breakout']
    exhaustion = state['market-exhaustion']
    pattern = breakout['pattern']
    buy = (trend['signal'] == 'STRONG_UPTREND'
           and pattern['present'] and pattern['direction'] == 'bull'
           and pattern['classification'] in ('FRESH', 'CONFIRMED')
           and breakout['signals']['volume_confirmation']['present']
           and volume['volume_ratio'] >= 1
           and not exhaustion['pattern']['present'])
    sell = (trend['signal'] not in ('STRONG_UPTREND', 'UPTREND')
            or exhaustion['pattern']['present']
            or pattern['classification'] == 'FAILED')
    return buy, sell


def replay(rows, *, fee=FEE, slippage=SLIPPAGE, state_fn=skill_state, trade_from=None):
    """Signals use bar i close; trades fill at i+1 open, or a later intrabar stop.

    One unlevered notional unit, all-in when long, cash when flat. Funding is excluded.
    The first 200 bars are warm-up. The final position is marked to market, not
    described as a completed sell trade.
    """
    if len(rows) < 260 or any(b[0]-a[0] != 14400 for a,b in zip(rows,rows[1:])):
        raise ValueError('invalid_replay_history')
    first = max(200, next((i for i, row in enumerate(rows) if trade_from is None or row[0] >= trade_from), len(rows)))
    if first >= len(rows)-1:
        raise ValueError('insufficient_trading_window')
    cash, units, entry, stop = 1.0, 0.0, None, None
    trades, equity, signals = [], [], []
    pending = None
    current = None
    for i in range(first, len(rows)):
        bar = rows[i]
        if pending:
            action, decision_time, planned_stop = pending
            if action == 'BUY' and not units:
                fill = bar[1] * (1+slippage)
                prior = cash
                units = cash * (1-fee) / fill
                cash = 0.0
                stop = min(planned_stop, fill*0.999)
                entry = {'time':bar[0], 'price':fill, 'equity':prior}
                signals.append({'decision_time':decision_time,'fill_time':bar[0],
                                'action':'BUY','reason':'trend_breakout_volume','stop':stop})
            elif action == 'SELL' and units:
                fill = bar[1] * (1-slippage)
                cash = units * fill * (1-fee)
                trades.append({'buy_time':entry['time'],'buy_price':entry['price'],
                               'sell_time':bar[0],'sell_price':fill,
                               'return_pct':(cash/entry['equity']-1)*100,'reason':'skill_exit'})
                signals.append({'decision_time':decision_time,'fill_time':bar[0],
                                'action':'SELL','reason':'trend_or_exhaustion','stop':None})
                units, entry, stop = 0.0, None, None
        pending = None
        # An armed stop executes during this candle. If opening below the stop,
        # use the worse opening price rather than the unattainable stop level.
        if units and bar[3] <= stop:
            fill = min(bar[1], stop) * (1-slippage)
            cash = units * fill * (1-fee)
            trades.append({'buy_time':entry['time'],'buy_price':entry['price'],
                           'sell_time':bar[0],'sell_price':fill,
                           'return_pct':(cash/entry['equity']-1)*100,'reason':'stop'})
            signals.append({'decision_time':bar[0],'fill_time':bar[0],
                            'action':'SELL','reason':'stop','stop':stop})
            units, entry, stop = 0.0, None, None
        equity.append(cash + units * bar[4])
        current = state_fn(rows[:i+1])
        buy, sell = _decision(current)
        if units and sell:
            pending = ('SELL',bar[0],None)
        elif not units and buy:
            support = current['market-s-r'].get('nearest_support')
            support = float(support) if isinstance(support,(int,float)) and 0 < support < bar[4] else 0
            planned_stop = max(support,bar[4]-2*_atr(rows[:i+1]))
            pending = ('BUY',bar[0],planned_stop)
    peak, drawdown = 1.0, 0.0
    for value in equity:
        peak=max(peak,value)
        drawdown=min(drawdown,value/peak-1)
    last = rows[-1]
    buy_now, sell_now = _decision(current)
    return {'strategy_kind':'technical_rule_experiment','role_backtest':False,
            'bars':len(rows), 'start':rows[0][0], 'end':last[0],
            'net_return_pct':(equity[-1]-1)*100,
            'max_drawdown_pct':drawdown*100,
            'buy_hold_pct':(last[4]/rows[first][4]-1)*100,
            'buy_hold_start':rows[first][0]+14400,
            'first_decision_bar':rows[first][0],
            'warmup_bars':first,
            'closed_trades':len(trades),
            'win_rate_pct':(sum(t['return_pct']>0 for t in trades)/len(trades)*100) if trades else None,
            'trades':trades, 'signals':signals, 'open_position':bool(units),
            'open_entry':entry, 'last_stop':stop,
            'last_close':last[4], 'current_state':current,
            'next_bar_signal':'SELL' if units and sell_now else 'BUY' if not units and buy_now else 'WAIT',
            'fee_per_side':fee,'slippage_per_side':slippage,'funding_included':False}
