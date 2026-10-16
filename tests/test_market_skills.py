import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('market_skill_runner',Path(__file__).parents[1]/'scripts/run_market_skill.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
def snapshot():
    return {'symbol':'ZECUSDT','category':'USDT-FUTURES','interval':'1m','capturedAt':18000000,'candles':[[i*60,100+i*.1,101+i*.1,99+i*.1,100.5+i*.1,100+i] for i in range(1,301)]}
def test_closed_bars_and_bitget_identity():
    result=runner.analyze_snapshot(snapshot(),now_ms=18000000)
    assert result['source']=='Bitget'
    assert result['input_bars']==300 and result['analyzed_bars']==299
    assert set(result['results'])==set(runner.SKILLS)
    assert result['results']['market-volume']['volume_ratio']>0
@pytest.mark.parametrize('change',[{'available':False},{'capturedAt':1},{'interval':'invalid'},{'candles':[]}])
def test_invalid_or_stale_snapshot_refused(change):
    value=snapshot();value.update(change)
    with pytest.raises(ValueError):runner.analyze_snapshot(value,now_ms=18000000)
def test_corrupt_ohlcv_refused():
    value=snapshot();value['candles'][1][2]=0
    with pytest.raises(ValueError):runner.analyze_snapshot(value,now_ms=18000000)
