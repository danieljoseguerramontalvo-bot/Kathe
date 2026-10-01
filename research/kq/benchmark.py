"""Benchmarks.

* ``buy_and_hold_returns``: daily returns of holding gold (bid closes, no costs, 1x notional).
* ``exposure_matched_long``: long gold only while the strategy has a position (whatever its
  side), M1 close-to-close returns summed per server day; isolates the gold drift earned
  by merely being in the market.
* ``buy_hold_volscaled`` (BUY_HOLD_VOLSCALED): always long, rebalanced once per server day at
  the first M1 bar outside the rollover window with spread <= the cap, sized so that one ATR14(D1) move (last
  completed D1 bar) = ``target_pct`` % of equity. Rebalances pay the same cost model as the
  strategies: buys at ask + slippage, sells at bid - slippage, commission = half the
  round-turn commission per lot traded per side, long swap at every rollover (x3 on the
  triple day). Trend strategies must be compared against it.
* ``benchmark_report``: summary of the three plus an OLS regression of the strategy's daily
  returns on BUY_HOLD_VOLSCALED (beta, annualised alpha and its t-stat).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import CostModel, floor_to_step, rollover_events
from .data import MarketData, last_closed_index
from .indicators import atr_mt5
from .metrics import cagr, daily_return_stats, drawdown_stats
from .timeutil import NS_PER_DAY, to_ns


def _range_idx(md: MarketData, start, end):
    s = to_ns(start) if start is not None else int(md.t[0])
    e = to_ns(end) if end is not None else int(md.t[-1]) + 1
    j0, j1 = int(np.searchsorted(md.t, s)), int(np.searchsorted(md.t, e))
    if j1 <= j0:
        raise ValueError("empty range")
    return j0, j1


def _day_last_index(t: np.ndarray) -> np.ndarray:
    d = t // NS_PER_DAY
    return np.flatnonzero(np.r_[d[1:] != d[:-1], True])


def buy_and_hold_returns(md: MarketData, start=None, end=None) -> pd.Series:
    j0, j1 = _range_idx(md, start, end)
    t, c = md.t[j0:j1], md.c[j0:j1]
    last = _day_last_index(t)
    closes = c[last]
    prev = np.r_[md.o[j0], closes[:-1]]
    idx = pd.to_datetime((t[last] // NS_PER_DAY) * NS_PER_DAY, unit="ns")
    return pd.Series(closes / prev - 1.0, index=idx, name="buy_hold")


def exposure_matched_long(md: MarketData, result) -> pd.Series:
    t = result.eq_t
    c = result.m1_close
    r = np.zeros(len(c))
    r[1:] = c[1:] / c[:-1] - 1.0
    held = np.zeros(len(c), dtype=bool)
    held[1:] = result.in_pos[:-1]
    day = t // NS_PER_DAY
    s = pd.Series(r * held).groupby(day).sum()
    s.index = pd.to_datetime(s.index.to_numpy() * NS_PER_DAY, unit="ns")
    return s.rename("exposure_matched_long")


def buy_hold_volscaled(md: MarketData, start=None, end=None, costs: CostModel | None = None,
                       initial_equity: float = 10_000.0, account_units_per_usd: float = 1.0,
                       target_pct: float = 1.0, atr_period: int = 14, rebalance_band: float = 0.0,
                       rollover_from_min: int = 1425, rollover_to_min: int = 75,
                       max_spread_points: float = 60.0) -> dict:
    """Simulate BUY_HOLD_VOLSCALED. Returns {'daily_equity', 'daily_returns', 'fills', 'metrics'}."""
    from .engine import in_minute_window

    costs = costs or CostModel()
    spec = md.spec
    j0, j1 = _range_idx(md, start, end)
    t = md.t
    o, c = md.o, md.c
    spr = costs.effective_spread_points(md.spread) * spec.point
    slip = costs.slippage_points * spec.point
    vpl = spec.contract_size * account_units_per_usd
    half_comm = costs.commission_per_lot_rt / 2.0
    swap_long, _ = costs.swap_money_per_lot_night(spec, account_units_per_usd)
    triple = costs.triple_weekday_python(spec)
    d1 = md.bars("D1")
    atr = atr_mt5(d1["high"].to_numpy(float), d1["low"].to_numpy(float), d1["close"].to_numpy(float), atr_period)
    d1_close = d1["close_time_ns"].to_numpy("int64")

    tt = t[j0:j1]
    day = tt // NS_PER_DAY
    starts = np.flatnonzero(np.r_[True, day[1:] != day[:-1]]) + j0
    ends = np.r_[starts[1:], j1]
    equity, lots, mark = float(initial_equity), 0.0, None
    last_time = None
    fills, days_out, eq_out = [], [], []
    total_cost = total_swap = 0.0
    for a, b in zip(starts.tolist(), ends.tolist()):
        # rebalance bar: first bar of the day outside the rollover window with spread <= cap
        okm = ~in_minute_window(t[a:b], rollover_from_min, rollover_to_min)
        if max_spread_points and max_spread_points > 0:
            okm &= costs.effective_spread_points(md.spread[a:b]) <= max_spread_points
        ok = np.flatnonzero(okm)
        if len(ok):
            j = a + int(ok[0])
            if mark is not None:
                equity += lots * vpl * (o[j] - mark)
                if lots > 0 and swap_long != 0.0:
                    for _, mult in rollover_events(last_time, int(t[j]), triple):
                        sw = lots * swap_long * mult
                        equity += sw
                        total_swap += sw
            mark = o[j]
            last_time = int(t[j])
            k = int(last_closed_index(d1_close, t[j]))
            a_ = atr[k] if k >= 0 else np.nan
            target = 0.0
            if np.isfinite(a_) and a_ > 0 and equity > 0:
                raw = target_pct / 100.0 * equity / (a_ * vpl)
                target = floor_to_step(raw, spec.volume_step)  # round DOWN, like the strategies' sizing
                target = min(target, spec.volume_max)
                if target < spec.volume_min - 1e-12:
                    target = 0.0
            delta = round(target - lots, 8)
            band_ok = lots == 0 or abs(delta) / lots > rebalance_band
            if abs(delta) >= spec.volume_step - 1e-12 and band_ok:
                if delta > 0:
                    cost = delta * vpl * (spr[j] + slip)       # buy at ask + slip vs bid mark
                else:
                    cost = -delta * vpl * slip                   # sell at bid - slip
                cost += abs(delta) * half_comm
                equity -= cost
                total_cost += cost
                fills.append((pd.Timestamp(int(t[j]), unit="ns"), lots, target, delta, o[j], a_, equity, cost))
                lots = target
        # end-of-day mark at the last M1 close (bid)
        jl = b - 1
        if mark is not None:
            equity += lots * vpl * (c[jl] - mark)
            if lots > 0 and swap_long != 0.0 and last_time is not None:
                for _, mult in rollover_events(last_time, int(t[jl]), triple):
                    sw = lots * swap_long * mult
                    equity += sw
                    total_swap += sw
            mark = c[jl]
            last_time = int(t[jl])
        days_out.append((int(t[jl]) // NS_PER_DAY) * NS_PER_DAY)
        eq_out.append(equity)
    deq = pd.Series(eq_out, index=pd.to_datetime(np.array(days_out, dtype="int64"), unit="ns"), name="equity")
    prev = np.r_[initial_equity, deq.to_numpy()[:-1]]
    dret = pd.Series(deq.to_numpy() / prev - 1.0, index=deq.index, name="buy_hold_volscaled")
    fills_df = pd.DataFrame(fills, columns=["time", "lots_before", "lots_after", "delta", "bid", "atr_d1",
                                            "equity_after", "cost"])
    span = (int(tt[-1]) - int(tt[0])) / NS_PER_DAY
    met = {"name": "BUY_HOLD_VOLSCALED", "target_pct_per_atr": target_pct, "final_equity": float(deq.iloc[-1]),
           "total_return_pct": float(100 * (deq.iloc[-1] / initial_equity - 1)),
           "cagr": cagr(initial_equity, float(deq.iloc[-1]), span),
           "n_rebalances": int(len(fills_df)), "total_costs": float(total_cost), "total_swap": float(total_swap)}
    met.update(daily_return_stats(dret))
    dd = drawdown_stats(deq.to_numpy(), deq.index.as_unit("ns").asi8, initial_equity)
    met["max_dd_pct_daily"] = dd.get("max_dd_pct")
    return {"daily_equity": deq, "daily_returns": dret, "fills": fills_df, "metrics": met}


def regression_vs(strategy_ret: pd.Series, bench_ret: pd.Series, periods: int = 252) -> dict:
    """OLS strategy = alpha + beta * benchmark on common days."""
    df = pd.concat([strategy_ret.rename("s"), bench_ret.rename("b")], axis=1, join="inner").dropna()
    n = len(df)
    if n < 20 or df["b"].std() == 0 or df["s"].std() == 0:
        return {"n_days": n}
    x, y = df["b"].to_numpy(), df["s"].to_numpy()
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    beta = ((x - xm) * (y - ym)).sum() / sxx
    alpha = ym - beta * xm
    resid = y - alpha - beta * x
    s2 = (resid ** 2).sum() / (n - 2)
    se_a = np.sqrt(s2 * (1.0 / n + xm ** 2 / sxx))
    return {"n_days": int(n), "corr": float(np.corrcoef(x, y)[0, 1]), "beta": float(beta),
            "alpha_daily": float(alpha), "alpha_ann": float(alpha * periods),
            "alpha_t_stat": float(alpha / se_a) if se_a > 0 else float("nan")}


def benchmark_report(md: MarketData, result) -> dict:
    cfg = result.config
    start, end = result.stats["range_first_bar"], pd.Timestamp(result.stats["range_last_bar"]) + pd.Timedelta(minutes=1)
    out = {}
    bh = buy_and_hold_returns(md, start, end)
    s = daily_return_stats(bh)
    out["buy_hold"] = {"total_return_pct": float(100 * (np.prod(1 + bh.to_numpy()) - 1)),
                       "sharpe_ann": s.get("sharpe_ann"), "ann_vol": s.get("ann_vol")}
    em = exposure_matched_long(md, result)
    s = daily_return_stats(em)
    out["exposure_matched_long"] = {"total_return_pct": float(100 * (np.prod(1 + em.to_numpy()) - 1)),
                                    "sharpe_ann": s.get("sharpe_ann"),
                                    "exposure_pct": float(100 * result.in_pos.mean()) if len(result.in_pos) else 0.0}
    vs = buy_hold_volscaled(md, start, end, CostModel.from_dict(cfg["costs"]), cfg["initial_equity"],
                            cfg["account_units_per_usd"], rollover_from_min=cfg.get("rollover_from_min", 1425),
                            rollover_to_min=cfg.get("rollover_to_min", 75),
                            max_spread_points=cfg.get("max_spread_points", 60.0))
    out["buy_hold_volscaled"] = {k: vs["metrics"][k] for k in ("total_return_pct", "cagr", "sharpe_ann", "ann_vol",
                                                                 "max_dd_pct_daily", "total_costs", "total_swap",
                                                                 "n_rebalances") if k in vs["metrics"]}
    out["strategy_vs_buy_hold_volscaled"] = regression_vs(result.daily_returns(), vs["daily_returns"])
    return out
