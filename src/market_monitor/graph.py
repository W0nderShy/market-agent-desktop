from decimal import Decimal, InvalidOperation
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .bitget import MarketError

class State(TypedDict, total=False):
    item: dict
    observation: dict | None
    error: str | None

def build_graph(store, feed, saver, stale_seconds=180):
    def collect(state):
        item = state['item']
        try:
            ticker = feed.ticker(item['category'], item['symbol'])
            now = int(time.time()*1000)
            ts = int(ticker['ts'])
            if now - ts > stale_seconds * 1000: raise MarketError('stale_data')
            if ts > now + 30000: raise MarketError('future_timestamp')
            price, volume = Decimal(ticker['lastPrice']), Decimal(ticker['volume24h'])
            if not price.is_finite() or not volume.is_finite() or price <= 0 or volume < 0:
                raise MarketError('invalid_response')
            candles = feed.candles(item['category'],item['symbol'])
            return {'observation': {'price': str(price), 'volume_24h': str(volume), 'exchange_ts':ts, 'collected_ts':now, 'candles':candles}, 'error':None}
        except MarketError as exc:
            return {'observation':None,'error':str(exc)}
        except (ValueError, KeyError, TypeError, InvalidOperation):
            return {'observation':None,'error':'invalid_response'}
        except Exception:
            return {'observation':None,'error':'collection_error'}
    def persist(state):
        store.record(state['item'],state.get('observation'),state.get('error'))
        return {}
    graph = StateGraph(State)
    graph.add_node('collect',collect)
    graph.add_node('persist',persist)
    graph.add_edge(START,'collect')
    graph.add_edge('collect','persist')
    graph.add_edge('persist',END)
    return graph.compile(checkpointer=saver)
