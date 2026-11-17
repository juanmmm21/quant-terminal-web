import type {
  AnalysisSnapshot,
  AuditEventsResponse,
  BotActionResponse,
  BotStatusResponse,
  CandlesData,
  EcosystemStatus,
  HealthResponse,
  PromotionResponse,
  TerminalSummary,
  Timeframe,
  ValidationResponse,
} from "../types/api";

const API_BASE = "/api/v1";
const TOKEN_KEY = "quant.controlToken";

/** Control token for the kill switch and other controls. Kept for this tab only. */
export function getControlToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setControlToken(token: string | null): void {
  try {
    if (token) {
      window.sessionStorage.setItem(TOKEN_KEY, token);
    } else {
      window.sessionStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // storage unavailable: the token simply is not remembered
  }
}

function controlHeaders(): Record<string, string> {
  const token = getControlToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiErrorDetail {
  message?: string;
  failed_checks?: string[];
}

async function request<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = init?.timeoutMs ?? 12_000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const { timeoutMs: _ignored, headers, ...rest } = init ?? {};
    const response = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: { "Content-Type": "application/json", ...(headers ?? {}) },
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string | ApiErrorDetail };
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (body.detail?.message) {
          const failed = body.detail.failed_checks?.join(", ");
          detail = failed ? `${body.detail.message}: ${failed}` : body.detail.message;
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
  pauseBot: () =>
    request<BotActionResponse>("/bot/pause", { method: "POST", headers: controlHeaders() }),
  resumeBot: () =>
    request<BotActionResponse>("/bot/resume", { method: "POST", headers: controlHeaders() }),
  panicBot: (reason: string) =>
    request<BotActionResponse>("/bot/panic", {
      method: "POST",
      headers: controlHeaders(),
      body: JSON.stringify({ reason }),
    }),
  resetBot: () =>
    request<BotActionResponse>("/bot/reset", { method: "POST", headers: controlHeaders() }),
  validation: (timeframe: Timeframe) =>
    request<ValidationResponse>(`/validation?timeframe=${encodeURIComponent(timeframe)}`),
  promotion: () => request<PromotionResponse>("/paper/promotion"),
  promote: (timeframe: Timeframe, reportId: string) =>
    request<PromotionResponse>("/paper/promote", {
      method: "POST",
      headers: controlHeaders(),
      body: JSON.stringify({ timeframe, report_id: reportId }),
    }),
  demote: () =>
    request<PromotionResponse>("/paper/demote", { method: "POST", headers: controlHeaders() }),
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
