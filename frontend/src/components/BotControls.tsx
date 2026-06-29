import type { BotStatus } from "../types/api";
import { GLOSSARY } from "../utils/glossary";
import { formatDateTime, formatRelative } from "../utils/format";
import { BotStatusBadge } from "./BotStatusBadge";
import { HelpTip } from "./HelpTip";

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
      <header className="section-intro compact">
        <div className="section-intro-text">
          <h2>Motor</h2>
        </div>
        <div className="motor-status-row">
          <BotStatusBadge status={status} />
          <HelpTip text={GLOSSARY.motor.description} />
        </div>
      </header>

      {updatedAt ? (
        <p className="status-meta">
          {formatRelative(updatedAt)} · {formatDateTime(updatedAt)}
        </p>
      ) : null}

      {statusMessage ? <p className="status-message">{statusMessage}</p> : null}

      <div className="control-buttons">
        <button
          type="button"
          className="button-primary"
          onClick={onResume}
          disabled={loading || status === "running" || isPanic}
        >
          Reanudar
        </button>
        <button type="button" onClick={onPause} disabled={loading || status === "paused" || isPanic}>
          Pausar
        </button>
        <button
          type="button"
          className="panic-button"
          onClick={onPanic}
          disabled={loading || isPanic}
        >
          Parada de emergencia
        </button>
        {isPanic ? (
          <button type="button" className="button-reset" onClick={onReset} disabled={loading}>
            Reiniciar
          </button>
        ) : null}
      </div>
    </section>
  );
}
