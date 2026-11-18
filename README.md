# quant-terminal-web

**Real-time quantitative analysis tool** for the quant ecosystem. Trains on historical data, emits **recommendations** (buy / sell / hold) on the live price, and shows an interactive chart with multiple timeframes.

Repository: [github.com/juanmmm21/quant-terminal-web](https://github.com/juanmmm21/quant-terminal-web)

## One-command startup

```bash
cd quant-terminal-web
python3 scripts/start_terminal.py
```

This automatically spins up:

1. **Historical bootstrap** from Binance (see [Market history](#market-history))
2. Market daemon: live ticks → lakehouse → periodic re-analysis
3. FastAPI API at `http://127.0.0.1:8000/api/v1/health`
4. React UI at **http://localhost:5173** (don't use port 8000 for the UI)

Also: `npm start` (alias for the script above).

**Requirements:** Node.js 20+ and Python 3.11+. The script creates `backend/.venv` on first run and installs dependencies there (it does not use the system `pip`).

**Port 8000 in use:** if there's already an API running, the script reuses it. If the port is taken by another process, try `:8001` or free the port with `lsof -i :8000`.

---

## Market history

The analysis engine trains on **all candles available** in `data/lake/`. Those candles come from Binance (bootstrap) and are extended live with WebSocket ticks.

### Does it download on its own?

**Yes**, when running `npm start` or `python3 scripts/start_terminal.py`, **with no manual steps**, when:

- No lakehouse exists (`data/lake/` without `candles.parquet`), **or**
- There are **fewer than 2000 1h candles** (insufficient history to train well).

By default it downloads:

| Interval | Default range | Approx. candles |
|-----------|---------------------|--------------|
| `1h` | **730 days** (~2 years) | ~17,520 |
| `1m` | **90 days** | ~129,600 |

The download is **paginated** (several requests to the public Binance API). The first run can take **1–3 minutes**.

After bootstrap, the **market daemon** ingests new ticks every ~10 s and **re-analyzes** the full history plus the live data. The UI refreshes candles and the recommendation every **3 s**.

### Manual or forced download

If you already have an old lakehouse with few candles (e.g. ~360) but startup doesn't re-download:

```bash
cd quant-terminal-web

# Force a full re-download when starting the stack
npm start -- --refresh-history

# Or just bootstrap (without starting the API/UI)
python3 scripts/bootstrap_market_data.py --days-1h 730 --days-1m 90
```

`start_terminal.py` options:

| Flag | Default | Description |
|------|---------|-------------|
| `--refresh-history` | off | Re-download even if a lakehouse already exists |
| `--history-days-1h` | `730` | Days of hourly candles |
| `--history-days-1m` | `90` | Days of 1-minute candles (`0` = skip) |
| `--skip-bootstrap` | off | Don't download history on startup |

`bootstrap_market_data.py` options:

```bash
python3 scripts/bootstrap_market_data.py --days-1h 730 --days-1m 90
python3 scripts/bootstrap_market_data.py --days-1h 365 --days-1m 0   # 1h only
```

Environment variable for the analysis engine's limit (`0` = use **all** candles in the lakehouse):

```bash
export TERMINAL_ANALYSIS_CANDLE_LIMIT=0   # default: no cap
```

---

## What it does (without simulating an account)

| Layer | Module | Function |
|------|--------|---------|
| History | `market-data-lakehouse` | OHLCV candles in Parquet |
| Indicators | `ta-indicators-from-scratch` | RSI, MACD, moving averages |
| Signals | `alpha-signal-generator` | Trained entry/exit |
| Live | `tick_bridge` + lakehouse | Updated price and candles |
| UI | `quant-terminal-web` | Recommendation + TradingView-like chart |

The terminal shows recommendations, indicators, historical signals and training metrics. Paper
trading on the Binance **testnet** is a separate, gated process (see
[24/7 paper trading](#247-paper-trading-on-the-binance-testnet)).

---

## Out-of-sample validation and the paper-trading gate

No strategy reaches paper trading on the strength of a single in-sample backtest. Every time the
analysis engine picks a strategy for a timeframe, `scripts/strategy_validation.py` (cached for
`TERMINAL_VALIDATION_MAX_AGE_HOURS`, default 6 h) runs, through the components' CLIs:

1. `event-driven-backtester validate` — **purged k-fold** (5 folds, 1 % embargo) and
   **walk-forward** (rolling window, 5 test windows). Each fold picks the candidate with the best
   Sharpe on its training bars and scores it on unseen bars. Bars whose information overlaps the
   test block (the p90 holding period) are purged.
2. `quant-metrics-calculator overfit` — **deflated Sharpe ratio** with `n_trials` = every
   (strategy, timeframe) pair the engine scores (2 × 5 = 10) and **PBO** via CSCV (16 blocks,
   12,870 combinations).

Candles are stamped at their open but signals use the close, so for validation both the price
and the signal are moved to the bar close: a signal is filled at the close it was computed from.
Strategies that never trade are excluded (a flat line would "win" against losing candidates).

The report (`data/runtime/validation_{tf}.json`, `GET /api/v1/validation?timeframe=1h`) is shown
in the **Validación fuera de muestra** panel. `POST /api/v1/paper/promote` requires the control
token **and** the `report_id` the operator was shown (409 if the report changed). Gate checks:

| Check | Default | Variable |
|-------|---------|----------|
| Deflated Sharpe ≥ | 0.95 | `TERMINAL_GATE_MIN_DEFLATED_SHARPE` |
| PBO ≤ | 0.5 | `TERMINAL_GATE_MAX_PBO` |
| Walk-forward and purged k-fold OOS Sharpe > | 0 | `TERMINAL_GATE_MIN_OOS_SHARPE` |
| Report age ≤ (h) | 24 | `TERMINAL_GATE_MAX_REPORT_AGE_HOURS` |

`TERMINAL_PAPER_GATE_MODE=enforce` (default) refuses a failing strategy with 412;
`acknowledge` lets it through but flags it `gate_passed: false` everywhere, including the
public view.

### Measured in this session (2026-11-17)

Binance BTCUSDT spot klines from `data-api.binance.vision`; 0.1 % commission per side, 0.01 BTC
per trade on 10,000 USDT; fills at the bar close; Linux x86_64 container (4 vCPU Intel Xeon).
These are **backtest** figures on history, not live or paper results.

| Timeframe | Period | Bars | Selected | Sharpe (ann.) | PSR | DSR | PBO | WF OOS Sharpe | CV OOS Sharpe |
|-----------|--------|------|----------|---------------|-----|-----|-----|---------------|---------------|
| 1h | 2024-11-18 → 2026-11-18 | 17,519 | rsi_mean_reversion | −0.78 | 0.134 | 0.0001 | 0.013 | −1.40 | −0.78 |
| 5m | 2026-08-19 → 2026-11-17 | 25,921 | rsi_mean_reversion | −7.21 | 0.0002 | 0.0000 | 0.000 | −10.37 | −7.21 |
| 1m (also 10m/15m) | 2026-08-19 → 2026-11-17 | 129,600 | rsi_mean_reversion | −40.5 | 0.0000 | 0.0000 | 0.000 | −40.96 | −40.52 |

Neither strategy passes: the gate blocks promotion in `enforce` mode. PBO is low only because
with two candidates the less-bad one (RSI) wins both in and out of sample; the out-of-sample
Sharpe is what fails. 10m/15m are analysed on 1m candles by the engine, so they repeat 1m.

---

## 24/7 paper trading on the Binance testnet

**Only test funds.** `quant-paper-trader` routes through `order-routing-gateway --mode testnet`;
real-money routing is locked inside the gateway and nothing in this repository unlocks it.

### What runs (`docker compose`)

| Service | Role | Restart / health |
|---------|------|------------------|
| `bootstrap` | downloads history once (`--if-missing`) | one-shot |
| `feed` | `websocket-feed-handler` → `data/live/ticks.jsonl` (rotated at 100 MB) + `feed_status.json` (stale detection: 15 s silence or 5 s exchange lag) | `unless-stopped`; unhealthy if the status file is old or stale |
| `daemon` | live ticks → lakehouse → analysis + out-of-sample validation | `unless-stopped` |
| `api` | FastAPI, **bound to 127.0.0.1:8000** (operator only: SSH tunnel or VPN) | `unless-stopped`; `/health` |
| `paper-trader` | one step every 10 s (below) | `unless-stopped`; unhealthy if `heartbeat.json` is older than 2 min |
| `alerts` | `quant-alerts`: pushes critical/warning alerts to the iOS app through APNs (`TERMINAL_APNS_*`) | `unless-stopped` |
| `comparison` | `scripts/paper_vs_backtest.py` every 15 min → `data/paper/comparison.json` | loop |
| `public` | nginx: `/public` page and `GET /api/v1/public/*` only, port 8080 | `unless-stopped` |

Every Python service uses the same image; state lives in the `quant-data` volume, so restarts and
upgrades keep the journal, the lakehouse and the promotion.

### What the trader does every step

1. **Emergency stop** (`POST /api/v1/bot/panic`, authenticated): cancel every open order at the
   venue; if the exchange is unreachable, keep retrying every step and never send a new order.
   The stop itself is a file write in the API, so it works with the exchange down.
2. **Reconcile** orders whose outcome is unknown (timeout, disconnect, process crash between
   sending and recording): the intent is written to `data/paper/state.json` *before* it is sent,
   and afterwards the trader asks the exchange by `clientOrderId` — a fill is booked exactly
   once, an order the exchange never saw is forgotten. Nothing new is sent meanwhile.
3. **Hold** when paused, when no strategy is promoted (the out-of-sample gate), or when market
   data is stale (feed status, status-file age or last-tick age).
4. **Target** from the promoted strategy's latest recommendation (`buy` → long
   `TERMINAL_PAPER_QUANTITY`, `sell` → flat); then hard caps and `risk-management-engine check`
   (fails closed if the engine is unavailable).

`backend/tests/test_chaos.py` drives these paths with a simulated exchange: disconnection at
submit, reply lost after the exchange accepted the order, process crash mid-order, an order still
working, stale data, and the emergency stop with the exchange down (plus the authenticated API
call that triggers it).

### iOS app (quant-terminal-ios)

Each phone gets its **own token**: `POST /api/v1/devices` with the operator token returns a
`qtd_…` token once; only its SHA-256 is stored (`data/runtime/devices.json`, mode 600) and it can
be revoked alone. A device token can read `/mobile/overview`, pull the emergency stop and register
its APNs token; it cannot resume the bot, promote strategies or manage devices (403). Push alerts
are signed with your APNs `.p8` key (ES256 JWT, refreshed every 50 min); the key file is mounted
read-only and never goes in `.env`. See the quant-terminal-ios README for signing and setup.

### Deploy

```bash
git clone https://github.com/juanmmm21/quant-terminal-web && cd quant-terminal-web
cp .env.example .env
# fill TERMINAL_ADMIN_TOKEN and BINANCE_TESTNET_API_KEY / _SECRET (testnet.binance.vision)
docker compose up -d --build
docker compose ps                       # all services healthy after ~1-3 min (bootstrap first)
ssh -L 8000:127.0.0.1:8000 your-server  # operator UI/API from your machine
```

Then, from the operator terminal (token in the control field): review the **Validación fuera de
muestra** panel and promote a strategy. With the default `TERMINAL_PAPER_GATE_MODE=enforce` a
strategy that fails the gate cannot be promoted (none of the current ones passes, see the
measured table above); `acknowledge` lets you paper-trade it anyway, flagged as such in public.

Public page: `http://<server>:8080/public` (put TLS in front of it if you publish it). Binance
answers HTTP 451 from restricted locations, testnet included; deploy from an eligible location.

| Variable | Default | |
|----------|---------|-|
| `TERMINAL_PAPER_VENUE` | `testnet` | `simulated` = fills at the live market price, no exchange (dry run) |
| `TERMINAL_PAPER_QUANTITY` | `0.001` | BTC per position |
| `TERMINAL_PAPER_MAX_POSITION` / `_MAX_ORDER_NOTIONAL` | `0.01` / `1000` | hard caps |
| `TERMINAL_PAPER_INTERVAL_SECONDS` | `10` | step period |
| `TERMINAL_PROJECT_ROOT` | repository root | set to `/app` in the image |

---

## Tick-to-decision latency (Rust accelerators)

`scripts/latency_bench.py` replays recorded Binance depth diffs as raw messages through three
paths that end in the same decision (top-5 imbalance and microprice, computed with `Decimal`),
checks that **every message gets the same decision on every path**, and reports per-message
latency after a 1,000-message warm-up:

| Path | p50 | p90 | p99 | p99.9 | max |
|------|-----|-----|-----|-------|-----|
| v0.1: `json.loads` → Decimal parser → `DepthSynchronizer` → view | 131 µs | 714 µs | 3.70 ms | 7.34 ms | 18.3 ms |
| fast API, Python fallback | 86 µs | 409 µs | 2.05 ms | 4.00 ms | 7.8 ms |
| fast API, Rust (`websocket-feed-handler-rs` + `order-book-reconstructor-rs`) | **15.5 µs** | 48 µs | **166 µs** | 321 µs | 0.69 ms |

Data and machine: 25,589 BTCUSDT depth diffs (100 ms stream, ~32 levels each) recorded from
`data-stream.binance.vision` on 2026-11-17 23:19–00:01 UTC; 4-vCPU Linux x86_64 container,
Python 3.12.3, release builds. Histograms:

```text
baseline (v0.1)            fast API, Rust
  <50µs   2875 ######       <10µs    882 ##
 <100µs   5726 ###########  <20µs  15824 ########################################
 <200µs   7076 ##############  <50µs   5582 ##############
 <500µs   5696 ###########   <100µs   1520 ####
<1000µs   1854 ####          <200µs    652 ##
<2000µs   1026 ##            <500µs    124 #
<5000µs    739 #            <1000µs      5 #
 >=5 ms     97 #
```

```bash
python3 scripts/latency_bench.py --recording stream.jsonl snapshots.jsonl
```

---

## Interactive chart

- **lightweight-charts** library (zoom, pan, scroll wheel, pinch)
- Timeframes: `1m`, `5m`, `10m`, `15m`, `1h` (`10m`/`15m` aggregated from `1m`)
- Up to **10,000 candles** per timeframe; live update every 3 s (last candle without redrawing everything)
- Historical signal markers on the chart
- Full screen and "Fit zoom"

---

## Main API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/market/candles?timeframe=1h` | Candles + last live price |
| `GET /api/v1/analysis/snapshot?timeframe=1h` | Recommendation, indicators, training |
| `GET /api/v1/summary` | Summary for the top bar |
| `POST /api/v1/bot/pause` | Pauses the analysis engine |

---

## Requirements

- Python 3.11+, Node 20+
- Ecosystem CLIs on PATH or the monorepo's `.venv` (`market-data-lakehouse`, `ta-indicators-from-scratch`, `alpha-signal-generator`)

See the installation and development sections further down in this README for backend/frontend details.

## Role in quant-core-infra

```text
JSONL ticks ──► market-data-lakehouse ──► ta-indicators ──► alpha-signal-generator
      │                                              │
      │                                              ▼
      │                                    risk-management-engine
      │                                              │
      │                                              ▼
      └──────────────────────────────► order-routing-gateway (paper)
                                                     │
                     quant-metrics-calculator ◄──────┤
                     trade-audit-logger ◄────────────┘
                              │
                              ▼
                     data/ecosystem/ ──► quant-terminal-web API ──► React
```

---

## Purpose

Demonstrates:

- Typed REST API with FastAPI and stable Pydantic contracts
- **Real ecosystem pipeline** via subprocess (7 modules) → `data/ecosystem/`
- Decoupled reading of SQLite, JSON, Parquet, and JSONL (no cross imports)
- **Live BTC price** from `data/live/ticks.jsonl` (WebSocket bridge)
- Paper trading with `order-routing-gateway`; panic/pause via `paper_bot_runner.py`
- React + TypeScript + Vite frontend with resilient per-panel loading

---

## How it works (main flow)

1. **`start_terminal.py`** / `npm start`: historical bootstrap (if needed), API, UI, and `market_daemon.py`.
2. **`market_daemon.py`**: WebSocket bridge → `data/live/ticks.jsonl` → incremental ingestion into the lakehouse → `analysis_engine.py` across all timeframes.
3. **`analysis_engine.py`**: exports candles from the lakehouse, computes indicators (`ta-indicators-from-scratch`), generates signals (`alpha-signal-generator`), picks the best strategy, and writes `data/runtime/analysis_{timeframe}.json`.
4. **API**: reads the lakehouse (candles), runtime (analysis), and live ticks (last price). Audit log in `data/runtime/audit.db` (empty until real events occur).
5. **Frontend**: polling every 3 s; chart and recommendation update with new data.

`data_mode` in `/api/v1/health`:

| Mode | Condition |
|------|-----------|
| `live` | Lakehouse with candles + runtime analysis |
| `demo` | No lakehouse (limited fallback) |

### Ecosystem pipeline (optional / legacy)

Scripts like `run_ecosystem_pipeline.py` and `paper_bot_runner.py` remain in the repo for integration with paper trading and account metrics, but they are **not part of the main recommendation flow**. See the [Ecosystem pipeline](#ecosystem-pipeline-optional--legacy) section below.

---

## Architecture

```text
quant-terminal-web/
├── backend/src/quant_terminal_api/
│   ├── readers/
│   │   ├── data.py        # audit, metrics, equity, trades
│   │   ├── lakehouse.py   # Parquet → DuckDB (market-data-lakehouse)
│   │   ├── live_ticks.py  # last JSONL tick
│   │   └── market.py      # combines lakehouse + live
│   ├── routes/            # health, bot, metrics, market, trades, audit, ecosystem
│   └── bot_state.py
├── frontend/src/
│   ├── components/        # CandlestickChart, TradesTable, TopBar, …
│   └── api/client.ts
├── scripts/
│   ├── start_terminal.py             # single startup: bootstrap + daemon + API + UI
│   ├── bootstrap_market_data.py      # paginated Binance klines → lakehouse
│   ├── market_daemon.py            # live ticks → lakehouse → analysis
│   ├── analysis_engine.py          # indicators + signals → data/runtime/
│   ├── tick_bridge.py                # WebSocket → ticks.jsonl
│   ├── run_ecosystem_pipeline.py     # (optional) paper pipeline → data/ecosystem/
│   └── ecosystem_tools.py            # subprocess / JSON utilities
├── samples/               # static demo data (tests; not the main flow)
├── data/                  # runtime: lake/, live/, runtime/ (gitignored)
└── package.json           # npm start → start_terminal.py
```

---

## Requirements

- Python **3.11+** (`python3` and `pip3` on macOS; or a venv with `source .venv/bin/activate`)
- Node.js **20+**
- [`market-data-lakehouse`](../market-data-lakehouse) and, for the full pipeline, the CLIs of:
  `ta-indicators-from-scratch`, `alpha-signal-generator`, `risk-management-engine`,
  `order-routing-gateway`, `quant-metrics-calculator`, `trade-audit-logger`
- SQLite (stdlib)

---

## Installation

### Backend

```bash
cd quant-terminal-web/backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

### Frontend

```bash
cd quant-terminal-web
npm run install:frontend
```

(or `cd frontend && npm install`)

### Demo audit data

```bash
cd quant-terminal-web
python3 samples/build_audit_db.py
```

### Market candles (lakehouse)

You normally **don't need** to run this by hand: `npm start` downloads the history if it's missing or insufficient (see [Market history](#market-history)).

```bash
# Install the lakehouse if not on PATH
cd ../market-data-lakehouse && python3 -m pip install -e . && cd ../quant-terminal-web

# Manual: 2 years at 1h + 90 days at 1m (paginated from Binance)
python3 scripts/bootstrap_market_data.py --days-1h 730 --days-1m 90
```

### Ecosystem pipeline (optional / legacy)

Requires the neighboring modules' CLIs installed on PATH or in their `.venv` (the script resolves them automatically).

```bash
cd quant-terminal-web

# 1. Candles in the lakehouse (if they don't exist yet)
python3 scripts/bootstrap_market_data.py

# 2. Live ticks (optional, improves paper fills)
python3 -m pip install websockets
python3 scripts/tick_bridge.py &

# 3. Full pipeline → data/ecosystem/
python3 scripts/run_ecosystem_pipeline.py

# 4. Paper bot that re-syncs as ticks arrive (optional)
python3 scripts/paper_bot_runner.py &
```

Shortcut: `chmod +x scripts/start_stack.sh && ./scripts/start_stack.sh`

After the pipeline, restart the API: `data_mode` will switch to `ecosystem`.

### Live price (optional)

```bash
source backend/.venv/bin/activate
python3 -m pip install websockets
python3 scripts/tick_bridge.py
```

---

## Usage

### API

```bash
cd backend
source .venv/bin/activate
quant-terminal-api --host 127.0.0.1 --port 8000
```

### UI (from the project root)

```bash
cd quant-terminal-web
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to the backend on `:8000`.

### Environment variables (`TERMINAL_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `TERMINAL_LAKEHOUSE_ROOT` | `data/lake` | `market-data-lakehouse` Parquet root |
| `TERMINAL_LAKEHOUSE_DUCKDB` | `data/lake/catalog.duckdb` | DuckDB catalog |
| `TERMINAL_TICKS_JSONL_PATH` | `data/live/ticks.jsonl` | Last live price |
| `TERMINAL_RUNTIME_DIR` | `data/runtime` | Analysis JSON + `audit.db` |
| `TERMINAL_CANDLE_SYMBOL` | `BTCUSDT` | Candle symbol |
| `TERMINAL_CANDLE_LIMIT` | `50000` | Max candles served by the API |
| `TERMINAL_ANALYSIS_CANDLE_LIMIT` | `0` (env) | Bars to train on (`0` = all) |
| `TERMINAL_AUDIT_DB_PATH` | `data/runtime/audit.db` | Audit SQLite (live session) |
| `TERMINAL_BOT_STATE_PATH` | `data/runtime/bot_state.json` | Engine state (pause/panic) |
| `TERMINAL_ADMIN_TOKEN` | — (control disabled) | Operator bearer token; environment only, never commit it |
| `TERMINAL_BINANCE_REST_URL` | `https://data-api.binance.vision` | Public market-data REST base used by the bootstrap |
| `TERMINAL_VALIDATION` | `1` | `0` skips out-of-sample validation in the analysis engine |

---

## REST API (`/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Healthcheck + `data_mode` (`demo` \| `live`) |
| `GET` | `/summary` | Top bar: price, capital, trades, bot state |
| `GET` | `/bot/status` | State (`running` \| `paused` \| `panic`) |
| `POST` | `/bot/panic` | Emergency stop 🔒 |
| `POST` | `/bot/pause` | Pause 🔒 |
| `POST` | `/bot/resume` | Resume 🔒 |
| `POST` | `/bot/reset` | Exit panic → `running` 🔒 |
| `GET` | `/validation?timeframe=1h` | DSR, PBO, walk-forward and purged k-fold report + gate |
| `GET` | `/paper/promotion` | Strategy currently in paper trading |
| `POST` | `/paper/promote` | Promote the validated strategy (`timeframe`, `report_id`) 🔒 |
| `POST` | `/paper/demote` | Stop paper trading it 🔒 |

| `POST` | `/devices` | Create a device token for the iOS app (shown once) 🔒 operator |
| `GET` | `/devices` | List devices (no secrets) 🔒 operator |
| `DELETE` | `/devices/{device_id}` | Revoke a device 🔒 operator |
| `PUT` | `/devices/me/push-token` | Register the APNs token of the calling device 🔒 device |
| `GET` | `/mobile/overview` | Bot status, paper trader, strategy, P&L and alerts for the app 🔒 |
| `GET` | `/public/paper` | Read-only paper vs backtest comparison (public) |

🔒 = `Authorization: Bearer <token>`: `TERMINAL_ADMIN_TOKEN` (operator) or a device token. With
no `TERMINAL_ADMIN_TOKEN` in the environment these endpoints answer 503 (control disabled). The
web UI asks for the token once per tab and keeps it in `sessionStorage` only.
| `GET` | `/metrics` | Sharpe, Sortino, profit factor, drawdown |
| `GET` | `/equity-curve` | Account capital in USDT |
| `GET` | `/market/candles` | OHLCV candles from the lakehouse |
| `GET` | `/trades` | Executed trades (fills) |
| `GET` | `/audit/events` | Audit events |

### Capital vs. BTC price

- **`/market/candles`** and **`/summary.last_price`** → market price of the asset (BTC/USDT).
- **`/equity-curve`** and **`/summary.account_capital`** → backtest account balance in USDT, **not** the BTC price.

---

## Data formats

### Live ticks (compatible with lakehouse / websocket-feed-handler)

```json
{
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "trade_id": "123",
  "price": "60152.00",
  "quantity": "0.01",
  "side": "buy",
  "event_time": "2026-06-29T10:00:00.000Z"
}
```

### Equity (account capital)

```json
{
  "symbol": "BTCUSDT",
  "currency": "USDT",
  "label": "Total account capital (not the BTC price)",
  "initial_capital": "10000.00",
  "current_capital": "10330.00",
  "equity_curve": [{"event_time": "...", "equity": "10000.00"}]
}
```

---

## Development

```bash
cd backend
source .venv/bin/activate
pytest -q
ruff check src tests
mypy src
```

```bash
cd frontend
npm run build
```

---

## Troubleshooting

| Symptom | Likely cause | Solution |
|---------|----------------|----------|
| `zsh: command not found: pip` | macOS without `pip` on PATH | Use `python3 -m pip` or `source .venv/bin/activate` |
| Few candles analyzed (~360) | Old lakehouse / short bootstrap | `npm start -- --refresh-history` or `bootstrap_market_data.py --days-1h 730` |
| Bootstrap doesn't start on its own | A lakehouse already exists but with little history | Same: `--refresh-history` (threshold: fewer than 2000 1h candles) |
| `503` on `/market/candles` | Empty lakehouse | `python3 scripts/bootstrap_market_data.py` |
| Blank page at `:5173` | API down or wrong port | Open **localhost:5173**; check `:8000/api/v1/health` |
| Chart doesn't update | Daemon stopped | Start with `npm start` (includes `market_daemon`) |
| `409` on resume after panic | Panic is terminal until reset | Click "Reset" or `POST /bot/reset` |

---

## Roadmap

- [x] Candles from `market-data-lakehouse` (no hardcoded price)
- [x] Spanish UX + panic reset + trades table
- [ ] WebSocket/SSE for real-time audit
- [ ] Authentication before exposing panic in production
- [ ] Live integration with `order-routing-gateway` for a real halt
- [ ] Docker Compose (API + UI + lakehouse volume)

---

## License

MIT
