"""Command line: run one backtest, write trades.csv / equity.csv / metrics.json and append the
experiment registry.

    python -m kq.run --data KQ_XAUUSD_M1.csv --spec KQ_XAUUSD_spec.json --strategy REF_T0 \
        --params '{"adx_min": 20}' --start 2022-01-01 --end 2024-12-31 --out runs/t0_dev

``--start`` / ``--end`` are server-time dates; ``--end`` is INCLUSIVE (the whole day is
tested). All data in the file (also before ``--start``) is used to warm up indicators.
``--strategy`` accepts every name in kq.strategies.STRATEGIES plus the benchmarks
BUY_HOLD_VOLSCALED and BUY_HOLD.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .costs import CostModel, commission_rt_from_spec
from .data import MarketData
from .engine import BacktestConfig, run_backtest
from .metrics import compute_metrics
from .registry import DEFAULT_REGISTRY, append_experiment, build_record, git_info, sanitize
from .strategies import BENCHMARKS, STRATEGIES, make_strategy
from .validation import bootstrap_ci, calibrate_random_entry, deflated_sharpe_ratio, monte_carlo_trades


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m kq.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="KQ_<SYMBOL>_M1.csv exported from MT5")
    ap.add_argument("--spec", default=None, help="KQ_<SYMBOL>_spec.json (optional; XAUUSD defaults)")
    ap.add_argument("--strategy", required=True, help=f"one of {sorted(STRATEGIES)} or {list(BENCHMARKS)}")
    ap.add_argument("--params", default="{}", help="JSON dict of strategy parameters")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD server time (inclusive)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD server time (INCLUSIVE)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--initial-equity", type=float, default=10_000.0, help="account currency")
    ap.add_argument("--risk-pct", type=float, default=1.0, help="%% of balance risked per trade")
    ap.add_argument("--fixed-lots", type=float, default=None, help="use fixed lots instead of risk sizing")
    ap.add_argument("--units-per-usd", type=float, default=None,
                    help="1 (USD account) or 100 (USC cent account); default from spec account_currency")
    ap.add_argument("--slippage-points", type=float, default=0.0)
    ap.add_argument("--commission", type=float, default=None,
                    help="per lot round turn, account currency (default: 2 x |commission_per_lot_side_observed| "
                         "from the spec if present, else 0)")
    ap.add_argument("--swap", action="store_true", help="apply swaps (values from the spec unless overridden)")
    ap.add_argument("--swap-long", type=float, default=None)
    ap.add_argument("--swap-short", type=float, default=None)
    ap.add_argument("--spread-mult", type=float, default=1.0)
    ap.add_argument("--spread-floor", type=float, default=0.0, help="minimum spread in points")
    ap.add_argument("--rollover-from", type=int, default=1425, help="no-entry window start, server minute")
    ap.add_argument("--rollover-to", type=int, default=75, help="no-entry window end, server minute")
    ap.add_argument("--max-spread-points", type=float, default=60.0, help="entry spread cap (0 disables)")
    ap.add_argument("--entry-deadline-min", type=float, default=90.0,
                    help="pending entries expire this many minutes after the open of the bar in which they "
                         "become executable (and at the end of that bar)")
    ap.add_argument("--hypothesis-id", default=None)
    ap.add_argument("--experiment-id", default=None)
    ap.add_argument("--split", default=None, help="split name, e.g. dev / validation / holdout")
    ap.add_argument("--n-trials", type=int, default=1, help="trials tried so far (Deflated Sharpe)")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--no-registry", action="store_true")
    ap.add_argument("--equity-freq", default="H1", help="M1 | M5 | M15 | H1 | H4 | D1")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--n-mc", type=int, default=2000)
    ap.add_argument("--no-benchmarks", action="store_true")
    return ap


def _config(a, md) -> BacktestConfig:
    units = a.units_per_usd if a.units_per_usd is not None else md.spec.default_units_per_usd()
    commission = a.commission
    if commission is None:
        commission = commission_rt_from_spec(md.spec) or 0.0
    costs = CostModel(slippage_points=a.slippage_points, commission_per_lot_rt=commission, apply_swap=a.swap,
                      swap_long=a.swap_long, swap_short=a.swap_short, spread_multiplier=a.spread_mult,
                      spread_floor_points=a.spread_floor)
    start = pd.Timestamp(a.start) if a.start else None
    end = pd.Timestamp(a.end) + pd.Timedelta(days=1) if a.end else None
    risk = None if a.fixed_lots is not None else a.risk_pct
    return BacktestConfig(start=start, end=end, initial_equity=a.initial_equity, risk_pct=risk,
                          fixed_lots=a.fixed_lots, account_units_per_usd=units, costs=costs,
                          rollover_from_min=a.rollover_from, rollover_to_min=a.rollover_to,
                          max_spread_points=a.max_spread_points, entry_deadline_min=a.entry_deadline_min)


def _run_benchmark(a, md, cfg, out: Path) -> dict:
    from .benchmark import buy_and_hold_returns, buy_hold_volscaled
    from .metrics import daily_return_stats
    t0 = time.perf_counter()
    params = json.loads(a.params or "{}")
    if a.strategy.upper() == "BUY_HOLD_VOLSCALED":
        res = buy_hold_volscaled(md, cfg.start, cfg.end, cfg.costs, cfg.initial_equity, cfg.account_units_per_usd,
                                 rollover_from_min=cfg.rollover_from_min, rollover_to_min=cfg.rollover_to_min,
                                 max_spread_points=cfg.max_spread_points, **params)
        res["fills"].to_csv(out / "trades.csv", index=False)
        eq = res["daily_equity"].rename_axis("date").to_frame()
        eq["ret"] = res["daily_returns"].to_numpy()
        eq.to_csv(out / "equity.csv")
        metrics = dict(res["metrics"])
        dr = res["daily_returns"]
    else:
        dr = buy_and_hold_returns(md, cfg.start, cfg.end)
        eq = (cfg.initial_equity * (1 + dr).cumprod()).rename("equity").rename_axis("date").to_frame()
        eq["ret"] = dr.to_numpy()
        eq.to_csv(out / "equity.csv")
        pd.DataFrame(columns=["time"]).to_csv(out / "trades.csv", index=False)
        metrics = {"name": "BUY_HOLD", "total_return_pct": float(100 * (np.prod(1 + dr.to_numpy()) - 1))}
        metrics.update(daily_return_stats(dr))
    metrics["bootstrap_sharpe"] = bootstrap_ci(dr.to_numpy(), "sharpe", n_boot=a.n_boot)
    metrics["runtime_s"] = round(time.perf_counter() - t0, 3)
    return {"metrics": metrics, "strategy": {"name": a.strategy.upper(), "timeframe": "D1", "params": params}}


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    t_all = time.perf_counter()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    md = MarketData.from_csv(a.data, a.spec)
    load_s = time.perf_counter() - t0
    cfg = _config(a, md)
    params = json.loads(a.params or "{}")
    if not isinstance(params, dict):
        raise SystemExit("--params must be a JSON object")

    if a.strategy.upper() in BENCHMARKS:
        bench = _run_benchmark(a, md, cfg, out)
        metrics, strat_info = bench["metrics"], bench["strategy"]
        result = None
    else:
        if a.strategy.upper() == "RANDOM_ENTRY" and params.get("p_entry") is None:
            cal = calibrate_random_entry(md, params.get("target", "REF_T0"), params.get("target_params", {}), cfg)
            params["p_entry"] = cal["p_entry"]
        strategy = make_strategy(a.strategy, params)
        result = run_backtest(md, strategy, cfg)
        for w in result.stats.get("warnings", []):
            print(f"WARNING: {w}", file=sys.stderr)
        metrics = compute_metrics(result, md=None if a.no_benchmarks else md)
        dr = result.daily_returns()
        metrics["bootstrap_sharpe"] = bootstrap_ci(dr.to_numpy(), "sharpe", n_boot=a.n_boot)
        metrics["bootstrap_mean_daily"] = bootstrap_ci(dr.to_numpy(), "mean", n_boot=a.n_boot)
        metrics["deflated_sharpe"] = deflated_sharpe_ratio(dr.to_numpy(), n_trials=a.n_trials)
        if len(result.trades) >= 2:
            metrics["monte_carlo_trades"] = monte_carlo_trades(result.trades["r_net"].to_numpy(), n_sims=a.n_mc,
                                                               risk_fraction=(cfg.risk_pct or 1.0) / 100.0)
        files = result.to_files(out, a.equity_freq)
        strat_info = result.strategy

    metrics["load_s"] = round(load_s, 3)
    metrics["total_s"] = round(time.perf_counter() - t_all, 3)
    run_info = {"cli": sys.argv if argv is None else ["kq.run"] + list(argv), "data": md.info(),
                "data_quality": md.source.get("quality"), "config": cfg.to_dict(), "strategy": strat_info}
    run_info.update(git_info())
    with open(out / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(sanitize({"run": run_info, "metrics": metrics}), f, indent=2, ensure_ascii=False, allow_nan=False)

    if not a.no_registry:
        if result is not None:
            rec = build_record(result, metrics, md, hypothesis_id=a.hypothesis_id, split=a.split,
                               experiment_id=a.experiment_id, extra={"out_dir": str(out.resolve())})
        else:
            rec = {"experiment_id": a.experiment_id, "hypothesis_id": a.hypothesis_id, "split": a.split,
                   "strategy": strat_info, "data": md.info(), "range": {"start": cfg.to_dict()["start"],
                                                                         "end": cfg.to_dict()["end"]},
                   "costs": cfg.costs.to_dict(), "config": cfg.to_dict(), "metrics": metrics,
                   "extra": {"out_dir": str(out.resolve())}}
            rec.update(git_info())
            rec = {k: v for k, v in rec.items() if v is not None or k in ("hypothesis_id", "split")}
        written = append_experiment(rec, a.registry)
        exp_id = written["experiment_id"]
    else:
        exp_id = None
    summary = {k: metrics.get(k) for k in ("n_trades", "expectancy_r", "t_stat_r", "profit_factor", "sharpe_ann",
                                            "cagr", "max_dd_pct", "total_return_pct", "runtime_s", "total_s")}
    summary.update({"experiment_id": exp_id, "out": str(out)})
    print(json.dumps(sanitize(summary)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
