import pytest

from market_monitor.backtest import replay, fetch_closed


def bars():
    return [[1_700_000_000 + i*14400, 100.0, 101.0, 99.0, 100.0, 1000.0]
            for i in range(260)]


def state(closed):
    signal = len(closed) == 201
    return {
        'market-trend': {'signal':'STRONG_UPTREND'},
        'market-volume': {'volume_ratio':2.0},
        'market-s-r': {'nearest_support':95.0},
        'market-breakout': {'pattern':{'present':signal,'direction':'bull',
                                       'classification':'FRESH' if signal else None},
                            'signals':{'volume_confirmation':{'present':signal}}},
        'market-exhaustion': {'pattern':{'present':False}},
    }


def test_signal_uses_closed_bar_and_fills_next_open():
    rows=bars()
    rows[201][1]=110.0
    rows[201][2]=111.0
    rows[201][3]=95.0
    result=replay(rows,state_fn=state)
    buy=result['signals'][0]
    assert buy['action']=='BUY'
    assert buy['decision_time']==rows[200][0]
    assert buy['fill_time']==rows[201][0]
    assert result['trades'][0]['reason']=='stop'
    assert result['trades'][0]['sell_time']==rows[201][0]


def test_gap_through_stop_fills_worse_open():
    rows=bars()
    rows[201][3]=100.0  # Entry bar does not hit stop.
    rows[202][1]=90.0
    rows[202][3]=89.0
    result=replay(rows,state_fn=state)
    stopped=result['trades'][0]
    assert stopped['sell_time']==rows[202][0]
    assert stopped['sell_price']==pytest.approx(90*(1-0.0002))


def test_rejects_missing_candles():
    rows=bars()
    rows[210][0]+=1
    with pytest.raises(ValueError,match='invalid_replay_history'):
        replay(rows,state_fn=state)


def test_trade_from_does_not_use_signals_before_requested_window():
    rows=bars()
    result=replay(rows,state_fn=state,trade_from=rows[220][0])
    assert result['first_decision_bar']==rows[220][0]
    assert result['warmup_bars']==220
    assert result['signals']==[]
