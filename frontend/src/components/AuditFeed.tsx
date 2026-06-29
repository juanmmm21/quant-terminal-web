import type { AuditEvent } from "../types/api";
import { GLOSSARY } from "../utils/glossary";
import { formatDateTime } from "../utils/format";
import { HelpTip } from "./HelpTip";

interface AuditFeedProps {
  events: AuditEvent[];
}

const EVENT_LABELS: Record<string, string> = {
  signal_decision: "Decisión de señal",
  risk_check: "Control de riesgo",
  order_submitted: "Orden enviada",
  order_filled: "Orden ejecutada",
  routing_result: "Enrutamiento",
  system_error: "Incidencia",
  metrics_computed: "Métricas",
  analysis_updated: "Análisis actualizado",
};

function formatPayload(payload: Record<string, unknown>): string {
  if (typeof payload.message === "string") {
    return payload.message;
  }
  if (typeof payload.reason === "string") {
    return payload.reason;
  }
  if (payload.verdict != null) {
    return String(payload.verdict);
  }
  if (payload.action != null) {
    return String(payload.action);
  }
  const entries = Object.entries(payload).slice(0, 4);
  if (entries.length === 0) {
    return "";
  }
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ");
}

export function AuditFeed({ events }: AuditFeedProps) {
  return (
    <section className="audit-panel">
      <header className="section-intro">
        <div className="section-intro-text">
          <h2>Actividad del sistema</h2>
          <p>{events.length} eventos</p>
        </div>
        <HelpTip text={GLOSSARY.audit.description} />
      </header>
      {events.length === 0 ? (
        <ul className="audit-feed audit-feed--empty" aria-label="Sin eventos" />
      ) : (
        <ul className="audit-feed">
          {events.map((event) => (
            <li key={event.event_id} className={`audit-item severity-${event.severity}`}>
              <div className="audit-meta">
                <span className="audit-type">
                  {EVENT_LABELS[event.event_type] ?? event.event_type}
                </span>
                <span className={`severity-tag severity-tag-${event.severity}`}>
                  {event.severity}
                </span>
                <span className="audit-time">{formatDateTime(event.occurred_at)}</span>
              </div>
              <div className="audit-body">
                <strong>{event.symbol}</strong>
              </div>
              {formatPayload(event.payload) ? (
                <p className="audit-summary">{formatPayload(event.payload)}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
