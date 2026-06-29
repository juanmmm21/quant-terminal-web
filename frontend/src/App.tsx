import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api/client";
import { AuditFeed } from "./components/AuditFeed";
import { BotControls } from "./components/BotControls";
import { CandlestickChart } from "./components/CandlestickChart";
import { CapitalPanel } from "./components/CapitalPanel";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { LoadingPanel } from "./components/LoadingPanel";
import { MetricsGrid } from "./components/MetricsGrid";
import { ToastStack, type ToastMessage } from "./components/Toast";
import { TopBar } from "./components/TopBar";
import { TradesTable } from "./components/TradesTable";
import type {
  AuditEvent,
  BotStatus,
  CandlesData,
  EquityCurve,
  PerformanceMetrics,
  TerminalSummary,
  TradeFill,
} from "./types/api";

const REFRESH_MS = 10_000;
const TOAST_DURATION_MS = 5_000;

type PendingAction = "panic" | "reset" | null;

function translateError(message: string): string {
  const map: Record<string, string> = {
    "bot is already in panic state": "El bot ya está en modo pánico.",
    "cannot pause while bot is in panic state": "No se puede pausar mientras el bot está en pánico.",
    "cannot resume while bot is in panic state; manual reset required":
      "No se puede reanudar en modo pánico. Usa «Reiniciar bot».",
    "Failed to load dashboard data": "No se pudieron cargar los datos del terminal.",
    "Action failed": "La acción no se completó.",
  };
  return map[message] ?? message;
}

export default function App() {
  const [summary, setSummary] = useState<TerminalSummary | null>(null);
  const [botStatus, setBotStatus] = useState<BotStatus>("running");
  const [botUpdatedAt, setBotUpdatedAt] = useState<string | null>(null);
  const [botMessage, setBotMessage] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [equity, setEquity] = useState<EquityCurve | null>(null);
  const [candles, setCandles] = useState<CandlesData | null>(null);
  const [trades, setTrades] = useState<TradeFill[]>([]);
  const [closedRoundTrips, setClosedRoundTrips] = useState(0);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiVersion, setApiVersion] = useState<string>("");
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);

  const pushToast = useCallback((text: string, tone: ToastMessage["tone"] = "info") => {
    const id = crypto.randomUUID();
    setToasts((current) => [...current, { id, text, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, TOAST_DURATION_MS);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) {
      setRefreshing(true);
    }
    try {
      const [
        health,
        summaryData,
        status,
        metricsData,
        equityData,
        candlesData,
        tradesData,
        auditData,
      ] = await Promise.all([
        api.health(),
        api.summary(),
        api.botStatus(),
        api.metrics(),
        api.equityCurve(),
        api.candles(),
        api.trades(),
        api.auditEvents(20),
      ]);
      setApiVersion(health.version);
      setSummary(summaryData);
      setBotStatus(status.status);
      setBotUpdatedAt(status.updated_at);
      setBotMessage(status.message);
      setMetrics(metricsData);
      setEquity(equityData);
      setCandles(candlesData);
      setTrades(tradesData.trades);
      setClosedRoundTrips(tradesData.closed_round_trips);
      setEvents(auditData.events);
      setError(null);
    } catch (err) {
      const raw = err instanceof ApiError ? err.message : "Failed to load dashboard data";
      setError(translateError(raw));
    } finally {
      setInitialLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void refresh(true);
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const runAction = async (
    action: () => Promise<{ message: string }>,
    successText: string,
  ) => {
    setActionLoading(true);
    setError(null);
    try {
      const result = await action();
      pushToast(result.message || successText, "success");
      await refresh(true);
    } catch (err) {
      const raw = err instanceof ApiError ? err.message : "Action failed";
      const message = translateError(raw);
      setError(message);
      pushToast(message, "error");
    } finally {
      setActionLoading(false);
      setPendingAction(null);
    }
  };

  if (initialLoading) {
    return (
      <div className="app-shell">
        <LoadingPanel />
      </div>
    );
  }

  return (
    <div className="app-shell">
      {summary ? (
        <TopBar
          summary={summary}
          apiVersion={apiVersion}
          refreshing={refreshing || actionLoading}
          onRefresh={() => void refresh()}
        />
      ) : null}

      <div className={summary?.data_mode === "live" ? "info-banner" : "demo-banner"} role="note">
        {summary?.data_mode === "live" ? (
          <>
            <strong>Datos live:</strong> velas desde <code>market-data-lakehouse</code> (Parquet/DuckDB)
            y último precio desde <code>data/live/ticks.jsonl</code> (puente WebSocket). El capital de
            cuenta sigue viniendo de métricas/backtest, no del precio de BTC.
          </>
        ) : (
          <>
            <strong>Modo demo:</strong> ejecuta{" "}
            <code>python scripts/bootstrap_market_data.py</code> para materializar velas reales en el
            lakehouse y <code>python scripts/tick_bridge.py</code> para precio live.
          </>
        )}
      </div>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />

      {error ? (
        <div className="error-banner" role="alert">
          <strong>Error:</strong> {error}
        </div>
      ) : null}

      <main className="terminal-layout">
        <aside className="sidebar">
          <BotControls
            status={botStatus}
            updatedAt={botUpdatedAt}
            statusMessage={botMessage}
            loading={actionLoading}
            onPause={() => void runAction(() => api.pauseBot(), "Bot pausado")}
            onResume={() => void runAction(() => api.resumeBot(), "Bot reanudado")}
            onPanic={() => setPendingAction("panic")}
            onReset={() => setPendingAction("reset")}
          />
          {metrics ? <MetricsGrid metrics={metrics} /> : null}
          {equity ? <CapitalPanel equity={equity} /> : null}
        </aside>

        <section className="main-column">
          {candles ? (
            <CandlestickChart
              symbol={candles.symbol}
              interval={candles.interval}
              currency={candles.currency}
              lastPrice={candles.last_price}
              changePct={candles.change_pct}
              candles={candles.candles}
            />
          ) : null}
          <TradesTable trades={trades} closedRoundTrips={closedRoundTrips} />
        </section>

        <aside className="audit-column">
          <AuditFeed events={events} />
        </aside>
      </main>

      <ConfirmDialog
        open={pendingAction === "panic"}
        title="¿Activar parada de emergencia?"
        message="Se detendrán todas las operaciones del bot. Tendrás que reiniciarlo manualmente cuando sea seguro continuar."
        confirmLabel="Sí, detener todo"
        cancelLabel="Cancelar"
        danger
        onConfirm={() =>
          void runAction(
            () => api.panicBot("parada de emergencia desde el terminal web"),
            "Parada de emergencia activada",
          )
        }
        onCancel={() => setPendingAction(null)}
      />

      <ConfirmDialog
        open={pendingAction === "reset"}
        title="¿Reiniciar el bot?"
        message="El estado volverá a «En marcha». Confirma solo si ya revisaste la causa del pánico."
        confirmLabel="Sí, reiniciar"
        cancelLabel="Cancelar"
        onConfirm={() => void runAction(() => api.resetBot(), "Bot reiniciado correctamente")}
        onCancel={() => setPendingAction(null)}
      />
    </div>
  );
}
