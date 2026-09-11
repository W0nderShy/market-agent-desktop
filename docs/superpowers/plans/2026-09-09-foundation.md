# Desktop market foundation implementation plan

User authorized implementation of steps 1–4 on 2026-09-09.

**Goal:** Independently versioned Desktop project with public Bitget watchlist data and a persistent LangGraph monitoring service.

**Architecture:** Keep full upstream dsh as a pinned submodule with a reproducible Desktop integration patch. A Python service owns data collection, durable event jobs and LangGraph checkpoints. User clarified that monitoring must be the dsh main page with a broker-style watchlist, candlestick chart and details; original dsh conversation remains reachable via navigation. No model execution in this milestone.

**Stack:** Python 3.12, SQLite, LangGraph, HTTPX, Node 24, Electron / upstream dsh.

## Tasks

- [ ] Initialize independent Git repository and pin existing full dsh checkout; create a private GitHub remote if authenticated creation is available. Do not change parent repository history.
- [ ] Install frozen upstream dependencies, build original Desktop and verify Electron startup. Record any upstream/platform blocker precisely.
- [ ] Add Python project: validated watchlist config, Bitget v3 public client, SQLite event queue, durable LangGraph collection graph, localhost API, CLI and tests. Verify bad symbols, stale data, restart recovery, duplicates and failure isolation with synthetic fixtures before live smoke.
- [ ] Provide desktop watchlist window with actual market state, freshness, errors and configuration; keep runtime data local. Validate that this is a desktop window rather than an external-browser-only interface.
- [ ] Add setup/start scripts, blank private config template, README, CI and pinned Python dependencies. Test fresh setup path and restart against real public BTCUSDT SPOT data explicitly designated as smoke input.
- [ ] Review tracked files for secrets/runtime data, commit only reviewed deliverables and push private remote if available.

## File boundaries

`src/market_monitor/`: config.py, bitget.py, store.py, graph.py, service.py, api.py, cli.py. `tests/`: deterministic backend regression tests. `desktop/`: local Electron monitor. `scripts/`: PowerShell bootstrap/launch. `config/watchlist.example.json`: empty watchlist. `runtime/`: all private generated state. `vendor/deepseek-harness`: upstream code owned by desktop-build task.

## Acceptance commands

`python -m pytest -q` must pass; `python -m market_monitor.cli --help` exposes configuration/once/serve/status commands. Live test stores a verified ticker with exchange and collection timestamps. Stop and restart service, verify persistent events/checkpoints and no duplicate observations. Desktop launch must yield a live Electron process and rendered monitor data, or a clearly documented specific blocker. No model key required at this milestone; no trading endpoints invoked.

## Scope limit

Rest scripts, continued reasoning, dialogue agent, production tray behavior and installer packaging belong to subsequent milestones. This milestone establishes their stateful foundation without presenting them as implemented.
