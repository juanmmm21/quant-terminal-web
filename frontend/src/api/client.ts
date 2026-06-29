import type {
  AuditEventsResponse,
  BotActionResponse,
  BotStatusResponse,
  EquityCurve,
  HealthResponse,
  PerformanceMetrics,
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
  botStatus: () => request<BotStatusResponse>("/bot/status"),
  pauseBot: () => request<BotActionResponse>("/bot/pause", { method: "POST" }),
  resumeBot: () => request<BotActionResponse>("/bot/resume", { method: "POST" }),
  panicBot: (reason: string) =>
    request<BotActionResponse>("/bot/panic", {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  metrics: () => request<PerformanceMetrics>("/metrics"),
  equityCurve: () => request<EquityCurve>("/equity-curve"),
  auditEvents: (limit = 50) => request<AuditEventsResponse>(`/audit/events?limit=${limit}`),
};

export { ApiError };
