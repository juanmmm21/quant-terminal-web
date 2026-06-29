import type { BotStatus } from "../types/api";
import { BotStatusBadge } from "./BotStatusBadge";

interface BotControlsProps {
  status: BotStatus;
  loading: boolean;
  onPause: () => void;
  onResume: () => void;
  onPanic: () => void;
}

export function BotControls({ status, loading, onPause, onResume, onPanic }: BotControlsProps) {
  const panicDisabled = loading || status === "panic";

  return (
    <section className="panel bot-controls">
      <header className="panel-header">
        <h2>Bot Control</h2>
        <BotStatusBadge status={status} />
      </header>
      <div className="control-buttons">
        <button type="button" onClick={onResume} disabled={loading || status === "running" || status === "panic"}>
          Resume
        </button>
        <button type="button" onClick={onPause} disabled={loading || status === "paused" || status === "panic"}>
          Pause
        </button>
        <button type="button" className="panic-button" onClick={onPanic} disabled={panicDisabled}>
          PANIC STOP
        </button>
      </div>
    </section>
  );
}
