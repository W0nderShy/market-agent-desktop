# Foundation verification — 2026-09-09

## Verified locally

- Full upstream dsh Git checkout at `5dda764ed3aa172535a7967b06ff95d9cbfe536a` (not a shallow clone).
- Node 24.15.0, pnpm 11.19.0, Python 3.12.10 and Electron 44.0.0.
- Frozen upstream dependency installation, Host/Client compilation, Web assets and Electron Desktop build succeeded. Parent-directory React type interference was resolved using explicit local public-hoist patterns.
- Original Desktop window was observed by the user. Integrated market-home Desktop shell also built successfully; market routing/authorization and locale tests passed (6 cases).
- Backend tests passed (24 cases), including validation, retries, stale data, failure isolation, persisted checkpoint resume, duplicate prevention, runtime locking, API authentication/shutdown, candle validation and supported intervals.
- The same 24 backend tests passed after installing locked dependencies into a separate fresh Python virtual environment. `pip check` found no broken requirements.
- Desktop policy and chart-data tests passed (8 cases). Real Electron UI testing loaded 300 candles, exercised zoom/crosshair, found no console errors or horizontal overflow, and verified that a forced candle-request failure clears the chart and shows an error.
- Desktop patch application was tested on a separate unpatched file tree and repeated successfully to verify idempotence on Windows PowerShell 5.1.
- Public Bitget spot and perpetual market interfaces returned real ticker and candle data without credentials. All six supported chart intervals were verified. Actual watchlist and prices are deliberately excluded from this document.
- Start → authenticated shutdown → restart preserved the configured watchlist and returned fresh market data. Runtime files are excluded by Git ignore rules; tracked-file baseline privacy checks passed.

## Limits

2026-09-11 integrated Desktop recheck: the actual dsh window loaded `dsh-app://market/index.html`, exposed the restricted monitor bridge and displayed 300 real candles. The conversation action navigated to the original dsh app; returning to the market homepage restored the chart. Backend 24 tests and desktop 8 tests passed again. Screenshot retained only in ignored local runtime storage.

This is a Windows source-development foundation, not a packaged installer. The market homepage integration uses an explicitly configured development root; installer asset bundling remains future work. Model research, trigger scripts, continued thinking, dialogue agents, tray/autostart and automatic process supervision are not implemented. Upstream Desktop currently opens development inspector ports; this development mode is not a hardened release configuration. Do not expose the development machine or these ports to untrusted networks.

The repository includes CI configuration; local test results do not claim that hosted Actions have passed. Baseline privacy scanning is not a full historical secret audit. The original dsh tool/telemetry configuration still requires the privacy hardening described in DATA_PRIVACY.md before model-driven unattended research.
