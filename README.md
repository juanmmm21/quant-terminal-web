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

**There is no capital simulation or paper trading in the main flow.** The UI shows recommendations, indicators, historical signals, and training metrics (directional accuracy on history).

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

---

## REST API (`/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Healthcheck + `data_mode` (`demo` \| `live`) |
| `GET` | `/summary` | Top bar: price, capital, trades, bot state |
| `GET` | `/bot/status` | State (`running` \| `paused` \| `panic`) |
| `POST` | `/bot/panic` | Emergency stop |
| `POST` | `/bot/pause` | Pause |
| `POST` | `/bot/resume` | Resume |
| `POST` | `/bot/reset` | Exit panic → `running` |
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
