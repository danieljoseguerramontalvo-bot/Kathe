"""Validation utilities.

* chronological splits and walk-forward windows (rolling / anchored; train and test never
  overlap), walk-forward optimisation with a stated objective and concatenated OOS trades;
* parameter-neighbourhood sensitivity tables;
* stationary block bootstrap (Politis & Romano 1994) of daily returns -> CIs of Sharpe/mean;
* Monte Carlo resampling of the trade sequence -> distribution of max drawdown / losing
  streak;
* Probabilistic and Deflated Sharpe Ratio (Bailey & Lopez de Prado 2012, 2014);
* Holm-Bonferroni step-down adjustment;
* monkey test (RANDOM_ENTRY) and the SESSION_BREAKOUT random-anchor control.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy import stats as sps

from .engine import BacktestConfig, run_backtest
from .metrics import compute_metrics, daily_return_stats, t_stat, trade_metrics
from .strategies import make_strategy

EULER_GAMMA = 0.5772156649015329


# ------------------------------------------------------------------------ splits
@dataclass(frozen=True)
class Split:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp          # exclusive


def chronological_split(start, end, cuts=None, fractions=None, names=None) -> list[Split]:
    """Split [start, end) chronologically, either at explicit ``cuts`` (dates) or by
    ``fractions`` of calendar time (e.g. (0.6, 0.2, 0.2))."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    if cuts is None:
        fr = np.asarray(fractions if fractions is not None else (0.6, 0.2, 0.2), dtype=float)
        if not np.isclose(fr.sum(), 1.0):
            raise ValueError("fractions must sum to 1")
        span = e - s
        cuts = [s + span * float(x) for x in np.cumsum(fr)[:-1]]
        cuts = [pd.Timestamp(c).normalize() for c in cuts]
    bounds = [s] + [pd.Timestamp(c) for c in cuts] + [e]
    if any(b2 <= b1 for b1, b2 in zip(bounds[:-1], bounds[1:])):
        raise ValueError("cuts must be strictly increasing inside (start, end)")
    names = names or (["train", "validation", "test"] if len(bounds) == 4 else [f"part{i}" for i in range(len(bounds) - 1)])
    return [Split(n, a, b) for n, a, b in zip(names, bounds[:-1], bounds[1:])]


@dataclass(frozen=True)
class WFWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp    # exclusive; == test_start
    test_start: pd.Timestamp
    test_end: pd.Timestamp     # exclusive


def walk_forward_windows(start, end, train_months: int, test_months: int, step_months: int | None = None,
                         anchored: bool = False) -> list[WFWindow]:
    """Rolling (fixed-length train) or anchored (train always starts at ``start``) windows.
    Test windows are consecutive, non-overlapping, and each train window ends exactly where
    its test window starts."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    step = step_months or test_months
    out = []
    k = 0
    while True:
        test_start = s + pd.DateOffset(months=train_months + k * step)
        test_end = test_start + pd.DateOffset(months=test_months)
        if test_end > e:
            break
        train_start = s if anchored else test_start - pd.DateOffset(months=train_months)
        out.append(WFWindow(train_start, test_start, test_start, test_end))
        k += 1
    return out


OBJECTIVES = {
    "t_stat_r": lambda m: m.get("t_stat_r", np.nan),
    "expectancy_r": lambda m: m.get("expectancy_r", np.nan),
    "sharpe": lambda m: m.get("sharpe_ann", np.nan),
    "profit_factor": lambda m: m.get("profit_factor", np.nan),
    "net_profit": lambda m: m.get("net_profit", np.nan),
}


def _grid(param_grid: dict) -> list[dict]:
    keys = list(param_grid)
    return [dict(zip(keys, v)) for v in itertools.product(*[param_grid[k] for k in keys])] if keys else [{}]


def _run(md, name, params, cfg, start, end):
    res = run_backtest(md, make_strategy(name, params), replace(cfg, start=start, end=end))
    return res, compute_metrics(res, benchmarks=False)


def walk_forward(md, strategy_name: str, param_grid: dict, cfg: BacktestConfig, windows: list[WFWindow],
                 base_params: dict | None = None, objective: str = "t_stat_r", min_trades: int = 20) -> dict:
    """Walk-forward optimisation.

    For each window, every combination of ``param_grid`` (merged over ``base_params``) is run
    on the TRAIN range; the combination with the best ``objective`` among those with at least
    ``min_trades`` trades is selected (ties -> first in grid order; none eligible -> the
    window is skipped) and run once on the TEST range. OOS trades are concatenated; OOS
    daily returns are chained. Default objective: t-stat of the mean R.
    """
    base = dict(base_params or {})
    obj = OBJECTIVES[objective] if isinstance(objective, str) else objective
    rows, oos_trades, oos_daily = [], [], []
    combos = _grid(param_grid)
    for w_id, w in enumerate(windows):
        if not (w.train_end <= w.test_start):
            raise ValueError("train and test overlap")
        best, best_score, train_m = None, -np.inf, None
        for combo in combos:
            _, m = _run(md, strategy_name, {**base, **combo}, cfg, w.train_start, w.train_end)
            sc = obj(m) if m.get("n_trades", 0) >= min_trades else np.nan
            if np.isfinite(sc) and sc > best_score:
                best, best_score, train_m = combo, sc, m
        row = {"window": w_id, "train_start": w.train_start, "train_end": w.train_end,
               "test_start": w.test_start, "test_end": w.test_end, "chosen": best,
               "train_score": best_score if best is not None else np.nan,
               "train_n_trades": train_m.get("n_trades") if train_m else 0}
        if best is not None:
            res, m = _run(md, strategy_name, {**base, **best}, cfg, w.test_start, w.test_end)
            tr = res.trades.copy()
            tr["wf_window"] = w_id
            oos_trades.append(tr)
            oos_daily.append(res.daily_returns())
            row.update({"test_n_trades": m.get("n_trades", 0), "test_expectancy_r": m.get("expectancy_r"),
                        "test_t_stat_r": m.get("t_stat_r"), "test_net_profit": m.get("net_profit", 0.0),
                        "test_sharpe": m.get("sharpe_ann")})
        rows.append(row)
    trades = pd.concat(oos_trades, ignore_index=True) if oos_trades else pd.DataFrame()
    daily = pd.concat(oos_daily) if oos_daily else pd.Series(dtype=float)
    summary = trade_metrics(trades) if len(trades) else {"n_trades": 0}
    summary.update(daily_return_stats(daily))
    summary["oos_compounded_return_pct"] = float(100 * (np.prod(1 + daily.to_numpy()) - 1)) if len(daily) else 0.0
    return {"windows": pd.DataFrame(rows), "oos_trades": trades, "oos_daily_returns": daily,
            "oos_metrics": summary, "objective": objective if isinstance(objective, str) else repr(objective),
            "n_combinations": len(combos), "min_trades": min_trades}


def param_neighbourhood(md, strategy_name: str, base_params: dict, grid: dict, cfg: BacktestConfig,
                        mode: str = "one_at_a_time",
                        columns=("n_trades", "expectancy_r", "t_stat_r", "profit_factor", "sharpe_ann",
                                 "max_dd_pct", "net_profit")) -> pd.DataFrame:
    """Sensitivity table. ``mode='one_at_a_time'`` varies each parameter over its grid values
    with the others at ``base_params``; ``mode='grid'`` runs the full product."""
    if mode == "grid":
        combos = _grid(grid)
    elif mode == "one_at_a_time":
        combos = [{}] + [{k: v} for k, vals in grid.items() for v in vals if base_params.get(k) != v]
    else:
        raise ValueError("mode must be 'one_at_a_time' or 'grid'")
    rows = []
    for combo in combos:
        params = {**base_params, **combo}
        _, m = _run(md, strategy_name, params, cfg, cfg.start, cfg.end)
        row = {f"param.{k}": params.get(k) for k in grid}
        row["is_base"] = all(params.get(k) == base_params.get(k) for k in grid)
        row.update({c: m.get(c, np.nan) for c in columns})
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ bootstrap / MC
def stationary_bootstrap_indices(n: int, n_boot: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap: blocks start at uniform random positions, have
    geometric lengths with mean ``mean_block`` and wrap around circularly. Returns (n_boot, n)."""
    p = 1.0 / float(mean_block)
    starts = rng.integers(0, n, size=(n_boot, n))
    new_block = rng.random((n_boot, n)) < p
    new_block[:, 0] = True
    pos = np.arange(n)[None, :]
    last_start = np.maximum.accumulate(np.where(new_block, pos, 0), axis=1)
    start_val = np.take_along_axis(starts, last_start, axis=1)
    return (start_val + (pos - last_start)) % n


def _sharpe(x, axis=-1, periods=252):
    sd = x.std(axis=axis, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return x.mean(axis=axis) / sd * np.sqrt(periods)


def bootstrap_ci(returns, stat: str = "sharpe", n_boot: int = 2000, mean_block: float = 10.0,
                 alpha: float = 0.05, seed: int = 0) -> dict:
    """Stationary-bootstrap CI of the annualised Sharpe ('sharpe') or mean daily return
    ('mean'). ``prob_le_0`` = share of bootstrap statistics <= 0 (a rough one-sided p)."""
    x = np.asarray(returns, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 10:
        return {"n": n}
    rng = np.random.default_rng(seed)
    idx = stationary_bootstrap_indices(n, n_boot, mean_block, rng)
    sample = x[idx]
    if stat == "sharpe":
        point, dist = float(_sharpe(x)), _sharpe(sample, axis=1)
    elif stat == "mean":
        point, dist = float(x.mean()), sample.mean(axis=1)
    else:
        raise ValueError("stat must be 'sharpe' or 'mean'")
    dist = dist[np.isfinite(dist)]
    lo, hi = np.quantile(dist, [alpha / 2, 1 - alpha / 2])
    return {"stat": stat, "n": n, "point": point, "ci_low": float(lo), "ci_high": float(hi),
            "se": float(dist.std(ddof=1)), "prob_le_0": float((dist <= 0).mean()),
            "n_boot": n_boot, "mean_block": mean_block, "alpha": alpha}


def monte_carlo_trades(r_values, n_sims: int = 5000, risk_fraction: float = 0.01, method: str = "shuffle",
                       seed: int = 0, quantiles=(0.05, 0.5, 0.95, 0.99)) -> dict:
    """Resample the sequence of trade R-multiples (``shuffle`` = permutation, ``bootstrap`` =
    with replacement) and compound at ``risk_fraction`` of equity per trade:
    equity *= 1 + risk_fraction * R. Returns quantiles of max drawdown (%), max drawdown in R
    (additive curve) and the longest losing streak, plus the observed values and their
    percentile in the simulated distribution."""
    r = np.asarray(r_values, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 2:
        return {"n_trades": n}
    rng = np.random.default_rng(seed)
    if method == "shuffle":
        sims = np.array([rng.permutation(r) for _ in range(n_sims)])
    elif method == "bootstrap":
        sims = r[rng.integers(0, n, size=(n_sims, n))]
    else:
        raise ValueError("method must be 'shuffle' or 'bootstrap'")

    def dd_stats(mat):
        eq = np.cumprod(1 + risk_fraction * mat, axis=1)
        eq = np.concatenate([np.ones((mat.shape[0], 1)), eq], axis=1)
        dd_pct = 100 * (1 - eq / np.maximum.accumulate(eq, axis=1)).max(axis=1)
        cum = np.concatenate([np.zeros((mat.shape[0], 1)), np.cumsum(mat, axis=1)], axis=1)
        dd_r = (np.maximum.accumulate(cum, axis=1) - cum).max(axis=1)
        streak = np.zeros(mat.shape[0])
        cur = np.zeros(mat.shape[0])
        for k in range(mat.shape[1]):
            cur = np.where(mat[:, k] < 0, cur + 1, 0)
            streak = np.maximum(streak, cur)
        return dd_pct, dd_r, streak

    dd_pct, dd_r, streak = dd_stats(sims)
    o_pct, o_r, o_s = (v[0] for v in dd_stats(r[None, :]))
    q = {f"q{int(qq * 100)}": qq for qq in quantiles}
    return {
        "n_trades": n, "n_sims": n_sims, "method": method, "risk_fraction": risk_fraction,
        "max_dd_pct": {k: float(np.quantile(dd_pct, v)) for k, v in q.items()},
        "max_dd_r": {k: float(np.quantile(dd_r, v)) for k, v in q.items()},
        "longest_losing_streak": {k: float(np.quantile(streak, v)) for k, v in q.items()},
        "observed": {"max_dd_pct": float(o_pct), "max_dd_r": float(o_r), "longest_losing_streak": int(o_s)},
        "observed_percentile": {"max_dd_pct": float((dd_pct <= o_pct).mean()),
                                "longest_losing_streak": float((streak <= o_s).mean())},
    }


# ------------------------------------------------------------------------ Sharpe inference
def probabilistic_sharpe_ratio(sr: float, sr_benchmark: float, n_obs: int, skew: float, kurt: float) -> float:
    """PSR = Phi((SR - SR*) sqrt(T-1) / sqrt(1 - g3 SR + (g4 - 1)/4 SR^2)); per-period SRs,
    ``kurt`` is the raw (non-excess) kurtosis."""
    den = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if den <= 0 or n_obs < 2:
        return float("nan")
    return float(sps.norm.cdf((sr - sr_benchmark) * np.sqrt(n_obs - 1) / np.sqrt(den)))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """E[max SR] of N independent trials with true SR 0 (Bailey & Lopez de Prado 2014)."""
    if n_trials <= 1:
        return 0.0
    g = EULER_GAMMA
    return float(np.sqrt(sr_variance) * ((1 - g) * sps.norm.ppf(1 - 1.0 / n_trials)
                                         + g * sps.norm.ppf(1 - 1.0 / (n_trials * np.e))))


def deflated_sharpe_ratio(returns=None, n_trials: int = 1, sr: float | None = None, n_obs: int | None = None,
                          skew: float | None = None, kurt: float | None = None,
                          sr_variance_trials: float | None = None, periods: int = 252) -> dict:
    """Deflated Sharpe Ratio = PSR evaluated at SR* = E[max SR over n_trials].

    All Sharpe ratios are PER PERIOD (daily). ``sr_variance_trials`` = variance of the
    per-period Sharpe ratios across the trials; if unknown, the sampling variance of the SR
    estimator, (1 - g3 SR + (g4-1)/4 SR^2) / (T-1), is used (i.e. all trials assumed
    noise-only). Returns DSR (probability that the true SR > 0 after deflation)."""
    if returns is not None:
        x = np.asarray(returns, dtype=float)
        x = x[np.isfinite(x)]
        n_obs = len(x)
        sd = x.std(ddof=1)
        sr = x.mean() / sd if sd > 0 else 0.0
        skew = float(sps.skew(x)) if sd > 0 else 0.0
        kurt = float(sps.kurtosis(x, fisher=False)) if sd > 0 else 3.0
    if sr is None or n_obs is None:
        raise ValueError("give returns or (sr, n_obs)")
    skew = 0.0 if skew is None else skew
    kurt = 3.0 if kurt is None else kurt
    if sr_variance_trials is None:
        sr_variance_trials = (1 - skew * sr + (kurt - 1) / 4 * sr ** 2) / max(n_obs - 1, 1)
    sr_star = expected_max_sharpe(int(n_trials), sr_variance_trials)
    return {"dsr": probabilistic_sharpe_ratio(sr, sr_star, n_obs, skew, kurt),
            "psr_vs_0": probabilistic_sharpe_ratio(sr, 0.0, n_obs, skew, kurt),
            "sr_per_period": float(sr), "sr_annualised": float(sr * np.sqrt(periods)),
            "sr_star_per_period": sr_star, "sr_star_annualised": float(sr_star * np.sqrt(periods)),
            "n_trials": int(n_trials), "n_obs": int(n_obs), "skew": float(skew), "kurtosis": float(kurt)}


def holm_bonferroni(p_values, alpha: float = 0.05) -> dict:
    """Holm step-down adjusted p-values (original order) and rejections at ``alpha``."""
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    order = np.argsort(p, kind="stable")
    adj_sorted = np.minimum(1.0, np.maximum.accumulate((m - np.arange(m)) * p[order]))
    adj = np.empty(m)
    adj[order] = adj_sorted
    return {"p_adjusted": adj, "reject": adj <= alpha, "alpha": alpha, "m": m}


# ------------------------------------------------------------------------ controls
def calibrate_random_entry(md, target: str, target_params: dict | None, cfg: BacktestConfig) -> dict:
    """Run the target once and return p_entry = entries / flat eligible decisions."""
    res = run_backtest(md, make_strategy(target, target_params), cfg)
    st = res.stats["strategy_stats"]
    elig = max(int(st.get("flat_eligible_decisions", 0)), 1)
    return {"p_entry": float(st.get("entries_emitted", 0)) / elig, "target_result": res,
            "target_entries": int(st.get("entries_emitted", 0)), "flat_eligible_decisions": elig}


def monkey_test(md, target: str, target_params: dict | None, cfg: BacktestConfig, n_runs: int = 100,
                seed: int = 0, metric: str = "expectancy_r", use_target_exits: bool = True) -> dict:
    """Compare the target with ``n_runs`` RANDOM_ENTRY runs (same exits, same frequency)."""
    cal = calibrate_random_entry(md, target, target_params, cfg)
    real = compute_metrics(cal["target_result"], benchmarks=False)
    vals = []
    for k in range(n_runs):
        s = make_strategy("RANDOM_ENTRY", {"target": target, "target_params": dict(target_params or {}),
                                           "p_entry": cal["p_entry"], "seed": seed + k,
                                           "use_target_exits": use_target_exits})
        m = compute_metrics(run_backtest(md, s, cfg), benchmarks=False)
        vals.append(m.get(metric, np.nan))
    return _control_summary(real.get(metric, np.nan), np.asarray(vals, float), metric,
                            {"p_entry": cal["p_entry"], "real_n_trades": real.get("n_trades", 0)})


def breakout_anchor_control(md, params: dict | None, cfg: BacktestConfig, n_seeds: int = 100, seed: int = 0,
                            metric: str = "expectancy_r", unconditional: bool = False) -> dict:
    """SESSION_BREAKOUT random-anchor control: the real strategy vs ``n_seeds`` runs whose
    range window is a random window of the same length (``anchor_mode='random'``).
    ``unconditional=True`` switches the compression filter off in both (c_max=None)."""
    base = dict(params or {})
    base.pop("anchor_mode", None)
    base.pop("anchor_seed", None)
    if unconditional:
        base["c_max"] = None
    real = compute_metrics(run_backtest(md, make_strategy("SESSION_BREAKOUT", {**base, "anchor_mode": "fixed"}), cfg),
                           benchmarks=False)
    vals, ntr = [], []
    for k in range(n_seeds):
        s = make_strategy("SESSION_BREAKOUT", {**base, "anchor_mode": "random", "anchor_seed": seed + k})
        m = compute_metrics(run_backtest(md, s, cfg), benchmarks=False)
        vals.append(m.get(metric, np.nan))
        ntr.append(m.get("n_trades", 0))
    out = _control_summary(real.get(metric, np.nan), np.asarray(vals, float), metric,
                           {"variant": "unconditional" if unconditional else "conditional",
                            "real_n_trades": real.get("n_trades", 0),
                            "random_n_trades_median": float(np.median(ntr)) if ntr else 0.0})
    return out


def _control_summary(real_value: float, dist: np.ndarray, metric: str, extra: dict) -> dict:
    d = dist[np.isfinite(dist)]
    out = {"metric": metric, "real": float(real_value), "n_random": int(len(d)), "random_values": d.tolist()}
    if len(d):
        out.update({"random_mean": float(d.mean()), "random_p05": float(np.quantile(d, 0.05)),
                    "random_p50": float(np.quantile(d, 0.5)), "random_p95": float(np.quantile(d, 0.95)),
                    "real_percentile": float((d < real_value).mean() + 0.5 * (d == real_value).mean()),
                    "p_value": float((1 + (d >= real_value).sum()) / (1 + len(d))),
                    "real_above_p95": bool(real_value > np.quantile(d, 0.95))})
    out.update(extra)
    return out


__all__ = ["Split", "chronological_split", "WFWindow", "walk_forward_windows", "walk_forward",
           "param_neighbourhood", "stationary_bootstrap_indices", "bootstrap_ci", "monte_carlo_trades",
           "probabilistic_sharpe_ratio", "expected_max_sharpe", "deflated_sharpe_ratio", "holm_bonferroni",
           "calibrate_random_entry", "monkey_test", "breakout_anchor_control", "t_stat"]
