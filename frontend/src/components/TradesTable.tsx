import type { TradeFill } from "../types/api";
import { formatDateTime, formatMoney } from "../utils/format";

interface TradesTableProps {
  trades: TradeFill[];
  closedRoundTrips: number;
}

function sideLabel(side: string): string {
  return side === "buy" ? "Compra" : side === "sell" ? "Venta" : side;
}

export function TradesTable({ trades, closedRoundTrips }: TradesTableProps) {
  return (
    <section className="trades-panel">
      <header className="section-header">
        <div>
          <h2>Operaciones ejecutadas</h2>
          <p className="section-subtitle">
            {closedRoundTrips} round-trips cerrados · {trades.length} fills en total
          </p>
        </div>
      </header>

      {trades.length === 0 ? (
        <p className="empty-state">Aún no hay operaciones registradas.</p>
      ) : (
        <div className="table-wrap">
          <table className="trades-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Operación</th>
                <th>Lado</th>
                <th>Cantidad</th>
                <th>Precio BTC</th>
                <th>Comisión</th>
                <th>PnL realizado</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => {
                const pnl = trade.realized_pnl ? Number(trade.realized_pnl) : null;
                return (
                  <tr key={trade.order_id}>
                    <td>{formatDateTime(trade.filled_at)}</td>
                    <td>
                      <span className="trade-label">{trade.label ?? trade.order_id}</span>
                    </td>
                    <td>
                      <span className={`side-pill side-${trade.side}`}>{sideLabel(trade.side)}</span>
                    </td>
                    <td>{trade.quantity} BTC</td>
                    <td>{formatMoney(trade.price)} USDT</td>
                    <td>{formatMoney(trade.commission)}</td>
                    <td className={pnl === null ? "pnl-na" : pnl >= 0 ? "pnl-pos" : "pnl-neg"}>
                      {pnl === null ? "—" : `${pnl >= 0 ? "+" : ""}${formatMoney(trade.realized_pnl!)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
