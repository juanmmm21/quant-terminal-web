import type { BotStatus } from "../types/api";

interface BotStatusBadgeProps {
  status: BotStatus;
}

const LABELS: Record<BotStatus, string> = {
  running: "Running",
  paused: "Paused",
  panic: "PANIC",
};

export function BotStatusBadge({ status }: BotStatusBadgeProps) {
  return <span className={`status-badge status-${status}`}>{LABELS[status]}</span>;
}
