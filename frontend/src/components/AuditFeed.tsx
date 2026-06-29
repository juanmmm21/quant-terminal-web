import type { AuditEvent } from "../types/api";
import { formatDateTime } from "../utils/format";

interface AuditFeedProps {
  events: AuditEvent[];
}

const EVENT_LABELS: Record<string, string> = {
  signal_decision: "Decisión de señal",
  risk_check: "Control de riesgo",
  order_submitted: "Orden enviada",
  order_filled: "Orden ejecutada",
  routing_result: "Resultado de routing",
  system_error: "Error del sistema",
  metrics_computed: "Métricas calculadas",
};

const SEVERITY_LABELS: Record<string, string> = {
  info: "Info",
  warning: "Aviso",
  error: "Error",
  critical: "Crítico",
};

function summarizePayload(event: AuditEvent): string {
  const payload = event.payload;
  if (event.event_type === "system_error" && typeof payload.message === "string") {
    return payload.message;
  }
  if (event.event_type === "order_filled" && payload.fill_price) {
    return `Fill @ ${payload.fill_price}`;
  }
  if (event.event_type === "risk_check" && payload.verdict) {
    return `Veredicto: ${String(payload.verdict)}`;
  }
  return JSON.stringify(payload);
}

export function AuditFeed({ events }: AuditFeedProps) {
  return (
    <section className="audit-panel">
      <header className="section-header">
        <h2>Registro de auditoría</h2>
        <p className="section-subtitle">{events.length} eventos recientes</p>
      </header>
      {events.length === 0 ? (
        <p className="empty-state">No hay eventos de auditoría recientes.</p>
      ) : (
        <ul className="audit-feed">
          {events.map((event) => (
            <li key={event.event_id} className={`audit-item severity-${event.severity}`}>
              <div className="audit-meta">
                <span className="audit-type">
                  {EVENT_LABELS[event.event_type] ?? event.event_type}
                </span>
                <span className={`severity-tag severity-tag-${event.severity}`}>
                  {SEVERITY_LABELS[event.severity] ?? event.severity}
                </span>
                <span className="audit-time">{formatDateTime(event.occurred_at)}</span>
              </div>
              <div className="audit-body">
                <strong>{event.symbol}</strong>
                <span className="audit-correlation">ID: {event.correlation_id}</span>
              </div>
              <p className="audit-summary">{summarizePayload(event)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
