const VERDICT_COPY: Record<string, { label: string }> = {
  buy: { label: "Comprar" },
  sell: { label: "Vender" },
  hold: { label: "Mantener" },
};

export function humanizeVerdict(verdict: string): { label: string } {
  const key = verdict.trim().toLowerCase();
  return VERDICT_COPY[key] ?? { label: verdict };
}

export function confidenceLabel(confidence: number): string {
  const pct = confidence * 100;
  if (pct >= 70) {
    return "Alta";
  }
  if (pct >= 40) {
    return "Media";
  }
  return "Baja";
}
