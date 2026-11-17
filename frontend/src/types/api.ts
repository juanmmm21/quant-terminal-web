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

export interface ValidationFold {
  test_start: string;
  test_end: string;
  selected: string;
  train_bars: number;
  purged_bars: number;
  oos_sharpe_annualized: number;
  oos_return: number;
}

export interface OosSummary {
  method: string;
  folds: number;
  label_horizon_bars: number;
  embargo_pct: number;
  oos_bars: number;
  oos_sharpe_annualized: number;
  oos_total_return: number;
  selected_in_folds: number;
  fold_detail: ValidationFold[];
}

export interface ValidationReport {
  report_id: string;
  kind: "backtest";
  disclaimer: string;
  symbol: string;
  timeframe: string;
  strategy: string;
  candidates: string[];
  excluded_candidates: string[];
  n_trials: number;
  n_bars: number;
  period_start: string | null;
  period_end: string | null;
  generated_at: string;
  deflated_sharpe_ratio: number | null;
  probabilistic_sharpe_ratio: number | null;
  sharpe_annualized: number | null;
  benchmark_sharpe_annualized: number | null;
  pbo: number | null;
  pbo_error: string | null;
  purged_kfold: OosSummary;
  walk_forward: OosSummary;
}

export interface GateCheck {
  name: string;
  value: number | null;
  threshold: number;
  comparison: string;
  passed: boolean;
  explanation: string;
}

export interface GateEvaluation {
  passed: boolean;
  mode: "enforce" | "acknowledge";
  checks: GateCheck[];
}

export interface ValidationResponse {
  report: ValidationReport;
  gate: GateEvaluation;
}

export interface Promotion {
  active: boolean;
  symbol: string;
  timeframe: string;
  strategy: string;
  report_id: string;
  gate_passed: boolean;
  gate_mode: string;
  promoted_at: string;
  promoted_by: string;
  validation: Record<string, number | string | null>;
}

export interface PromotionResponse {
  promotion: Promotion | null;
}
