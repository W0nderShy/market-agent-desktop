from market_monitor.research_sources import ExternalEvidence, parse_fred


def test_fred_parser_uses_latest_valid_observations():
    csv='observation_date,DGS10\n2026-09-21,4.10\n2026-09-22,.\n2026-09-23,4.05\n'
    result=parse_fred(csv,'DGS10')
    assert result['value']==4.05
    assert result['previous']==4.10
    assert result['as_of']=='2026-09-23'


def test_fred_parser_rejects_empty_or_non_numeric_series():
    import pytest
    with pytest.raises(ValueError):parse_fred('observation_date,DGS10\n2026-09-23,.\n','DGS10')


def test_external_evidence_keeps_missing_series_and_cross_asset_proxies():
    class Response:
        def __init__(self,text):self.text=text
        def raise_for_status(self):pass
    class Client:
        def get(self,url,**kwargs):
            if kwargs['params']['id']=='DGS10':return Response('observation_date,DGS10\n2026-09-22,4.10\n2026-09-23,4.05\n')
            raise OSError('unavailable')
    class Feed:
        def candles(self,category,symbol,interval='1D',limit=60):
            if symbol=='XAUUSDT':raise OSError('not listed')
            end=1800000000//86400*86400+57600
            return [[str((end-i*86400)*1000),'100','102','99',str(100+i/1000),'10'] for i in reversed(range(limit))]
    source=ExternalEvidence(Feed(),client=Client(),clock=lambda:1800000000+86401)
    data=source.snapshot()
    assert data['macro']['DGS10']['value']==4.05
    assert data['macro']['DGS2']['status']=='unavailable'
    assert data['cross_asset']['BTCUSDT']['instrument']=='Bitget USDT perpetual proxy'
    assert data['cross_asset']['XAUUSDT']['status']=='unavailable'
