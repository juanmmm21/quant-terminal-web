export type BotStatus = "running" | "paused" | "panic";
export type Timeframe = "1m" | "5m" | "10m" | "15m" | "1h";

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

export interface TerminalSummary {
  data_mode: string;
  symbol: string;
  last_price: string;
  price_currency: string;
  change_pct: string;
  recommendation_verdict: string;
  recommendation_confidence: number;
  analysis_timeframe: string;
  bot_status: BotStatus;
  last_sync: string;
}

export interface Recommendation {
  verdict: string;
  action: string;
  side: string | null;
  confidence: number;
  reason: string;
  strategy_id: string;
  reference_price: string;
  event_time: string | null;
}

export interface IndicatorSnapshot {
  rsi: number | null;
  macd_line: number | null;
  signal_line: number | null;
  sma_20: number | null;
  ema_20: number | null;
}

export interface TrainingStats {
  timeframe: string;
  symbol: string;
  bars_analyzed: number;
  signal_count: number;
  enter_signals: number;
  exit_signals: number;
  directional_win_rate: string;
  selected_strategy: string;
  trained_at: string;
}

export interface SignalMarker {
  event_time: string;
  action: string;
  side: string | null;
  confidence: number;
  reason: string;
  reference_price: string;
  strategy_id: string;
}

export interface AnalysisSnapshot {
  symbol: string;
  timeframe: string;
  last_price: string;
  currency: string;
  updated_at: string;
  recommendation: Recommendation;
  indicators: IndicatorSnapshot;
  training: TrainingStats;
  signals: SignalMarker[];
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
  analysis_ready: boolean;
  paths: Record<string, string>;
  modules: Record<string, string>;
  manifest: Record<string, unknown> | null;
  last_checked: string;
}
