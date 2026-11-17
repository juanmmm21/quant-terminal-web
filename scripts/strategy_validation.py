#!/usr/bin/env python3
"""
Out-of-sample validation of the strategy the analysis engine selected.

Runs, via subprocess only (no cross-repo imports):
  event-driven-backtester validate  (purged k-fold with embargo + walk-forward)
  quant-metrics-calculator overfit   (deflated Sharpe ratio + PBO via CSCV)
and writes data/runtime/validation_{timeframe}.json, which the API shows before any strategy
can be promoted to paper trading.

Timing: a candle is stamped at its open time but its signal is computed from its close. Both
the price tick and the signal are therefore moved to the bar close, so a signal is filled at
the close it was computed from and never at an earlier price.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ecosystem_tools import project_root, resolve_cli, run_cli  # noqa: E402

logger = logging.getLogger(__name__)

TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "10m": 600, "15m": 900, "1h": 3600}
REPORT_VERSION = 1
DEFAULT_MAX_AGE_HOURS = float(os.environ.get("TERMINAL_VALIDATION_MAX_AGE_HOURS", "6"))


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                record = json.loads(line)
                if isinstance(record, dict):
                    rows.append(record)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def candles_to_close_ticks(
    candles: list[dict[str, Any]], *, symbol: str, bar_seconds: int
) -> list[dict[str, Any]]:
    """One tick per candle at its close time, priced at the close."""
    step = timedelta(seconds=bar_seconds)
    ticks: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        close_time = parse_time(str(candle["event_time"])) + step
        ticks.append(
            {
                "symbol": symbol,
                "trade_id": f"bar-{index}",
                "price": str(candle["close"]),
                "quantity": str(candle.get("volume") or 1),
                "event_time": close_time.isoformat(),
            }
        )
    return ticks


def shift_signals_to_bar_close(
    signals: list[dict[str, Any]], *, bar_seconds: int
) -> list[dict[str, Any]]:
    step = timedelta(seconds=bar_seconds)
    shifted: list[dict[str, Any]] = []
    for signal in signals:
        if signal.get("action") not in ("enter", "exit"):
            continue
        moved = dict(signal)
        moved["event_time"] = (parse_time(str(signal["event_time"])) + step).isoformat()
        shifted.append(moved)
    return shifted


def pbo_splits(n_bars: int) -> int:
    """16 blocks (12,870 combinations) when there is data for it, fewer (even) otherwise."""
    for splits in (16, 12, 10, 8, 6, 4, 2):
        if n_bars >= splits * 20:
            return splits
    return 2


def report_id(report: dict[str, Any]) -> str:
    body = {key: value for key, value in report.items() if key != "report_id"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def run_validation(
    *,
    symbol: str,
    timeframe: str,
    bar_seconds: int,
    candles_jsonl: Path,
    signal_files: dict[str, Path],
    selected: str,
    n_trials: int,
    work: Path,
    initial_cash: str = "10000",
    position_size: str = "0.01",
    commission_rate: str = "0.001",
) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    candles = read_jsonl(candles_jsonl)
    if len(candles) < 64:
        raise ValueError(f"not enough candles to validate ({len(candles)})")
    ticks_path = work / f"validation_ticks_{timeframe}.jsonl"
    write_jsonl(ticks_path, candles_to_close_ticks(candles, symbol=symbol, bar_seconds=bar_seconds))

    candidate_args: list[str] = []
    excluded: list[str] = []
    for name, path in sorted(signal_files.items()):
        payload = json.loads(path.read_text(encoding="utf-8"))
        shifted = shift_signals_to_bar_close(
            payload if isinstance(payload, list) else [], bar_seconds=bar_seconds
        )
        if not any(signal.get("action") == "enter" for signal in shifted):
            # A strategy that never trades is not a candidate: its flat equity would "win"
            # every fold against any losing strategy and make PBO look reassuring.
            excluded.append(name)
            continue
        shifted_path = work / f"validation_signals_{timeframe}_{name}.jsonl"
        write_jsonl(shifted_path, shifted)
        candidate_args += ["--candidate", f"{name}={shifted_path}"]

    if selected in excluded or not candidate_args:
        raise ValueError(f"selected strategy {selected} produced no trades to validate")

    backtester = resolve_cli("event-driven-backtester")
    common = [
        "--ticks",
        str(ticks_path),
        "--symbol",
        symbol,
        *candidate_args,
        "--initial-cash",
        initial_cash,
        "--position-size",
        position_size,
        "--commission-rate",
        commission_rate,
        "--bar-seconds",
        str(bar_seconds),
    ]
    purged_path = work / f"validation_purged_{timeframe}.json"
    run_cli([backtester, "validate", *common, "--method", "purged-kfold", "--n-splits", "5",
             "--embargo-pct", "0.01", "--output", str(purged_path)])
    walk_path = work / f"validation_walk_{timeframe}.json"
    run_cli([backtester, "validate", *common, "--method", "walk-forward", "--n-splits", "5",
             "--output", str(walk_path)])
    purged = json.loads(purged_path.read_text(encoding="utf-8"))
    walk = json.loads(walk_path.read_text(encoding="utf-8"))

    matrix = dict(purged["returns_matrix"])
    bar_times: list[str] = matrix.pop("bar_times", [])
    matrix["selected"] = selected
    matrix["n_trials"] = n_trials
    matrix_path = work / f"validation_matrix_{timeframe}.json"
    matrix_path.write_text(json.dumps(matrix) + "\n", encoding="utf-8")
    overfit_path = work / f"validation_overfit_{timeframe}.json"
    metrics = resolve_cli("quant-metrics-calculator")
    run_cli([metrics, "overfit", "--returns", str(matrix_path), "--n-splits",
             str(pbo_splits(purged["n_bars"])), "--output", str(overfit_path)])
    overfit = json.loads(overfit_path.read_text(encoding="utf-8"))

    report = build_report(
        symbol=symbol,
        timeframe=timeframe,
        bar_seconds=bar_seconds,
        selected=selected,
        n_trials=n_trials,
        purged=purged,
        walk=walk,
        overfit=overfit,
        excluded=excluded,
        period_start=bar_times[0] if bar_times else None,
        period_end=bar_times[-1] if bar_times else None,
        assumptions={
            "initial_cash": initial_cash,
            "position_size": position_size,
            "commission_rate": commission_rate,
            "fill": "bar close of the candle the signal was computed from",
        },
    )
    return report


def build_report(
    *,
    symbol: str,
    timeframe: str,
    bar_seconds: int,
    selected: str,
    n_trials: int,
    purged: dict[str, Any],
    walk: dict[str, Any],
    overfit: dict[str, Any],
    excluded: list[str],
    period_start: str | None,
    period_end: str | None,
    assumptions: dict[str, str],
) -> dict[str, Any]:
    periods_per_year = 365 * 24 * 3600 // bar_seconds
    dsr = overfit.get("deflated_sharpe") or {}
    pbo = overfit.get("pbo")

    def annualize(value: float | None) -> float | None:
        return None if value is None else float(value) * periods_per_year**0.5

    report: dict[str, Any] = {
        "version": REPORT_VERSION,
        "kind": "backtest",
        "disclaimer": "Backtest on historical Binance candles. Not live or paper performance.",
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_seconds": bar_seconds,
        "strategy": selected,
        "candidates": purged.get("candidates", []),
        "excluded_candidates": excluded,
        "n_trials": n_trials,
        "n_bars": purged.get("n_bars"),
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "assumptions": assumptions,
        "deflated_sharpe_ratio": dsr.get("deflated_sharpe_ratio"),
        "probabilistic_sharpe_ratio": dsr.get("probabilistic_sharpe_ratio"),
        "sharpe_annualized": dsr.get("annualized_sharpe_ratio")
        or annualize(dsr.get("sharpe_ratio")),
        "benchmark_sharpe_annualized": annualize(dsr.get("benchmark_sharpe_ratio")),
        "pbo": None if pbo is None else pbo.get("probability_of_overfitting"),
        "pbo_detail": pbo,
        "pbo_error": overfit.get("pbo_error"),
        "purged_kfold": _summarize(purged, selected, periods_per_year),
        "walk_forward": _summarize(walk, selected, periods_per_year),
    }
    report["report_id"] = report_id(report)
    return report


def _summarize(payload: dict[str, Any], selected: str, periods_per_year: int) -> dict[str, Any]:
    folds = payload.get("folds", [])
    return {
        "method": payload.get("method"),
        "folds": len(folds),
        "label_horizon_bars": payload.get("label_horizon_bars"),
        "embargo_pct": payload.get("embargo_pct"),
        "oos_bars": payload.get("oos_bars"),
        "oos_sharpe_annualized": float(payload.get("oos_sharpe", 0.0)) * periods_per_year**0.5,
        "oos_total_return": payload.get("oos_total_return"),
        "selected_in_folds": sum(1 for fold in folds if fold.get("selected") == selected),
        "fold_detail": [
            {
                "test_start": fold.get("test_start"),
                "test_end": fold.get("test_end"),
                "selected": fold.get("selected"),
                "train_bars": fold.get("train_bars"),
                "purged_bars": fold.get("purged_bars"),
                "oos_sharpe_annualized": float(fold.get("out_of_sample_sharpe", 0.0))
                * periods_per_year**0.5,
                "oos_return": fold.get("out_of_sample_return"),
            }
            for fold in folds
        ],
    }


def is_fresh(path: Path, *, strategy: str, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> bool:
    if not path.exists():
        return False
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        generated = parse_time(str(report["generated_at"]))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False
    if report.get("strategy") != strategy or report.get("version") != REPORT_VERSION:
        return False
    return datetime.now(tz=UTC) - generated < timedelta(hours=max_age_hours)


def write_report(runtime: Path, report: dict[str, Any]) -> Path:
    output = runtime / f"validation_{report['timeframe']}.json"
    tmp = output.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the selected strategy out of sample")
    parser.add_argument("--timeframe", default="1h", choices=sorted(TIMEFRAME_SECONDS))
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from analysis_engine import run_analysis

    run_analysis(symbol=args.symbol.upper(), ui_timeframe=args.timeframe, force_validation=True)
    print(project_root() / "data" / "runtime" / f"validation_{args.timeframe}.json")


if __name__ == "__main__":
    main()
