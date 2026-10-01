"""Performance metrics for a BacktestResult (or a bare trade list / daily return series).

Definitions (documented in README):
* R of a trade = initial stop distance in price, measured from the entry FILL:
  r_price = |entry_fill - initial_stop|. ``r_net`` = net P&L (after spread, slippage,
  commission, swap) / (lots * contract_size * units_per_usd * r_price): size-invariant.
* Drawdown: on equity marked to market at EVERY M1 close (``max_dd_pct``) and on the
  worst intrabar mark (``max_dd_intrabar_pct``: bid low for longs / ask high for shorts).
* Sharpe: mean / sd of DAILY returns (equity at the last M1 close of each server day with
  data) x sqrt(252). CAGR from the first to the last bar of the range (calendar time).
* Exposure: share of M1 closes in the range with an open position.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from .timeutil import NS_PER_DAY

TRADING_DAYS = 252


# ------------------------------------------------------------------------ primitives
def profit_factor(pnl) -> float:
    pnl = np.asarray(pnl, dtype=float)
    gp = pnl[pnl > 0].sum()
    gl = -pnl[pnl < 0].sum()
    if gl == 0:
        return float("inf") if gp > 0 else float("nan")
    return float(gp / gl)


def t_stat(x) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / np.sqrt(n))) if sd > 0 else float("nan")


def p_value_mean_gt0(x) -> float:
    """One-sided p-value of H0: mean <= 0 (Student t)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    t = t_stat(x)
    return float(sps.t.sf(t, len(x) - 1)) if np.isfinite(t) else float("nan")


def max_consecutive(mask) -> int:
    best = cur = 0
    for v in np.asarray(mask, dtype=bool):
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return int(best)


def drawdown_stats(equity, t_ns, initial: float | None = None) -> dict:
    """Max drawdown (% and money), its peak/trough/recovery times, the longest drawdown
    duration (peak -> recovery, or -> end if not recovered) and the time to recovery."""
    eq = np.asarray(equity, dtype=float)
    t_ns = np.asarray(t_ns, dtype="int64")
    if len(eq) == 0:
        return {}
    init = eq[0] if initial is None else float(initial)
    peak = np.maximum.accumulate(np.maximum(eq, init))
    dd = eq / peak - 1.0
    i_tr = int(np.argmin(dd))
    pk_val = peak[i_tr]
    at_high = eq >= peak - 1e-9
    before = np.flatnonzero(at_high[:i_tr + 1])
    i_pk = int(before[-1]) if len(before) else None
    after = np.flatnonzero(eq[i_tr:] >= pk_val - 1e-9)
    i_rec = i_tr + int(after[0]) if len(after) and dd[i_tr] < 0 else None
    t_pk = t_ns[i_pk] if i_pk is not None else t_ns[0]
    # longest underwater spell between successive highs (start of range counts as a high)
    highs_t = np.r_[t_ns[0], t_ns[at_high]]
    spells = np.diff(np.r_[highs_t, t_ns[-1]])
    longest = int(spells.max()) if len(spells) else 0
    last_open = (t_ns[-1] - highs_t[-1]) == longest and not at_high[-1]
    day = NS_PER_DAY
    return {
        "max_dd_pct": float(-dd[i_tr] * 100.0),
        "max_dd_money": float((peak - eq).max()),
        "max_dd_peak_time": str(pd.Timestamp(int(t_pk), unit="ns")),
        "max_dd_trough_time": str(pd.Timestamp(int(t_ns[i_tr]), unit="ns")),
        "max_dd_recovery_time": None if i_rec is None else str(pd.Timestamp(int(t_ns[i_rec]), unit="ns")),
        "max_dd_duration_days": float(((t_ns[i_rec] if i_rec is not None else t_ns[-1]) - t_pk) / day),
        "time_to_recovery_days": None if i_rec is None else float((t_ns[i_rec] - t_ns[i_tr]) / day),
        "max_dd_recovered": bool(i_rec is not None or dd[i_tr] == 0),
        "longest_dd_days": float(longest / day),
        "longest_dd_unrecovered": bool(last_open),
    }


def intrabar_drawdown_pct(equity_close, equity_worst, initial: float) -> float:
    """Worst intrabar mark (bid low / ask high) relative to the running peak of the
    CLOSE-marked equity, in %."""
    eq = np.asarray(equity_close, dtype=float)
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(np.maximum(eq, float(initial)))
    return float(100.0 * max(0.0, (1.0 - np.asarray(equity_worst, dtype=float) / peak).max()))


def daily_return_stats(ret: pd.Series, periods: int = TRADING_DAYS) -> dict:
    r = np.asarray(ret, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 2:
        return {"n_days": n}
    sd = r.std(ddof=1)
    downside = r[r < 0]
    dsd = np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)) if n else np.nan
    return {
        "n_days": int(n),
        "mean_daily_ret": float(r.mean()),
        "sd_daily_ret": float(sd),
        "sharpe_ann": float(r.mean() / sd * np.sqrt(periods)) if sd > 0 else float("nan"),
        "sortino_ann": float(r.mean() / dsd * np.sqrt(periods)) if dsd > 0 else float("nan"),
        "ann_vol": float(sd * np.sqrt(periods)),
        "skew_daily": float(sps.skew(r)) if sd > 0 else float("nan"),
        "kurtosis_daily": float(sps.kurtosis(r, fisher=False)) if sd > 0 else float("nan"),
        "worst_day": float(r.min()),
        "best_day": float(r.max()),
        "share_days_negative": float(len(downside) / n),
    }


def cagr(initial: float, final: float, days: float) -> float:
    if days <= 0 or initial <= 0:
        return float("nan")
    if final <= 0:
        return -1.0
    return float((final / initial) ** (365.25 / days) - 1.0)


# ------------------------------------------------------------------------ trade level
def trade_metrics(trades: pd.DataFrame) -> dict:
    """Trade-list statistics in money and in R (size-invariant)."""
    n = int(len(trades))
    out = {"n_trades": n}
    if n == 0:
        return out
    pnl = trades["net_pnl"].to_numpy(float)
    r = trades["r_net"].to_numpy(float)
    rf = r[np.isfinite(r)]
    wins, losses = pnl > 0, pnl < 0
    out.update({
        "net_profit": float(pnl.sum()),
        "gross_profit": float(pnl[wins].sum()),
        "gross_loss": float(pnl[losses].sum()),
        "win_rate": float(wins.mean()),
        "avg_win": float(pnl[wins].mean()) if wins.any() else float("nan"),
        "avg_loss": float(pnl[losses].mean()) if losses.any() else float("nan"),
        "avg_win_r": float(r[wins & np.isfinite(r)].mean()) if (wins & np.isfinite(r)).any() else float("nan"),
        "avg_loss_r": float(r[losses & np.isfinite(r)].mean()) if (losses & np.isfinite(r)).any() else float("nan"),
        "profit_factor": profit_factor(pnl),
        "expectancy": float(pnl.mean()),
        "expectancy_r": float(rf.mean()) if len(rf) else float("nan"),
        "median_r": float(np.median(rf)) if len(rf) else float("nan"),
        "sd_r": float(rf.std(ddof=1)) if len(rf) > 1 else float("nan"),
        "t_stat_r": t_stat(rf),
        "p_value_r": p_value_mean_gt0(rf),
        "max_consecutive_losses": max_consecutive(losses),
        "max_consecutive_wins": max_consecutive(wins),
        "total_commission": float(trades["commission"].sum()),
        "total_swap": float(trades["swap"].sum()),
        "avg_hold_hours": float(trades["hold_minutes"].mean() / 60.0),
        "median_hold_hours": float(trades["hold_minutes"].median() / 60.0),
        "avg_lots": float(trades["lots"].mean()),
        "exit_reasons": {str(k): int(v) for k, v in trades["exit_reason"].value_counts().items()},
    })
    return out


def _group_table(trades: pd.DataFrame, key) -> dict:
    out = {}
    for k, g in trades.groupby(key):
        r = g["r_net"].to_numpy(float)
        out[str(k)] = {"n": int(len(g)), "net_profit": float(g["net_pnl"].sum()),
                       "expectancy_r": float(np.nanmean(r)) if len(r) else float("nan"),
                       "t_stat_r": t_stat(r), "win_rate": float((g["net_pnl"] > 0).mean()),
                       "profit_factor": profit_factor(g["net_pnl"].to_numpy(float))}
    return out


def cost_stress(trades: pd.DataFrame, point: float, value_per_price_per_lot: float,
                extra_points=(10, 20, 40)) -> dict:
    """Recompute trade metrics with an extra cost of X points per round trip (post-hoc:
    same fills and sizes, cost subtracted per trade; exact in R)."""
    out = {}
    if len(trades) == 0:
        return out
    lots = trades["lots"].to_numpy(float)
    pnl = trades["net_pnl"].to_numpy(float)
    rp = trades["r_price"].to_numpy(float)
    r = trades["r_net"].to_numpy(float)
    for x in extra_points:
        p2 = pnl - x * point * lots * value_per_price_per_lot
        r2 = r - x * point / rp
        out[f"+{x}pts"] = {"net_profit": float(p2.sum()), "expectancy": float(p2.mean()),
                           "expectancy_r": float(np.nanmean(r2)), "t_stat_r": t_stat(r2),
                           "profit_factor": profit_factor(p2), "win_rate": float((p2 > 0).mean())}
    return out


def break_even_cost(trades: pd.DataFrame, point: float, value_per_price_per_lot: float) -> dict:
    """Extra cost (points per round trip) at which net expectancy becomes 0: in money
    (sum pnl / sum(point * lots * value)) and in R (mean r_net / mean(point / r_price)).
    Negative = the strategy already loses (a cost REDUCTION of that size would be needed)."""
    if len(trades) == 0:
        return {"break_even_extra_points_money": float("nan"), "break_even_extra_points_r": float("nan")}
    lots = trades["lots"].to_numpy(float)
    pnl = trades["net_pnl"].to_numpy(float)
    rp = trades["r_price"].to_numpy(float)
    r = trades["r_net"].to_numpy(float)
    ok = np.isfinite(r) & np.isfinite(rp) & (rp > 0)
    den_r = np.mean(point / rp[ok]) if ok.any() else float("nan")
    return {
        "break_even_extra_points_money": float(pnl.sum() / (point * value_per_price_per_lot * lots.sum())),
        "break_even_extra_points_r": float(np.mean(r[ok]) / den_r) if ok.any() else float("nan"),
    }


def concentration(trades: pd.DataFrame, daily_pnl: pd.Series | None = None, k: int = 5) -> dict:
    """Share of the net profit coming from the top-k trades and top-k days (NaN if net <= 0)."""
    out = {}
    if len(trades) == 0:
        return out
    pnl = trades["net_pnl"].to_numpy(float)
    net = pnl.sum()
    top = np.sort(pnl)[::-1][:k].sum()
    out["top5_trades_share_of_net"] = float(top / net) if net > 0 else float("nan")
    if daily_pnl is not None and len(daily_pnl):
        d = np.sort(np.asarray(daily_pnl, dtype=float))[::-1][:k].sum()
        dn = float(np.asarray(daily_pnl, dtype=float).sum())
        out["top5_days_share_of_net"] = float(d / dn) if dn > 0 else float("nan")
    return out


# ------------------------------------------------------------------------ full report
def compute_metrics(result, md=None, stress_points=(10, 20, 40), benchmarks: bool = True) -> dict:
    """All run metrics. With ``md`` also the benchmarks (buy & hold, BUY_HOLD_VOLSCALED,
    exposure-matched long) and the regression of the strategy on BUY_HOLD_VOLSCALED."""
    trades = result.trades
    spec = result.spec
    point = float(spec["point"])
    vpl = float(spec["contract_size"]) * float(result.config["account_units_per_usd"])
    init = result.initial_equity
    t = result.eq_t
    m = {"strategy": result.strategy["name"], "timeframe": result.strategy["timeframe"],
         "range_first_bar": result.stats["range_first_bar"], "range_last_bar": result.stats["range_last_bar"]}
    m.update(trade_metrics(trades))
    final = float(result.equity[-1])
    days = (int(t[-1]) - int(t[0])) / NS_PER_DAY if len(t) > 1 else 0.0
    m["initial_equity"] = init
    m["final_equity"] = final
    m["total_return_pct"] = 100.0 * (final / init - 1.0)
    m["cagr"] = cagr(init, final, days)
    dr = result.daily_returns()
    m.update(daily_return_stats(dr))
    m.update(drawdown_stats(result.equity, t, init))
    m["max_dd_intrabar_pct"] = intrabar_drawdown_pct(result.equity, result.equity_worst, init)
    m["equity_marking"] = "M1 close (bid for longs, ask for shorts); intrabar: bid low / ask high"
    m["exposure_pct"] = float(100.0 * result.in_pos.mean()) if len(result.in_pos) else 0.0
    m["mar_ratio"] = m["cagr"] / (m["max_dd_pct"] / 100.0) if m.get("max_dd_pct") else float("nan")
    if len(trades):
        tr = trades.copy()
        tr["year"] = tr["entry_time"].dt.year
        tr["side_name"] = np.where(tr["side"] > 0, "long", "short")
        tr["hour_utc"] = tr["entry_time_utc"].dt.hour
        m["by_side"] = _group_table(tr, "side_name")
        m["by_year"] = _group_table(tr, "year")
        m["by_entry_hour_utc"] = _group_table(tr, "hour_utc")
        m["long_net_profit"] = m["by_side"].get("long", {}).get("net_profit", 0.0)
        m["short_net_profit"] = m["by_side"].get("short", {}).get("net_profit", 0.0)
        m["cost_stress"] = cost_stress(trades, point, vpl, stress_points)
        m.update(break_even_cost(trades, point, vpl))
        m["avg_r_price"] = float(trades["r_price"].mean())
        m["avg_entry_spread_pts"] = float(trades["entry_spread_pts"].mean())
    deq = result.daily_equity()
    yr = deq.groupby(deq.index.year).last()
    prev = np.r_[init, yr.to_numpy()[:-1]]
    m["return_by_year_pct"] = {str(y): float(100.0 * (v / p - 1.0)) for y, v, p in zip(yr.index, yr.to_numpy(), prev)}
    daily_pnl = deq.diff().fillna(deq.iloc[0] - init) if len(deq) else pd.Series(dtype=float)
    m.update(concentration(trades, daily_pnl))
    sk = result.skipped
    m["n_skipped"] = int(len(sk))
    m["skipped_by_reason"] = ({f"{k[0]}:{k[1]}": int(v) for k, v in sk.groupby(["kind", "reason"]).size().items()}
                              if len(sk) else {})
    m["runtime_s"] = result.stats.get("runtime_s")
    m["engine_warnings"] = list(result.stats.get("warnings", []))
    if benchmarks and md is not None:
        from .benchmark import benchmark_report
        m["benchmarks"] = benchmark_report(md, result)
    return m
