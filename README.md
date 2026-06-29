# quant-terminal-web

**Herramienta de análisis cuantitativo en tiempo real** del ecosistema quant. Entrena sobre histórico, emite **recomendaciones** (comprar / vender / mantener) sobre el precio live y muestra un gráfico interactivo con múltiples marcos temporales.

Repositorio: [github.com/juanmmm21/quant-terminal-web](https://github.com/juanmmm21/quant-terminal-web)

## Arranque con un solo comando

```bash
cd quant-terminal-web
python3 scripts/start_terminal.py
```

Esto levanta automáticamente:

1. **Bootstrap histórico** desde Binance (ver sección [Histórico de mercado](#histórico-de-mercado))
2. Daemon de mercado: ticks live → lakehouse → re-análisis periódico
3. API FastAPI en `http://127.0.0.1:8000/api/v1/health`
4. UI React en **http://localhost:5173** (no uses el puerto 8000 para la interfaz)

También: `npm start` (alias al script anterior).

**Requisitos:** Node.js 20+ y Python 3.11+. El script crea `backend/.venv` en el primer arranque e instala dependencias ahí (no usa `pip` del sistema).

**Puerto 8000 ocupado:** si ya hay una API en marcha, el script la reutiliza. Si el puerto está ocupado por otro proceso, prueba `:8001` o libera el puerto con `lsof -i :8000`.

---

## Histórico de mercado

El motor de análisis entrena sobre **todas las velas disponibles** en `data/lake/`. Esas velas vienen de Binance (bootstrap) y se amplían en vivo con los ticks del WebSocket.

### ¿Se descarga solo?

**Sí**, al ejecutar `npm start` o `python3 scripts/start_terminal.py`, **sin pasos manuales**, cuando:

- No existe lakehouse (`data/lake/` sin `candles.parquet`), **o**
- Hay **menos de 2000 velas de 1h** (histórico insuficiente para entrenar bien).

Por defecto descarga:

| Intervalo | Alcance por defecto | Velas aprox. |
|-----------|---------------------|--------------|
| `1h` | **730 días** (~2 años) | ~17 520 |
| `1m` | **90 días** | ~129 600 |

La descarga es **paginada** (varias peticiones a la API pública de Binance). La primera vez puede tardar **1–3 minutos**.

Tras el bootstrap, el **market daemon** ingesta ticks nuevos cada ~10 s y **re-analiza** el histórico completo más los datos live. La UI refresca velas y recomendación cada **3 s**.

### Descarga manual o forzada

Si ya tienes un lakehouse antiguo con pocas velas (p. ej. ~360) pero el arranque no vuelve a descargar:

```bash
cd quant-terminal-web

# Forzar re-descarga completa al arrancar el stack
npm start -- --refresh-history

# O solo bootstrap (sin levantar API/UI)
python3 scripts/bootstrap_market_data.py --days-1h 730 --days-1m 90
```

Opciones de `start_terminal.py`:

| Flag | Default | Descripción |
|------|---------|-------------|
| `--refresh-history` | off | Re-descarga aunque ya exista lakehouse |
| `--history-days-1h` | `730` | Días de velas horarias |
| `--history-days-1m` | `90` | Días de velas de 1 minuto (`0` = omitir) |
| `--skip-bootstrap` | off | No descarga histórico al arrancar |

Opciones de `bootstrap_market_data.py`:

```bash
python3 scripts/bootstrap_market_data.py --days-1h 730 --days-1m 90
python3 scripts/bootstrap_market_data.py --days-1h 365 --days-1m 0   # solo 1h
```

Variable de entorno para el límite del motor de análisis ( `0` = usar **todas** las velas del lakehouse):

```bash
export TERMINAL_ANALYSIS_CANDLE_LIMIT=0   # default: sin tope
```

---

## Qué hace (sin simular cuenta)

| Capa | Módulo | Función |
|------|--------|---------|
| Histórico | `market-data-lakehouse` | Velas OHLCV en Parquet |
| Indicadores | `ta-indicators-from-scratch` | RSI, MACD, medias |
| Señales | `alpha-signal-generator` | Entrada/salida entrenada |
| Live | `tick_bridge` + lakehouse | Precio y velas actualizadas |
| UI | `quant-terminal-web` | Recomendación + gráfico TradingView-like |

**No hay simulación de capital ni paper trading en el flujo principal.** La UI muestra recomendaciones, indicadores, señales históricas y métricas de entrenamiento (acierto direccional sobre histórico).

---

## Gráfico interactivo

- Librería **lightweight-charts** (zoom, pan, rueda, pinch)
- Marcos: `1m`, `5m`, `10m`, `15m`, `1h` (`10m`/`15m` agregados desde `1m`)
- Hasta **10 000 velas** por marco; actualización live cada 3 s (última vela sin redibujar todo)
- Marcadores de señales históricas en el gráfico
- Pantalla completa y «Ajustar zoom»

---

## API principal

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/v1/market/candles?timeframe=1h` | Velas + último precio live |
| `GET /api/v1/analysis/snapshot?timeframe=1h` | Recomendación, indicadores, entrenamiento |
| `GET /api/v1/summary` | Resumen para la barra superior |
| `POST /api/v1/bot/pause` | Pausa el motor de análisis |

---

## Requisitos

- Python 3.11+, Node 20+
- CLIs del ecosistema en PATH o `.venv` del monorepo (`market-data-lakehouse`, `ta-indicators-from-scratch`, `alpha-signal-generator`)

Ver secciones de instalación y desarrollo más abajo en este README para detalle de backend/frontend.

## Rol en quant-core-infra

```text
ticks JSONL ──► market-data-lakehouse ──► ta-indicators ──► alpha-signal-generator
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

## Objetivo

Demuestra:

- API REST tipada con FastAPI y contratos Pydantic estables
- **Pipeline real del ecosistema** vía subprocess (7 módulos) → `data/ecosystem/`
- Lectura desacoplada de SQLite, JSON, Parquet y JSONL (sin imports cruzados)
- **Precio BTC live** desde `data/live/ticks.jsonl` (puente WebSocket)
- Paper trading con `order-routing-gateway`; pánico/pausa vía `paper_bot_runner.py`
- Frontend React + TypeScript + Vite con carga resiliente por panel

---

## Cómo funciona (flujo principal)

1. **`start_terminal.py`** / `npm start`: bootstrap histórico (si hace falta), API, UI y `market_daemon.py`.
2. **`market_daemon.py`**: puente WebSocket → `data/live/ticks.jsonl` → ingesta incremental al lakehouse → `analysis_engine.py` en todos los marcos temporales.
3. **`analysis_engine.py`**: exporta velas del lakehouse, calcula indicadores (`ta-indicators-from-scratch`), genera señales (`alpha-signal-generator`), elige la mejor estrategia y escribe `data/runtime/analysis_{timeframe}.json`.
4. **API**: lee lakehouse (velas), runtime (análisis) y ticks live (último precio). Auditoría en `data/runtime/audit.db` (vacía hasta eventos reales).
5. **Frontend**: polling cada 3 s; gráfico y recomendación se actualizan con datos nuevos.

Modo `data_mode` en `/api/v1/health`:

| Modo | Condición |
|------|-----------|
| `live` | Lakehouse con velas + análisis en runtime |
| `demo` | Sin lakehouse (fallback limitado) |

### Pipeline ecosistema (opcional / legacy)

Scripts como `run_ecosystem_pipeline.py` y `paper_bot_runner.py` siguen en el repo para integración con paper trading y métricas de cuenta, pero **no forman parte del flujo principal** de recomendaciones. Ver sección [Pipeline ecosistema](#pipeline-ecosistema-opcional--legacy) más abajo.

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
│   ├── routes/            # health, bot, metrics, market, trades, audit, ecosystem
│   └── bot_state.py
├── frontend/src/
│   ├── components/        # CandlestickChart, TradesTable, TopBar, …
│   └── api/client.ts
├── scripts/
│   ├── start_terminal.py             # arranque único: bootstrap + daemon + API + UI
│   ├── bootstrap_market_data.py      # Binance klines paginados → lakehouse
│   ├── market_daemon.py            # ticks live → lakehouse → análisis
│   ├── analysis_engine.py          # indicadores + señales → data/runtime/
│   ├── tick_bridge.py                # WebSocket → ticks.jsonl
│   ├── run_ecosystem_pipeline.py     # (opcional) pipeline paper → data/ecosystem/
│   └── ecosystem_tools.py            # utilidades subprocess / JSON
├── samples/               # datos demo estáticos (tests; no flujo principal)
├── data/                  # runtime: lake/, live/, runtime/ (gitignored)
└── package.json           # npm start → start_terminal.py
```

---

## Requisitos

- Python **3.11+** (`python3` y `pip3` en macOS; o venv con `source .venv/bin/activate`)
- Node.js **20+**
- [`market-data-lakehouse`](../market-data-lakehouse) y, para el pipeline completo, los CLIs de:
  `ta-indicators-from-scratch`, `alpha-signal-generator`, `risk-management-engine`,
  `order-routing-gateway`, `quant-metrics-calculator`, `trade-audit-logger`
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

Normalmente **no hace falta** ejecutar esto a mano: `npm start` descarga el histórico si falta o es insuficiente (ver [Histórico de mercado](#histórico-de-mercado)).

```bash
# Instalar lakehouse si no está en PATH
cd ../market-data-lakehouse && python3 -m pip install -e . && cd ../quant-terminal-web

# Manual: 2 años en 1h + 90 días en 1m (paginado desde Binance)
python3 scripts/bootstrap_market_data.py --days-1h 730 --days-1m 90
```

### Pipeline ecosistema (opcional / legacy)

Requiere los CLIs de los módulos vecinos instalados en PATH o en su `.venv` (el script los resuelve automáticamente).

```bash
cd quant-terminal-web

# 1. Velas en lakehouse (si aún no existen)
python3 scripts/bootstrap_market_data.py

# 2. Ticks live (opcional, mejora fills paper)
python3 -m pip install websockets
python3 scripts/tick_bridge.py &

# 3. Pipeline completo → data/ecosystem/
python3 scripts/run_ecosystem_pipeline.py

# 4. Bot paper que re-sincroniza al llegar ticks (opcional)
python3 scripts/paper_bot_runner.py &
```

Atajo: `chmod +x scripts/start_stack.sh && ./scripts/start_stack.sh`

Tras el pipeline, reinicia la API: `data_mode` pasará a `ecosystem`.

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
| `TERMINAL_RUNTIME_DIR` | `data/runtime` | Análisis JSON + `audit.db` |
| `TERMINAL_CANDLE_SYMBOL` | `BTCUSDT` | Símbolo de velas |
| `TERMINAL_CANDLE_LIMIT` | `50000` | Máx. velas servidas por la API |
| `TERMINAL_ANALYSIS_CANDLE_LIMIT` | `0` (env) | Barras para entrenar (`0` = todas) |
| `TERMINAL_AUDIT_DB_PATH` | `data/runtime/audit.db` | SQLite de auditoría (sesión live) |
| `TERMINAL_BOT_STATE_PATH` | `data/runtime/bot_state.json` | Estado del motor (pause/panic) |

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
| Pocas velas analizadas (~360) | Lakehouse antiguo / bootstrap corto | `npm start -- --refresh-history` o `bootstrap_market_data.py --days-1h 730` |
| Bootstrap no arranca solo | Ya hay lakehouse pero con poco histórico | Mismo: `--refresh-history` (umbral: menos de 2000 velas 1h) |
| `503` en `/market/candles` | Lakehouse vacío | `python3 scripts/bootstrap_market_data.py` |
| Página en blanco en `:5173` | API caída o puerto equivocado | Abre **localhost:5173**; comprueba `:8000/api/v1/health` |
| Gráfico no se actualiza | Daemon parado | Arranca con `npm start` (incluye `market_daemon`) |
| `409` al resume tras panic | Pánico es terminal hasta reset | Pulsa «Reiniciar» o `POST /bot/reset` |

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
