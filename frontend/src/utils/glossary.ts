export interface GlossaryEntry {
  title: string;
  description: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  recommendation: {
    title: "Recomendación",
    description:
      "Sugerencia automática basada en datos históricos y el precio actual. No es asesoramiento financiero: úsala como orientación para aprender.",
  },
  confidence: {
    title: "Confianza",
    description:
      "Qué tan alineadas están las señales técnicas entre sí. Un valor bajo significa duda; uno alto, mayor consenso del modelo.",
  },
  rsi: {
    title: "RSI",
    description:
      "Índice de fuerza relativa (0–100). Por encima de 70 suele indicar sobrecompra; por debajo de 30, sobreventa.",
  },
  macd: {
    title: "MACD",
    description:
      "Mide el momentum del precio. Cuando la línea MACD cruza la señal hacia arriba, a menudo se interpreta como impulso alcista.",
  },
  timeframe: {
    title: "Marco temporal",
    description:
      "Cada vela resume el movimiento del precio en ese intervalo. 1h = una hora por vela; 1m = un minuto por vela.",
  },
  motor: {
    title: "Motor de análisis",
    description:
      "Proceso en segundo plano que actualiza precios, recalcula indicadores y genera recomendaciones.",
  },
  signals: {
    title: "Señales",
    description:
      "Momentos en los que el modelo detectó una oportunidad de entrada (comprar) o salida (vender) en el histórico.",
  },
  training: {
    title: "Entrenamiento histórico",
    description:
      "El sistema revisa velas pasadas para calibrar la estrategia y estimar qué tan acertadas fueron señales similares.",
  },
  audit: {
    title: "Registro de auditoría",
    description:
      "Historial de eventos del ecosistema: órdenes simuladas, métricas y decisiones internas. Útil para trazabilidad.",
  },
  changePct: {
    title: "Variación",
    description: "Cambio porcentual del precio respecto al inicio del periodo mostrado en el gráfico.",
  },
};
