# quant-terminal-web

Dashboard web de control del ecosistema quant. Expone una **API REST** estable (`/api/v1/...`) y una interfaz React para monitorizar bots, ver rendimiento, consultar el trail de auditoría y activar el **botón de pánico**. Duodécimo módulo del ecosistema [quant-core-infra](https://github.com/juanmmm21/quant-core-infra).

Repositorio: [github.com/juanmmm21/quant-terminal-web](https://github.com/juanmmm21/quant-terminal-web)

---

## Qué es y qué problema resuelve

Los módulos backend del ecosistema (backtester, métricas, auditoría, routing) producen datos valiosos, pero no son operables por un humano sin una capa de visualización y control.

`quant-terminal-web` cierra ese gap: es la **consola operativa** que lee datos del ecosistema **sin imports cruzados** entre repos (solo JSON, SQLite, Parquet y subprocess), y ofrece la misma API que consumirá `quant-terminal-ios`.

---

## Rol en quant-core-infra

```text
websocket-feed-handler ──► ticks JSONL ──┐
market-data-lakehouse ──► Parquet/DuckDB ─┼──► quant-terminal-web API
quant-metrics-calculator ──► metrics.json ─┤         │
trade-audit-logger ──► audit.db ──────────┤         ▼
event-driven-backtester ──► fills ────────┘    React dashboard
                                                          │
                                                          ▼
                                               quant-terminal-ios (misma API)
```

---

## Objetivo

Demuestra:

- API REST tipada con FastAPI y contratos Pydantic estables
- Lectura desacoplada de SQLite (`trade-audit-logger`), JSON (`quant-metrics-calculator`) y Parquet (`market-data-lakehouse`)
- **Precio BTC live** desde ticks WebSocket (puente compatible con `websocket-feed-handler`), no hardcodeado
- Estado de bot (`running` / `paused` / `panic`) con persistencia, reset y UX en español
- Frontend React + TypeScript + Vite: velas OHLCV, tabla de operaciones, métricas y auditoría
- Precisión financiera: balances y PnL como `string` en API (sin `float` en dinero)

---

## Cómo funciona

1. **Velas:** la API consulta `data/lake/` (salida de `market-data-lakehouse`) vía DuckDB.
2. **Último precio:** lee el último tick de `data/live/ticks.jsonl` (escrito por `scripts/tick_bridge.py`).
3. **Métricas / equity / trades:** leen JSON/JSONL de `samples/` o rutas `TERMINAL_*` configurables.
4. **Auditoría:** query directa a SQLite de `trade-audit-logger`.
5. **Frontend:** polling cada 10s, gráfico de velas, operaciones visibles y controles del bot.

Modos:

| Modo | Condición | UI |
|------|-----------|-----|
| `demo` | Sin Parquet en `data/lake/` | Banner con instrucciones de bootstrap |
| `live` | Lakehouse materializado | Precio y velas de mercado reales |

---

## Arquitectura

```text
quant-terminal-web/
├── backend/src/quant_terminal_api/
│   ├── readers/
│   │   ├── data.py        # audit, metrics, equity, trades
│   │   ├── lakehouse.py   # Parquet → DuckDB (market-data-lakehouse)
│   │   ├── live_ticks.py  # último tick JSONL
│   │   └── market.py      # combina lakehouse + live
│   ├── routes/            # health, bot, metrics, market, trades, audit
│   └── bot_state.py
├── frontend/src/
│   ├── components/        # CandlestickChart, TradesTable, TopBar, …
│   └── api/client.ts
├── scripts/
│   ├── bootstrap_market_data.py  # Binance klines → lakehouse ingest
│   └── tick_bridge.py              # WebSocket → ticks.jsonl
├── samples/               # demo: audit, metrics, equity, trades
├── data/                  # runtime: lake/ + live/ (gitignored)
└── package.json           # npm run dev desde la raíz
```

---

## Requisitos

- Python **3.11+** (`python3` y `pip3` en macOS; o venv con `source .venv/bin/activate`)
- Node.js **20+**
- [`market-data-lakehouse`](../market-data-lakehouse) instalado para materializar velas
- SQLite (stdlib)

---

## Instalación

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

(o `cd frontend && npm install`)

### Datos de auditoría demo

```bash
cd quant-terminal-web
python3 samples/build_audit_db.py
```

### Velas de mercado (lakehouse)

```bash
# Instalar lakehouse si no está en PATH
cd ../market-data-lakehouse && python3 -m pip install -e . && cd ../quant-terminal-web

# Materializa Parquet en data/lake/ (subprocess, sin imports cruzados)
python3 scripts/bootstrap_market_data.py
```

### Precio live (opcional)

```bash
source backend/.venv/bin/activate
python3 -m pip install websockets
python3 scripts/tick_bridge.py
```

---

## Uso

### API

```bash
cd backend
source .venv/bin/activate
quant-terminal-api --host 127.0.0.1 --port 8000
```

### UI (desde la raíz del proyecto)

```bash
cd quant-terminal-web
npm run dev
```

Abre [http://localhost:5173](http://localhost:5173). Vite proxifica `/api` al backend en `:8000`.

### Variables de entorno (`TERMINAL_*`)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `TERMINAL_LAKEHOUSE_ROOT` | `data/lake` | Raíz Parquet de `market-data-lakehouse` |
| `TERMINAL_LAKEHOUSE_DUCKDB` | `data/lake/catalog.duckdb` | Catálogo DuckDB |
| `TERMINAL_TICKS_JSONL_PATH` | `data/live/ticks.jsonl` | Último precio live |
| `TERMINAL_CANDLE_SYMBOL` | `BTCUSDT` | Símbolo de velas |
| `TERMINAL_CANDLE_TIMEFRAME` | `1h` | Timeframe (`1m`, `5m`, `1h`) |
| `TERMINAL_AUDIT_DB_PATH` | `samples/audit.db` | SQLite de `trade-audit-logger` |
| `TERMINAL_METRICS_PATH` | `samples/metrics.json` | Salida de `quant-metrics-calculator` |
| `TERMINAL_EQUITY_PATH` | `samples/equity.json` | Capital de cuenta (USDT, no precio BTC) |
| `TERMINAL_TRADES_PATH` | `samples/trades.jsonl` | Fills del backtester |
| `TERMINAL_BOT_STATE_PATH` | `samples/bot_state.json` | Estado del bot |

---

## API REST (`/api/v1`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Healthcheck + `data_mode` (`demo` \| `live`) |
| `GET` | `/summary` | Barra superior: precio, capital, trades, estado bot |
| `GET` | `/bot/status` | Estado (`running` \| `paused` \| `panic`) |
| `POST` | `/bot/panic` | Parada de emergencia |
| `POST` | `/bot/pause` | Pausa |
| `POST` | `/bot/resume` | Reanuda |
| `POST` | `/bot/reset` | Sale de pánico → `running` |
| `GET` | `/metrics` | Sharpe, Sortino, profit factor, drawdown |
| `GET` | `/equity-curve` | Capital de cuenta en USDT |
| `GET` | `/market/candles` | Velas OHLCV desde lakehouse |
| `GET` | `/trades` | Operaciones ejecutadas (fills) |
| `GET` | `/audit/events` | Eventos de auditoría |

### Capital vs precio BTC

- **`/market/candles`** y **`/summary.last_price`** → precio de mercado del activo (BTC/USDT).
- **`/equity-curve`** y **`/summary.account_capital`** → saldo de la cuenta en USDT del backtest, **no** el precio de BTC.

---

## Formatos de datos

### Ticks live (compatible con lakehouse / websocket-feed-handler)

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

### Equity (capital de cuenta)

```json
{
  "symbol": "BTCUSDT",
  "currency": "USDT",
  "label": "Capital total de la cuenta (no es el precio de BTC)",
  "initial_capital": "10000.00",
  "current_capital": "10330.00",
  "equity_curve": [{"event_time": "...", "equity": "10000.00"}]
}
```

---

## Desarrollo

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

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `zsh: command not found: pip` | macOS sin `pip` en PATH | Usa `python3 -m pip` o `source .venv/bin/activate` |
| `npm run dev` ENOENT en raíz | `package.json` solo en `frontend/` | Usa `npm run dev` desde raíz (hay delegación) o `cd frontend` |
| `503` en `/market/candles` | Lakehouse vacío | `python3 scripts/bootstrap_market_data.py` |
| Modo `demo` en UI | Sin `candles.parquet` en `data/lake/` | Ejecuta bootstrap del lakehouse |
| `409` al resume tras panic | Pánico es terminal hasta reset | Pulsa «Reiniciar bot» o `POST /bot/reset` |
| Precio no actualiza en live | `tick_bridge.py` no corre | Arranca `python3 scripts/tick_bridge.py` |

---

## Roadmap

- [x] Velas desde `market-data-lakehouse` (sin precio hardcodeado)
- [x] UX español + reset de pánico + tabla de operaciones
- [ ] WebSocket/SSE para auditoría en tiempo real
- [ ] Autenticación antes de exponer panic en producción
- [ ] Integración live con `order-routing-gateway` para halt real
- [ ] Docker Compose (API + UI + lakehouse volume)

---

## Licencia

MIT
