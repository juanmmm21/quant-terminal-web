# quant-terminal-web

Dashboard web de control del ecosistema quant. Expone una **API REST** estable (`/api/v1/...`) y una interfaz React para monitorizar bots, ver rendimiento, consultar el trail de auditoría y activar el **botón de pánico**. Duodécimo módulo del ecosistema [quant-core-infra](https://github.com/juanmmm21/quant-core-infra).

Repositorio: [github.com/juanmmm21/quant-terminal-web](https://github.com/juanmmm21/quant-terminal-web)

---

## Qué es y qué problema resuelve

Los módulos backend del ecosistema (backtester, métricas, auditoría, routing) producen datos valiosos, pero no son operables por un humano sin una capa de visualización y control.

`quant-terminal-web` cierra ese gap: es la **consola operativa** que lee datos del ecosistema sin imports cruzados entre repos, y ofrece la misma API que consumirá `quant-terminal-ios`.

---

## Rol en quant-core-infra

```text
quant-metrics-calculator ──► metrics.json / equity.json ──┐
trade-audit-logger ──► audit.db (SQLite) ─────────────────┤
order-routing-gateway / estrategia ──► bot state ─────────┼──► quant-terminal-web
                                                          │         │
                                                          │    React UI
                                                          ▼
                                               quant-terminal-ios (misma API)
```

Es la **interfaz de control** del pipeline cuantitativo.

---

## Objetivo

Demuestra:

- API REST tipada con FastAPI y contratos Pydantic estables
- Lectura desacoplada de SQLite (`trade-audit-logger`) y JSON (`quant-metrics-calculator`)
- Estado de bot (`running` / `paused` / `panic`) con persistencia local
- Frontend React + TypeScript + Vite sin lógica de trading en el cliente
- Precisión financiera: balances y PnL como `string` en API (sin `float` en dinero)

---

## Cómo funciona

1. **Backend** (`quant-terminal-api`) arranca un servidor FastAPI que expone endpoints bajo `/api/v1`.
2. **Readers** leen archivos configurables (`TERMINAL_AUDIT_DB_PATH`, `TERMINAL_METRICS_PATH`, `TERMINAL_EQUITY_PATH`).
3. **Bot state** se guarda en `bot_state.json` (por defecto en `samples/`) y responde a pause/resume/panic.
4. **Frontend** hace polling cada 10s y renderiza métricas, curva de equidad, feed de auditoría y controles.

En v1 los datos de muestra en `samples/` permiten ejecutar el dashboard sin cablear el ecosistema live.

---

## Arquitectura

```text
quant-terminal-web/
├── backend/
│   └── src/quant_terminal_api/
│       ├── models.py          # contratos Pydantic (API pública)
│       ├── config.py          # TerminalSettings (env TERMINAL_*)
│       ├── bot_state.py       # estado del bot (thread-safe + JSON)
│       ├── readers/           # SQLite audit + JSON metrics/equity
│       ├── routes/            # health, bot, metrics, audit
│       ├── app.py             # FastAPI factory
│       └── __main__.py        # CLI uvicorn
├── frontend/
│   └── src/
│       ├── api/client.ts      # cliente REST tipado
│       ├── components/        # UI dashboard
│       └── App.tsx
└── samples/                   # datos demo del ecosistema
```

### Componentes backend

| Módulo | Responsabilidad |
|--------|-----------------|
| `readers/data.py` | Query SQLite audit, parse metrics/equity JSON |
| `bot_state.py` | Transiciones running/paused/panic + persistencia |
| `routes/bot.py` | POST panic/pause/resume, GET status |
| `routes/metrics.py` | GET metrics, GET equity-curve |
| `routes/audit.py` | GET audit/events con filtros |

---

## Requisitos

- Python **3.11+**
- Node.js **20+** (para el frontend)
- SQLite (stdlib, para lectura de audit)

---

## Instalación

### Backend

```bash
cd quant-terminal-web/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Frontend

```bash
cd quant-terminal-web/frontend
npm install
```

### Datos de muestra

```bash
cd quant-terminal-web
python samples/build_audit_db.py
```

---

## Uso

### Arrancar API

```bash
cd backend
source .venv/bin/activate
quant-terminal-api --host 127.0.0.1 --port 8000
```

Variables de entorno opcionales:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `TERMINAL_AUDIT_DB_PATH` | `samples/audit.db` | SQLite de `trade-audit-logger` |
| `TERMINAL_METRICS_PATH` | `samples/metrics.json` | Salida de `quant-metrics-calculator` |
| `TERMINAL_EQUITY_PATH` | `samples/equity.json` | Curva de equidad JSON |
| `TERMINAL_BOT_STATE_PATH` | `samples/bot_state.json` | Estado persistido del bot |
| `TERMINAL_HOST` | `127.0.0.1` | Bind host |
| `TERMINAL_PORT` | `8000` | Bind port |

### Arrancar UI

```bash
cd frontend
npm run dev
```

Abre [http://localhost:5173](http://localhost:5173). Vite proxifica `/api` al backend en `:8000`.

---

## API REST (`/api/v1`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Healthcheck + versión |
| `GET` | `/bot/status` | Estado actual (`running` \| `paused` \| `panic`) |
| `POST` | `/bot/panic` | Parada de emergencia (`{"reason": "..."}`) |
| `POST` | `/bot/pause` | Pausa operativa |
| `POST` | `/bot/resume` | Reanuda operativa |
| `GET` | `/metrics` | Sharpe, Sortino, profit factor, drawdown |
| `GET` | `/equity-curve` | Serie `{event_time, equity}` |
| `GET` | `/audit/events` | Últimos N eventos (`?limit=50&event_type=&symbol=`) |

### Ejemplo: métricas

```bash
curl -s http://127.0.0.1:8000/api/v1/metrics | jq
```

```json
{
  "symbol": "BTCUSDT",
  "sharpe_ratio": "1.42",
  "sortino_ratio": "2.10",
  "profit_factor": "1.85",
  "max_drawdown_pct": "0.00594",
  "total_return_pct": "0.003",
  "win_rate": "0.5",
  "trade_count": 2,
  "computed_at": "2024-01-02T12:00:00.000Z"
}
```

### Ejemplo: pánico

```bash
curl -X POST http://127.0.0.1:8000/api/v1/bot/panic \
  -H 'Content-Type: application/json' \
  -d '{"reason": "operator halt"}'
```

---

## Formatos de datos (ecosistema)

### Métricas (`quant-metrics-calculator`)

Valores monetarios y ratios como **strings** para evitar pérdida de precisión.

### Equity curve

```json
{
  "symbol": "BTCUSDT",
  "equity_curve": [
    {"event_time": "2024-01-01T12:00:00.000Z", "equity": "10000.00"}
  ]
}
```

### Auditoría (`trade-audit-logger` SQLite)

La API consulta la tabla `audit_events` con el mismo esquema que el módulo de auditoría. No importa código Python entre repos.

---

## Uso programático

```python
from quant_terminal_api.app import create_app
from quant_terminal_api.config import TerminalSettings

settings = TerminalSettings(
    audit_db_path="samples/audit.db",
    metrics_path="samples/metrics.json",
    equity_path="samples/equity.json",
).resolve_paths()

app = create_app(settings)
# Despliega con uvicorn o TestClient para integración
```

---

## Desarrollo

### Backend

```bash
cd backend
pytest -q
ruff check src tests
mypy src
```

### Frontend

```bash
cd frontend
npm run build
```

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `503` en `/audit/events` | `audit.db` no existe | Ejecuta `python samples/build_audit_db.py` |
| UI sin datos | API no arrancada | Inicia `quant-terminal-api` en `:8000` |
| `409` al resume tras panic | Estado panic es terminal en v1 | Borra o edita `bot_state.json` manualmente |
| CORS bloqueado | Origen distinto a `:5173` | Añade origen en `TERMINAL_CORS_ORIGINS` (futuro) o usa proxy Vite |

---

## Roadmap

- [ ] WebSocket/SSE para feed de auditoría en tiempo real
- [ ] Autenticación (API key / OAuth) antes de exponer panic en producción
- [ ] Integración live con `order-routing-gateway` para halt real
- [ ] Tema claro y responsive mobile-first
- [ ] Docker Compose (API + UI + volumen audit)

---

## Licencia

MIT
