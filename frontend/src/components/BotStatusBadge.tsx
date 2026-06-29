import type { BotStatus } from "../types/api";

interface BotStatusBadgeProps {
  status: BotStatus;
}

const LABELS: Record<BotStatus, string> = {
  running: "En marcha",
  paused: "Pausado",
  panic: "Detenido",
};

export function BotStatusBadge({ status }: BotStatusBadgeProps) {
  return <span className={`status-badge status-${status}`}>{LABELS[status]}</span>;
}
