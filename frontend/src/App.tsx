import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api/client";
import { AuditFeed } from "./components/AuditFeed";
import { BotControls } from "./components/BotControls";
import { EquityChart } from "./components/EquityChart";
import { MetricsGrid } from "./components/MetricsGrid";
import type {
  AuditEvent,
  BotStatus,
  EquityCurve,
  PerformanceMetrics,
} from "./types/api";

const REFRESH_MS = 10_000;

export default function App() {
  const [botStatus, setBotStatus] = useState<BotStatus>("running");
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [equity, setEquity] = useState<EquityCurve | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiVersion, setApiVersion] = useState<string>("");

  const refresh = useCallback(async () => {
    try {
      const [health, status, metricsData, equityData, auditData] = await Promise.all([
        api.health(),
        api.botStatus(),
        api.metrics(),
        api.equityCurve(),
        api.auditEvents(30),
      ]);
      setApiVersion(health.version);
      setBotStatus(status.status);
      setMetrics(metricsData);
      setEquity(equityData);
      setEvents(auditData.events);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load dashboard data";
      setError(message);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const runAction = async (action: () => Promise<unknown>) => {
    setLoading(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Action failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <p className="eyebrow">quant-core-infra</p>
          <h1>quant-terminal-web</h1>
        </div>
        <div className="header-meta">
          <span>API v{apiVersion || "—"}</span>
          <span className="refresh-hint">auto-refresh {REFRESH_MS / 1000}s</span>
        </div>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <main className="dashboard-grid">
        <BotControls
          status={botStatus}
          loading={loading}
          onPause={() => runAction(api.pauseBot)}
          onResume={() => runAction(api.resumeBot)}
          onPanic={() => runAction(() => api.panicBot("operator panic from web terminal"))}
        />
        {metrics ? <MetricsGrid metrics={metrics} /> : null}
        {equity ? <EquityChart symbol={equity.symbol} points={equity.points} /> : null}
        <AuditFeed events={events} />
      </main>
    </div>
  );
}
