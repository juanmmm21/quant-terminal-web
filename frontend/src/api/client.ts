import type {
  AnalysisSnapshot,
  AuditEventsResponse,
  BotActionResponse,
  BotStatusResponse,
  CandlesData,
  EcosystemStatus,
  HealthResponse,
  TerminalSummary,
  Timeframe,
} from "../types/api";

const API_BASE = "/api/v1";

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // keep status text
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  summary: () => request<TerminalSummary>("/summary"),
  botStatus: () => request<BotStatusResponse>("/bot/status"),
  pauseBot: () => request<BotActionResponse>("/bot/pause", { method: "POST" }),
  resumeBot: () => request<BotActionResponse>("/bot/resume", { method: "POST" }),
  panicBot: (reason: string) =>
    request<BotActionResponse>("/bot/panic", {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  resetBot: () => request<BotActionResponse>("/bot/reset", { method: "POST" }),
  candles: (timeframe: Timeframe, limit = 500) =>
    request<CandlesData>(`/market/candles?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`),
  analysisSnapshot: (timeframe: Timeframe) =>
    request<AnalysisSnapshot>(`/analysis/snapshot?timeframe=${encodeURIComponent(timeframe)}`),
  auditEvents: (limit = 50) => request<AuditEventsResponse>(`/audit/events?limit=${limit}`),
  ecosystemStatus: () => request<EcosystemStatus>("/ecosystem/status"),
};

export { ApiError };
