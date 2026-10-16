# Vendored financial analysis subset

Upstream: https://github.com/krzysu/market-skills
Pinned commit: 1af8e68377efb18dd18af0c22360f991f307f031 (MIT).

Only the five requested analyzers, four internal indicator dependencies, and pure math/loader helpers are included. No execution adapters, alternative market-data providers, upstream run scripts or trading strategies are installed. Original source files are unmodified; hashes are recorded in UPSTREAM.json. Project adapter: scripts/run_market_skill.py. dsh entry points: .agents/skills/market-*/SKILL.md.

Adaptation: use only the active Bitget chart, reject stale/malformed/discontinuous candles, exclude unclosed bars, require adequate history. Upstream volatility assumes 252 daily samples: the adapter suppresses those annualized magnitudes and exposes only relative regimes and a 30-bar percentile. Upstream composite labels remain heuristics; a missing volume confirmation receives an explicit warning. Rounded indicator prices are not order prices.
