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

async function request<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = init?.timeoutMs ?? 12_000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      signal: controller.signal,
      ...init,
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) {
          detail = typeof body.detail === "string" ? body.detail : response.statusText;
        }
      } catch {
        // keep status text
      }
      throw new ApiError(detail, response.status);
    }
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("La API no respondió a tiempo. ¿Está en marcha en :8000?", 504);
    }
    if (err instanceof TypeError) {
      throw new ApiError("No se pudo conectar con la API. Ejecuta npm start desde quant-terminal-web.", 0);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
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
  candles: (timeframe: Timeframe, limit = 10_000) =>
    request<CandlesData>(
      `/market/candles?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
      { timeoutMs: 45_000 },
    ),
  analysisSnapshot: (timeframe: Timeframe) =>
    request<AnalysisSnapshot>(`/analysis/snapshot?timeframe=${encodeURIComponent(timeframe)}`),
  auditEvents: (limit = 50) => request<AuditEventsResponse>(`/audit/events?limit=${limit}`),
  ecosystemStatus: () => request<EcosystemStatus>("/ecosystem/status"),
};

export { ApiError };
