export type BotStatus = "running" | "paused" | "panic";

export interface BotStatusResponse {
  status: BotStatus;
  updated_at: string;
  message: string | null;
}

export interface BotActionResponse {
  status: BotStatus;
  updated_at: string;
  action: string;
  message: string;
}

export interface PerformanceMetrics {
  symbol: string;
  sharpe_ratio: string;
  sortino_ratio: string;
  profit_factor: string;
  max_drawdown_pct: string;
  total_return_pct: string;
  win_rate: string;
  trade_count: number;
  computed_at: string | null;
}

export interface EquityPoint {
  event_time: string;
  equity: string;
}

export interface EquityCurve {
  symbol: string;
  points: EquityPoint[];
}

export interface AuditEvent {
  event_id: string;
  event_type: string;
  symbol: string;
  correlation_id: string;
  occurred_at: string;
  severity: string;
  payload: Record<string, unknown>;
}

export interface AuditEventsResponse {
  events: AuditEvent[];
  count: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
}
