import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api/client";
import { AuditFeed } from "./components/AuditFeed";
import { BotControls } from "./components/BotControls";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { LoadingPanel } from "./components/LoadingPanel";
import { RecommendationPanel } from "./components/RecommendationPanel";
import { SignalHistory } from "./components/SignalHistory";
import { ToastStack, type ToastMessage } from "./components/Toast";
import { TopBar } from "./components/TopBar";
import { TIMEFRAMES, TradingChart } from "./components/TradingChart";
import type {
  AnalysisSnapshot,
  AuditEvent,
  BotStatus,
  CandlesData,
  TerminalSummary,
  Timeframe,
} from "./types/api";

const REFRESH_MS = 8_000;
const TOAST_DURATION_MS = 5_000;

type PendingAction = "panic" | "reset" | null;

function translateError(message: string): string {
  const map: Record<string, string> = {
    "bot is already in panic state": "El análisis ya está detenido por pánico.",
    "cannot pause while bot is in panic state": "No se puede pausar: ya está en pánico.",
    "cannot resume while bot is in panic state; manual reset required":
      "Reinicia el análisis tras revisar la causa del pánico.",
    "Failed to load dashboard data": "No se pudieron cargar los datos del terminal.",
    "Action failed": "La acción no se completó.",
  };
  return map[message] ?? message;
}

export default function App() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [summary, setSummary] = useState<TerminalSummary | null>(null);
  const [botStatus, setBotStatus] = useState<BotStatus>("running");
  const [botUpdatedAt, setBotUpdatedAt] = useState<string | null>(null);
  const [botMessage, setBotMessage] = useState<string | null>(null);
  const [candles, setCandles] = useState<CandlesData | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisSnapshot | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiVersion, setApiVersion] = useState<string>("");
  const [dataMode, setDataMode] = useState<string>("demo");
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

  const refresh = useCallback(
    async (silent = false, tf: Timeframe = timeframe) => {
      if (!silent) {
        setRefreshing(true);
      }
      const errors: string[] = [];
      try {
        const results = await Promise.allSettled([
          api.health(),
          api.summary(),
          api.botStatus(),
          api.candles(tf),
          api.analysisSnapshot(tf),
          api.auditEvents(20),
        ]);

        const [healthResult, summaryResult, statusResult, candlesResult, analysisResult, auditResult] =
          results;

        if (healthResult.status === "fulfilled") {
          setApiVersion(healthResult.value.version);
          setDataMode(healthResult.value.data_mode);
        }

        if (summaryResult.status === "fulfilled") {
          setSummary(summaryResult.value);
        } else {
          errors.push("resumen");
        }

        if (statusResult.status === "fulfilled") {
          setBotStatus(statusResult.value.status);
          setBotUpdatedAt(statusResult.value.updated_at);
          setBotMessage(statusResult.value.message);
        }

        if (candlesResult.status === "fulfilled") {
          setCandles(candlesResult.value);
        } else {
          errors.push("velas");
        }

        if (analysisResult.status === "fulfilled") {
          setAnalysis(analysisResult.value);
        } else {
          errors.push("análisis");
        }

        if (auditResult.status === "fulfilled") {
          setEvents(auditResult.value.events);
        }

        if (errors.length > 0) {
          setError(
            errors.includes("análisis")
              ? `Motor de análisis iniciando… (${errors.join(", ")})`
              : `No se cargaron: ${errors.join(", ")}`,
          );
        } else {
          setError(null);
        }
      } catch (err) {
        const raw = err instanceof ApiError ? err.message : "Failed to load dashboard data";
        setError(translateError(raw));
      } finally {
        setInitialLoading(false);
        setRefreshing(false);
        setChartLoading(false);
      }
    },
    [timeframe],
  );

  const changeTimeframe = (tf: Timeframe) => {
    if (!TIMEFRAMES.includes(tf)) {
      return;
    }
    setChartLoading(true);
    setTimeframe(tf);
    void refresh(true, tf);
  };

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

      <div className={dataMode === "live" ? "info-banner" : "demo-banner"} role="note">
        {dataMode === "live" ? (
          <>
            <strong>Herramienta live:</strong> precios en tiempo real, velas del lakehouse y
            recomendaciones entrenadas sobre histórico. Un solo comando:{" "}
            <code>python3 scripts/start_terminal.py</code>
          </>
        ) : (
          <>
            <strong>Arranque rápido:</strong> ejecuta <code>python3 scripts/start_terminal.py</code>{" "}
            para bootstrap histórico, ticks live, análisis y UI.
          </>
        )}
      </div>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />

      {error ? (
        <div className="error-banner" role="alert">
          <strong>Aviso:</strong> {error}
        </div>
      ) : null}

      <main className="terminal-layout analysis-layout">
        <aside className="sidebar">
          <BotControls
            status={botStatus}
            updatedAt={botUpdatedAt}
            statusMessage={botMessage}
            loading={actionLoading}
            onPause={() => void runAction(() => api.pauseBot(), "Análisis pausado")}
            onResume={() => void runAction(() => api.resumeBot(), "Análisis reanudado")}
            onPanic={() => setPendingAction("panic")}
            onReset={() => setPendingAction("reset")}
          />
          <RecommendationPanel analysis={analysis} />
        </aside>

        <section className="main-column">
          {candles ? (
            <TradingChart
              symbol={candles.symbol}
              currency={candles.currency}
              timeframe={timeframe}
              lastPrice={candles.last_price}
              changePct={candles.change_pct}
              candles={candles.candles}
              analysis={analysis}
              loading={chartLoading}
              onTimeframeChange={changeTimeframe}
            />
          ) : null}
          <SignalHistory signals={analysis?.signals ?? []} />
        </section>

        <aside className="audit-column">
          <AuditFeed events={events} />
        </aside>
      </main>

      <ConfirmDialog
        open={pendingAction === "panic"}
        title="¿Detener el análisis?"
        message="Se dejarán de emitir recomendaciones hasta reinicio manual."
        confirmLabel="Sí, detener"
        cancelLabel="Cancelar"
        danger
        onConfirm={() =>
          void runAction(
            () => api.panicBot("parada de emergencia desde el terminal web"),
            "Análisis detenido",
          )
        }
        onCancel={() => setPendingAction(null)}
      />

      <ConfirmDialog
        open={pendingAction === "reset"}
        title="¿Reiniciar el análisis?"
        message="El motor volverá a emitir recomendaciones sobre precio live."
        confirmLabel="Sí, reiniciar"
        cancelLabel="Cancelar"
        onConfirm={() => void runAction(() => api.resetBot(), "Análisis reiniciado")}
        onCancel={() => setPendingAction(null)}
      />
    </div>
  );
}
