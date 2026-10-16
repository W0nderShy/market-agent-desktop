import math

from market_monitor.probabilities import estimate_outcome_distribution


def candles(closes, step=900):
    return [[i * step, close, close, close, close, 10 + i % 7]
            for i, close in enumerate(closes, start=1)]


def test_three_way_distribution_sums_to_exactly_100_and_uses_only_matured_outcomes():
    closes = [100 * math.exp(0.005 * math.sin(i / 9) + 0.001 * i)
              for i in range(300)]
    result = estimate_outcome_distribution(candles(closes), '15m')
    assert result['horizon_bars'] == 16
    assert result['observation_bars'] > 100
    assert result['latest_training_anchor'] <= result['as_of'] - 16 * 900
    assert sum(result['percentages'].values()) == 100.0
    assert all(0 <= value <= 100 for value in result['percentages'].values())


def test_distribution_reacts_to_a_new_closed_bar_without_model_round():
    closes = [100 * math.exp(0.012 * math.sin(i / 8) + 0.0005 * i)
              for i in range(300)]
    before = estimate_outcome_distribution(candles(closes), '15m')
    after = estimate_outcome_distribution(candles(closes + [closes[-1] * 1.12]), '15m')
    assert before['as_of'] < after['as_of']
    assert before['percentages'] != after['percentages']


def test_short_or_gapped_history_does_not_publish_percentages():
    rows = candles([100 + math.sin(i / 5) for i in range(300)])
    assert estimate_outcome_distribution(rows[:100], '15m') is None
    rows[160][0] += 1
    assert estimate_outcome_distribution(rows, '15m') is None
