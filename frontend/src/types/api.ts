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
  currency: string;
  label: string;
  initial_capital: string;
  current_capital: string;
  points: EquityPoint[];
}

export interface Candle {
  open_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface CandlesData {
  symbol: string;
  interval: string;
  currency: string;
  last_price: string;
  change_pct: string;
  candles: Candle[];
}

export interface TradeFill {
  order_id: string;
  symbol: string;
  side: "buy" | "sell" | string;
  quantity: string;
  price: string;
  commission: string;
  filled_at: string;
  realized_pnl: string | null;
  label: string | null;
}

export interface TradesData {
  trades: TradeFill[];
  count: number;
  closed_round_trips: number;
}

export interface TerminalSummary {
  data_mode: string;
  symbol: string;
  last_price: string;
  price_currency: string;
  account_capital: string;
  capital_currency: string;
  capital_change: string;
  trade_count: number;
  bot_status: BotStatus;
  last_sync: string;
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
  data_mode: string;
}

export interface EcosystemStatus {
  data_mode: string;
  ecosystem_ready: boolean;
  lakehouse_ready: boolean;
  live_ticks_ready: boolean;
  paths: Record<string, string>;
  modules: Record<string, string>;
  manifest: Record<string, unknown> | null;
  last_checked: string;
}
