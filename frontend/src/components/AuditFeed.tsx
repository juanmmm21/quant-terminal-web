import type { AuditEvent } from "../types/api";

interface AuditFeedProps {
  events: AuditEvent[];
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function AuditFeed({ events }: AuditFeedProps) {
  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Audit Feed</h2>
        <span className="feed-count">{events.length} events</span>
      </header>
      <ul className="audit-feed">
        {events.map((event) => (
          <li key={event.event_id} className={`audit-item severity-${event.severity}`}>
            <div className="audit-meta">
              <span className="audit-type">{event.event_type}</span>
              <span className="audit-time">{formatTime(event.occurred_at)}</span>
            </div>
            <div className="audit-body">
              <strong>{event.symbol}</strong>
              <span className="audit-correlation">{event.correlation_id}</span>
            </div>
            <pre className="audit-payload">{JSON.stringify(event.payload, null, 0)}</pre>
          </li>
        ))}
      </ul>
    </section>
  );
}
