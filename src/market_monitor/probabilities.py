"""Exploratory, outcome-based BUY/SELL/HOLD shares from closed Bitget candles.

The three labels describe the *next window's return*, not realized trading P&L.
Only historical anchors whose entire forward window has closed enter the estimate.
"""
import math


HORIZON_BARS = {'1m': 60, '5m': 24, '15m': 16, '1H': 8, '4H': 6, '1D': 5}
STEP_SECONDS = {'1m': 60, '5m': 300, '15m': 900, '1H': 3600,
                '4H': 14400, '1D': 86400}
LABELS = ('buy', 'sell', 'hold')


def _features(rows, index):
    closes = [row[4] for row in rows[index - 20:index + 1]]
    returns = [math.log(closes[j] / closes[j - 1]) for j in range(1, len(closes))]
    average = sum(returns) / len(returns)
    volatility = math.sqrt(sum((item - average) ** 2 for item in returns) / len(returns))
    volatility = max(volatility, 0.0001)
    trend = math.log(closes[-1] / closes[-9]) / (volatility * math.sqrt(8))
    recent_volume = sum(row[5] for row in rows[index - 3:index + 1]) / 4
    baseline_volume = sum(row[5] for row in rows[index - 19:index + 1]) / 20
    volume_ratio = recent_volume / baseline_volume if baseline_volume else 1
    return max(-5, min(5, trend)), math.log(max(volume_ratio, 0.01)), volatility


def _percentages(weighted_counts):
    total = sum(weighted_counts.values())
    raw = {key: weighted_counts[key] / total * 1000 for key in LABELS}
    units = {key: math.floor(raw[key]) for key in LABELS}
    remainder = 1000 - sum(units.values())
    for key in sorted(LABELS, key=lambda item: raw[item] - units[item], reverse=True)[:remainder]:
        units[key] += 1
    return {key: units[key] / 10 for key in LABELS}


def estimate_outcome_distribution(rows, interval):
    """Return three percentages totaling 100, or None when evidence is too thin.

    Similarity weights compare current trend, relative volume and volatility with
    past states. Historical labels are mutually exclusive forward-return buckets.
    Overlapping windows are disclosed with an effective non-overlapping block count.
    """
    horizon = HORIZON_BARS.get(interval)
    step = STEP_SECONDS.get(interval)
    if horizon is None or len(rows) < 200:
        return None
    if any(rows[i][0] - rows[i - 1][0] != step for i in range(1, len(rows))):
        return None
    if any(len(row) < 6 or row[4] <= 0 or row[5] < 0 for row in rows):
        return None
    first = 40
    last = len(rows) - horizon - 1
    count = last - first + 1
    blocks = count // horizon
    if blocks < 10:
        return None
    current = _features(rows, len(rows) - 1)
    counts = {key: 1.0 for key in LABELS}  # one observation per class limits false certainty
    for index in range(first, last + 1):
        trend, volume, volatility = _features(rows, index)
        distance = (abs(current[0] - trend)
                    + 0.5 * abs(current[1] - volume)
                    + 0.5 * abs(math.log(current[2] / volatility)))
        weight = (0.5 + 0.5 * (index - first + 1) / count) / (1 + distance)
        future_return = math.log(rows[index + horizon][4] / rows[index][4])
        band = max(0.002, 0.5 * volatility * math.sqrt(horizon))
        label = 'buy' if future_return > band else 'sell' if future_return < -band else 'hold'
        counts[label] += weight
    return {
        'percentages': _percentages(counts),
        'interval': interval,
        'horizon_bars': horizon,
        'horizon_seconds': horizon * step,
        'observation_bars': count,
        'effective_blocks': blocks,
        'as_of': rows[-1][0] + step,
        'latest_training_anchor': rows[last][0] + step,
        'method': 'historical_analog_v1',
        'meaning': 'forward_return_buckets_not_strategy_pnl',
    }
