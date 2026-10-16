"""Read-only, provenance-bearing evidence outside the selected Bitget chart."""
import csv
import io
import math
import time
from datetime import datetime, timezone

import httpx


FRED_SERIES = {
    'FEDFUNDS':'effective policy rate (monthly average)',
    'DGS2':'US Treasury 2Y yield',
    'DGS10':'US Treasury 10Y yield',
    'DFII10':'US TIPS 10Y real yield',
    'T10Y2Y':'US 10Y minus 2Y yield',
    'VIXCLS':'VIX close',
    'BAMLH0A0HYM2':'US high-yield option-adjusted spread',
    'NFCI':'Chicago Fed financial conditions index',
    'WALCL':'Federal Reserve total assets',
    'M2SL':'US M2 money stock',
}


def parse_fred(body,series):
    rows=[]
    for row in csv.DictReader(io.StringIO(body)):
        try:
            date=datetime.strptime(row['observation_date'],'%Y-%m-%d').date().isoformat()
            value=float(row[series])
            if math.isfinite(value):rows.append((date,value))
        except (KeyError,TypeError,ValueError):continue
    if not rows:raise ValueError('no_observations')
    latest=rows[-1]
    return {'value':latest[1],'previous':rows[-2][1] if len(rows)>1 else None,
            'as_of':latest[0],'status':'available'}


class ExternalEvidence:
    def __init__(self,feed,client=None,clock=time.time):
        self.feed=feed
        self.client=client or httpx.Client(timeout=12,follow_redirects=False)
        self.clock=clock
        self._cached_at=0
        self._cached=None

    def snapshot(self):
        now=int(self.clock())
        if self._cached is not None and now-self._cached_at<21600:return self._cached
        start=datetime.fromtimestamp(now-90*86400,timezone.utc).strftime('%Y-%m-%d')
        macro={}
        for series,label in FRED_SERIES.items():
            entry={'name':label,'source':'FRED / Federal Reserve Bank of St. Louis',
                   'url':f'https://fred.stlouisfed.org/series/{series}'}
            try:
                response=self.client.get('https://fred.stlouisfed.org/graph/fredgraph.csv',
                                         params={'id':series,'cosd':start})
                response.raise_for_status()
                entry.update(parse_fred(response.text,series))
                age=(datetime.fromtimestamp(now,timezone.utc).date()-datetime.fromisoformat(entry['as_of']).date()).days
                max_age=60 if series in ('FEDFUNDS','M2SL') else 14 if series in ('NFCI','WALCL') else 7
                if age<0 or age>max_age:entry['status']='stale'
            except Exception:
                entry['status']='unavailable'
            macro[series]=entry
        cross={}
        for symbol,label in (('BTCUSDT','Bitcoin'),('XAUUSDT','gold-linked Bitget contract')):
            entry={'name':label,'instrument':'Bitget USDT perpetual proxy',
                   'source':'Bitget public market API',
                   'url':f'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol={symbol}&interval=1D&limit=60'}
            try:
                raw=self.feed.candles('USDT-FUTURES',symbol,interval='1D',limit=60)
                rows=[]
                for item in raw:
                    stamp=int(item[0])//1000
                    o,h,l,c=map(float,item[1:5])
                    if (stamp%86400 not in (0,57600) or not all(math.isfinite(x) for x in (o,h,l,c))
                            or min(o,h,l,c)<=0 or h<max(o,l,c) or l>min(o,h,c)):
                        raise ValueError('invalid_candle')
                    if stamp+86400<=now:rows.append((stamp,c))
                rows.sort()
                if len(rows)<21 or now-(rows[-1][0]+86400)>3*86400:raise ValueError('stale')
                entry.update(status='available',as_of=rows[-1][0]+86400,close=rows[-1][1],
                             change_20d_pct=round((rows[-1][1]/rows[-21][1]-1)*100,3))
            except Exception:
                entry['status']='unavailable'
            cross[symbol]=entry
        self._cached={'captured_at':now,'macro':macro,'cross_asset':cross,
                      'limitations':['宏观序列发布频率各异，as_of 是观察日期，不等于实时值。',
                                     'XAUUSDT 是 Bitget 合约代理，不能等同现货黄金或其他交易所报价。',
                                     '美联储降息预期、MOVE、期权与企业基本面目前没有可核查输入。']}
        self._cached_at=now
        return self._cached

    def close(self):
        self.client.close()
