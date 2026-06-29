import type { BotStatus } from "../types/api";
import { formatDateTime, formatRelative } from "../utils/format";
import { BotStatusBadge } from "./BotStatusBadge";

interface BotControlsProps {
  status: BotStatus;
  updatedAt: string | null;
  statusMessage: string | null;
  loading: boolean;
  onPause: () => void;
  onResume: () => void;
  onPanic: () => void;
  onReset: () => void;
}

const STATUS_HELP: Record<BotStatus, string> = {
  running: "El bot opera con normalidad. Puedes pausarlo o activar la parada de emergencia.",
  paused: "Las nuevas operaciones están bloqueadas. Pulsa Reanudar para continuar.",
  panic: "Todas las operaciones están detenidas. Revisa el motivo y reinicia cuando sea seguro.",
};

export function BotControls({
  status,
  updatedAt,
  statusMessage,
  loading,
  onPause,
  onResume,
  onPanic,
  onReset,
}: BotControlsProps) {
  const isPanic = status === "panic";

  return (
    <section className={`panel bot-controls ${isPanic ? "panel-panic" : ""}`}>
      <header className="section-header">
        <div className="panel-header-row">
          <h2>Control del bot</h2>
          <BotStatusBadge status={status} />
        </div>
      </header>

      <p className="status-help">{STATUS_HELP[status]}</p>

      {updatedAt ? (
        <p className="status-meta">
          Último cambio: <strong>{formatDateTime(updatedAt)}</strong>
          <span className="status-relative"> ({formatRelative(updatedAt)})</span>
        </p>
      ) : null}

      {statusMessage ? (
        <p className="status-message">
          <span className="status-message-label">Motivo:</span> {statusMessage}
        </p>
      ) : null}

      {isPanic ? (
        <div className="panic-callout" role="alert">
          <strong>Parada de emergencia activa.</strong> Resume y Pause están deshabilitados hasta
          que reinicies el bot.
        </div>
      ) : null}

      <div className="control-buttons">
        <button
          type="button"
          className="button-primary"
          title={isPanic ? "No disponible en modo pánico" : status === "running" ? "El bot ya está en marcha" : undefined}
          onClick={onResume}
          disabled={loading || status === "running" || isPanic}
        >
          ▶ Reanudar
        </button>
        <button
          type="button"
          title={isPanic ? "No disponible en modo pánico" : status === "paused" ? "El bot ya está pausado" : undefined}
          onClick={onPause}
          disabled={loading || status === "paused" || isPanic}
        >
          ⏸ Pausar
        </button>
        <button
          type="button"
          className="panic-button"
          title={isPanic ? "El pánico ya está activo" : "Detiene todas las operaciones de inmediato"}
          onClick={onPanic}
          disabled={loading || isPanic}
        >
          ⛔ Parada de emergencia
        </button>
        {isPanic ? (
          <button
            type="button"
            className="button-reset"
            onClick={onReset}
            disabled={loading}
          >
            ↺ Reiniciar bot
          </button>
        ) : null}
      </div>
    </section>
  );
}
