"""Ejecutor del protocolo prerregistrado v5 (``MQL5/docs/PROTOCOLO_V5.md``, enmiendas 1, 2 y 3).

Se escribe y se sube al repositorio ANTES de ver ningún dato real, para que la selección no pueda
adaptarse a los resultados. Dos etapas:

``devval``  walk-forward sobre DEV + VAL de cada familia (H3a, H2, H1, H4), H3b exploratoria,
            controles (prueba del mono, anclas aleatorias de H2), estudios adicionales si alguna
            familia sobrevive, criterios a-k, selección y congelado de como mucho 3 candidatas.
            Los datos se recortan al final de VAL: la reserva final no se carga.
``holdout`` una sola ejecución por candidata congelada sobre HOLD. Queda anotada en el registro
            encadenado (``record_type = holdout_lock``) ANTES de calcularse; una segunda ejecución de
            la misma candidata se rechaza salvo con ``--contaminated-rerun``, y entonces se marca como
            contaminada y no puede aprobar.

Costes definidos en USD por onza (precio), no en puntos, y convertidos con ``spec.point``: así
valen igual para símbolos de 2 o 3 decimales.

Uso:
    python -m kq.protocol devval  --scenario A --data KQ_XAUUSD_M1.csv --spec KQ_XAUUSD_spec.json --out runs/protoA
    python -m kq.protocol holdout --scenario A --data KQ_XAUUSD_M1.csv --spec KQ_XAUUSD_spec.json \
        --frozen runs/protoA/frozen_candidates.json --out runs/protoA_hold
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import multiprocessing as mp
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark import buy_and_hold_returns, buy_hold_volscaled
from .costs import CostModel, commission_rt_from_spec
from .data import MarketData, daily_break_check, file_sha256
from .engine import BacktestConfig, run_backtest
from .metrics import cost_stress, daily_return_stats, t_stat, trade_metrics
from .registry import DEFAULT_REGISTRY as REGISTRY_PATH
from .registry import (append_experiment, config_key, distinct_config_keys, git_info, git_uncommitted, head_path,
                       read_registry, sanitize, verify_registry)
from .strategies import make_strategy, scan_session_windows
from .validation import (calibrate_random_entry, deflated_sharpe_ratio, holm_bonferroni, monte_carlo_trades,
                         walk_forward, walk_forward_windows)

PROTOCOL_VERSION = "v5 + enmiendas 1, 2 y 3 (2026-09-29)"

# ---------------------------------------------------------------- cortes (fin EXCLUSIVO, hora del servidor)
SCENARIOS = {
    "A": {"wf_start": "2022-01-01", "dev": ("2022-01-03", "2024-07-01"), "val": ("2024-07-01", "2025-07-01"),
          "hold_start": "2025-07-01", "train_months": 18, "test_months": 6, "min_oos_trades": 100},
    "B": {"wf_start": "2008-01-01", "dev": ("2008-01-01", "2017-01-01"), "val": ("2017-01-01", "2022-01-01"),
          "hold_start": "2022-01-01", "train_months": 48, "test_months": 12, "min_oos_trades": 200},
}

# Configuraciones distintas ya probadas en la fase v4 (familias EMA/RSI): F7, F0, T0-M15, T1-M15,
# F0-H4, T0-H4, T1-H4 y T0-H1. Cuentan en el Deflated Sharpe (enmienda 2).
PRIOR_TRIALS = 8
BUDGET_CANDIDATES = 14
BUDGET_EXTRAS = 6
MIN_TRAIN_TRADES = 30
MIN_NEIGHBOUR_TRADES = 10

RSI2_BASE = {"ema_period": 200, "rsi_period": 2, "buy_level": 10.0, "sell_level": 90.0, "exit_long": 70.0,
             "exit_short": 30.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 6.0, "adx_filter": False,
             "htf_filter": False, "trail_atr": 0.0}
RANGE_GATE = {"allow_regime": "range", "er_period": 20, "er_threshold": 0.3}

# El orden de cada rejilla va de lo más simple a lo más complejo: los empates los gana la primera.
FAMILIES = {
    "H3a": {"strategy": "SESSION_DRIFT", "title": "Deriva de la sesión asiática (compra 00-08 UTC)",
            "base": {"h_in": 0, "h_out": 8, "side": 1, "sl_atr": 3.0, "atr_period": 14}, "grid": {},
            "neighbours": {"h_in": [23, 1], "h_out": [7, 9], "sl_atr": [2.0, 4.0]},
            "direction_rule": "vs_volscaled", "regime_extras": [{"allow_regime": "trend"}, {"allow_vol": [1, 2]}],
            "n_components": 1},
    "H2": {"strategy": "SESSION_BREAKOUT", "title": "Ruptura del rango asiático tras compresión",
           "base": {"buffer_frac": 0.1}, "grid": {"c_max": [None, 0.4], "tp_mult": [1.0, 2.0]},
           "direction_rule": "short_or_volscaled",
           "regime_extras": [{"allow_regime": "trend"}, {"allow_vol": [1, 2]}], "n_components": 2},
    "H1": {"strategy": "TREND_DONCHIAN", "title": "Tendencia Donchian con chandelier",
           "base": {"k_sl": 2.0, "k_trail": 3.0, "atr_period": 14}, "grid": {"timeframe": ["H4", "D1"], "n": [20, 55]},
           "direction_rule": "vs_volscaled",
           "regime_extras": [{"allow_regime": "trend"}, {"allow_vol": [1, 2]}], "n_components": 2},
    "H4": {"strategy": "REF_RSI2", "title": "RSI(2) condicionado al régimen",
           "base": dict(RSI2_BASE), "grid": {"timeframe": ["H1", "H4"], "regime_gate": [None, RANGE_GATE]},
           "direction_rule": "short_or_volscaled",
           "regime_extras": [{"allow_vol": [0, 1]}, {"allow_regime": "range", "allow_vol": [0, 1]}],
           "n_components": 2},
}
PRIORITY = {"A": ["H3a", "H2", "H1", "H4"], "B": ["H1", "H3a", "H2", "H4"]}

# Referencias con resultado conocido en el probador de MT5 (XAUUSD HFM, 2022-01-01 -> 2024-12-31)
PARITY = {
    "B1_REF_T0_H4": {"strategy": "REF_T0", "params": {}, "mt5": {"n_trades": 100, "profit_factor": 1.21}},
    "B2_REF_RSI2_F0_H4": {"strategy": "REF_RSI2", "params": {**RSI2_BASE, "timeframe": "H4"},
                          "mt5": {"n_trades": 230, "profit_factor": 0.96}},
}

# Costes del protocolo (apartado 2 y enmienda 2), en USD por onza de precio
SLIPPAGE_USD = 0.03           # deslizamiento adverso por ejecución
MAX_SPREAD_USD = 0.60         # tope de spread para entrar (regla común motor/EA)
PARITY_MAX_SPREAD_USD = 0.80  # el de la v4 (InpMaxSpreadPips = 8)
STRESS_USD = (0.10, 0.20, 0.40)
FILTER_COST_USD = 0.10        # coste con el que se compara la mejora del filtro de compresión (H2)
STOP_RATIO_RANGE = (0.8, 1.25)  # distancia de stop mediana aleatoria / real admisible en la prueba del mono


# ---------------------------------------------------------------- utilidades
def _ts(x) -> pd.Timestamp:
    return pd.Timestamp(x)


def _params_key(strategy: str, params: dict) -> str:
    return config_key(strategy, params)


def usd_to_points(usd: float, spec) -> float:
    return round(float(usd) / float(spec.point), 9)   # 0.29 / 0.01 = 28.999999999999996 -> 29.0


def _describe(params: dict) -> str:
    parts = []
    for k, v in params.items():
        if isinstance(v, dict):
            v = "{" + ",".join(f"{a}={b}" for a, b in v.items()) + "}"
        parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else "(fija)"


def _grid(grid: dict) -> list[dict]:
    import itertools
    keys = list(grid)
    return [dict(zip(keys, v)) for v in itertools.product(*[grid[k] for k in keys])] if keys else [{}]


def _with_gate(params: dict, extra_gate: dict | None) -> dict:
    """Añade o combina un filtro de régimen con el que ya tenga la configuración."""
    p = dict(params)
    if extra_gate:
        g = dict(p.get("regime_gate") or {})
        g.update(extra_gate)
        p["regime_gate"] = g
    return p


_MD = None  # MarketData compartido con los procesos hijos (fork)


def _run_expectancy(job):
    """(esperanza en R, operaciones, distancia de stop mediana en precio)."""
    name, params, cfg = job
    res = run_backtest(_MD, make_strategy(name, params), cfg)
    tm = trade_metrics(res.trades)
    rp = float(np.median(res.trades["r_price"].to_numpy(float))) if len(res.trades) else float("nan")
    return float(tm.get("expectancy_r", np.nan)), int(tm.get("n_trades", 0)), rp


def _pmap(md, jobs, workers: int):
    global _MD
    _MD = md
    if workers <= 1 or len(jobs) < 4:
        return [_run_expectancy(j) for j in jobs]
    try:
        ctx = mp.get_context("fork")
    except ValueError:
        return [_run_expectancy(j) for j in jobs]
    with ctx.Pool(workers) as pool:
        return pool.map(_run_expectancy, jobs, chunksize=max(1, len(jobs) // (workers * 8)))


def _control(real_wf: float, real_static: float, real_stop: float, vals: list[tuple], label: str,
             check_stop_ratio: bool = True) -> dict:
    """Compara la esperanza real con la distribución de ejecuciones aleatorias.

    ``real_wf`` = esperanza del walk-forward concatenado; ``real_static`` = la de la configuración
    modal ejecutada sobre el mismo periodo que las aleatorias (comparación homogénea). Se exige
    que AMBAS superen el percentil 95. Con ``check_stop_ratio`` el control solo es válido si la
    distancia de stop mediana de las aleatorias está entre 0.8 y 1.25 veces la real (si no, los
    costes pesan distinto en R y la comparación está sesgada)."""
    d = np.array([v[0] for v in vals], dtype=float)
    ok = np.isfinite(d)
    d = d[ok]
    if len(d) == 0:
        raise RuntimeError(f"{label}: ninguna ejecución aleatoria produjo operaciones; el control no es válido")
    stops = np.array([v[2] for v in vals], dtype=float)
    rand_stop = float(np.nanmedian(stops)) if np.isfinite(stops).any() else float("nan")
    ratio = rand_stop / real_stop if np.isfinite(real_stop) and real_stop > 0 else float("nan")
    valid = (not check_stop_ratio) or bool(np.isfinite(ratio) and STOP_RATIO_RANGE[0] <= ratio <= STOP_RATIO_RANGE[1])
    p95 = float(np.quantile(d, 0.95))
    out = {"control": label, "real_expectancy_r": real_wf, "real_static_expectancy_r": real_static,
           "n_random": int(len(d)), "random_mean": float(d.mean()), "random_p50": float(np.median(d)),
           "random_p95": p95, "p_value": float((1 + (d >= real_wf).sum()) / (1 + len(d))),
           "random_median_trades": float(np.median([v[1] for v in vals])),
           "real_median_stop": real_stop, "random_median_stop": rand_stop, "stop_ratio": ratio,
           "stop_ratio_checked": check_stop_ratio, "valid": valid}
    out["beats_p95"] = bool(valid and np.isfinite(real_wf) and real_wf > p95
                            and np.isfinite(real_static) and real_static > p95)
    return out


def _chained_equity(results) -> np.ndarray:
    """Encadena la equidad M1 de varias ventanas de prueba (cada una empieza con el capital inicial)."""
    parts, level = [np.array([1.0])], 1.0
    for res in results:
        if len(res.equity) == 0:
            continue
        rel = np.asarray(res.equity, float) / res.initial_equity
        parts.append(level * rel)
        level *= rel[-1]
    return np.concatenate(parts)


def _max_dd_pct(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(eq)
    return float(100.0 * (1.0 - eq / peak).max())


def _int0(v) -> int:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if np.isfinite(f) else 0


def _num(v, default=float("nan")) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if np.isfinite(f) else default


def _semester(ts: pd.Series) -> pd.Series:
    return ts.dt.year.astype(str) + np.where(ts.dt.month <= 6, "-S1", "-S2")


# ---------------------------------------------------------------- evaluación fuera de muestra
def evaluate_oos(trades: pd.DataFrame, daily: pd.Series, chained_eq: np.ndarray, md: MarketData, cfg: BacktestConfig,
                 scen: dict, n_trials: int, bench_sharpe: float, direction_rule: str,
                 neighbours: list[dict] | None, monkey: dict | None, seed: int = 0) -> dict:
    """Métricas y criterios a-k del apartado 5 sobre las operaciones fuera de muestra."""
    tm = trade_metrics(trades) if len(trades) else {"n_trades": 0}
    ds = daily_return_stats(daily) if len(daily) else {}
    out = {"metrics": {**tm, **ds}}
    n = int(tm.get("n_trades", 0))
    crit = {}
    crit["a"] = {"desc": f"operaciones >= {scen['min_oos_trades']}", "value": n, "pass": n >= scen["min_oos_trades"]}
    if n == 0:
        for k in "bcdefghijk":
            crit[k] = {"desc": "sin operaciones", "value": None, "pass": False}
        out["criteria"] = crit
        out["defensible"] = False
        return out

    r = trades["r_net"].to_numpy(float)
    exp_r, t_r = float(np.nanmean(r)), t_stat(r)
    crit["b"] = {"desc": "esperanza R > 0 y t >= 2.0", "value": {"expectancy_r": exp_r, "t": t_r},
                 "pass": bool(exp_r > 0 and np.isfinite(t_r) and t_r >= 2.0)}

    dsr = deflated_sharpe_ratio(daily.to_numpy(float), n_trials=n_trials) if len(daily) > 10 else {"dsr": float("nan")}
    out["dsr"] = dsr
    crit["c"] = {"desc": f"Deflated Sharpe >= 0.95 (N = {n_trials})", "value": dsr.get("dsr"),
                 "pass": bool(np.isfinite(dsr.get("dsr", np.nan)) and dsr["dsr"] >= 0.95)}

    pf = tm.get("profit_factor", float("nan"))
    crit["d"] = {"desc": "factor de beneficio >= 1.20", "value": pf, "pass": bool(np.isfinite(pf) and pf >= 1.20)}

    point = float(md.spec.point)
    vpl = float(md.spec.contract_size) * float(cfg.account_units_per_usd)
    pts = [usd / point for usd in STRESS_USD]
    raw = cost_stress(trades, point, vpl, pts)
    stress = {f"+{usd:.2f} USD": v for usd, v in zip(STRESS_USD, raw.values())}
    out["cost_stress"] = stress
    e20 = stress.get("+0.20 USD", {}).get("expectancy_r", float("nan"))
    crit["e"] = {"desc": "esperanza R con +0.20 USD por operación > 0", "value": e20,
                 "pass": bool(np.isfinite(e20) and e20 > 0)}

    dd = _max_dd_pct(chained_eq)
    mc = monte_carlo_trades(r, n_sims=5000, risk_fraction=0.01, method="shuffle", seed=seed)
    out["monte_carlo"] = mc
    mc95 = mc.get("max_dd_pct", {}).get("q95", float("nan"))
    crit["f"] = {"desc": "drawdown <= 20 % y percentil 95 de Monte Carlo <= 30 %", "value": {"dd": dd, "mc_q95": mc95},
                 "pass": bool(dd <= 20.0 and np.isfinite(mc95) and mc95 <= 30.0)}

    tr = trades.copy()
    tr["sem"] = _semester(tr["exit_time"])
    by_sem = tr.groupby("sem")["r_net"].sum()
    by_year = tr.groupby(tr["exit_time"].dt.year)["r_net"].sum()
    total_r = float(np.nansum(r))
    pos_share = float((by_sem > 0).mean()) if len(by_sem) else 0.0
    max_year_share = float(by_year.max() / total_r) if total_r > 0 else float("nan")
    out["by_semester_r"] = {str(k): float(v) for k, v in by_sem.items()}
    out["by_year_r"] = {str(k): float(v) for k, v in by_year.items()}
    crit["g"] = {"desc": ">= 60 % de semestres positivos y ningún año > 50 % del beneficio (en R)",
                 "value": {"semesters_positive": pos_share, "max_year_share": max_year_share},
                 "pass": bool(pos_share >= 0.60 and np.isfinite(max_year_share) and max_year_share <= 0.50)}

    top5_tr = float(np.sort(r)[::-1][:5].sum() / total_r) if total_r > 0 else float("nan")
    by_day = tr.groupby(tr["exit_time"].dt.normalize())["r_net"].sum().to_numpy(float)
    top5_day = float(np.sort(by_day)[::-1][:5].sum() / total_r) if total_r > 0 else float("nan")
    crit["h"] = {"desc": "5 mejores operaciones <= 30 % y 5 mejores días <= 35 % del beneficio (en R)",
                 "value": {"top5_trades": top5_tr, "top5_days": top5_day},
                 "pass": bool(np.isfinite(top5_tr) and top5_tr <= 0.30 and np.isfinite(top5_day) and top5_day <= 0.35)}

    if neighbours is None:
        crit["i"] = {"desc": "vecindario", "value": "no evaluado", "pass": False}
    else:
        counted = [nb for nb in neighbours if nb["n_trades"] >= MIN_NEIGHBOUR_TRADES]
        ok = bool(counted) and all(np.isfinite(nb["expectancy_r"]) and nb["expectancy_r"] > 0 for nb in counted)
        crit["i"] = {"desc": f"todas las vecinas (>= {MIN_NEIGHBOUR_TRADES} operaciones) con esperanza > 0",
                     "value": [{k: nb[k] for k in ("config", "n_trades", "expectancy_r")} for nb in neighbours],
                     "pass": ok}

    sharpe = ds.get("sharpe_ann", float("nan"))
    long_mask = trades["side"].to_numpy() > 0
    short_net = float(trades.loc[~long_mask, "net_pnl"].sum()) if (~long_mask).any() else None
    beats_bh = bool(np.isfinite(sharpe) and np.isfinite(bench_sharpe) and sharpe > bench_sharpe)
    if direction_rule == "vs_volscaled":
        ok_j = beats_bh
        desc_j = "Sharpe fuera de muestra > comprar y mantener escalado por volatilidad"
    else:
        ok_j = bool((short_net is not None and short_net >= 0) or beats_bh)
        desc_j = "ventas con resultado >= 0, o Sharpe > comprar y mantener escalado por volatilidad"
    crit["j"] = {"desc": desc_j, "value": {"sharpe": sharpe, "bh_volscaled_sharpe": bench_sharpe,
                                           "short_net_profit": short_net}, "pass": ok_j}

    if monkey is None:
        crit["k"] = {"desc": "prueba del mono", "value": "no evaluada", "pass": False}
    else:
        crit["k"] = {"desc": "esperanza (walk-forward y configuración modal) > percentil 95 de entradas aleatorias "
                             "con la misma distancia de stop",
                     "value": {"real": exp_r, "modal": monkey.get("real_static_expectancy_r"),
                               "random_p95": monkey.get("random_p95"), "stop_ratio": monkey.get("stop_ratio")},
                     "pass": bool(monkey.get("beats_p95"))}
    out["criteria"] = crit
    out["defensible"] = all(c["pass"] for c in crit.values())
    return out


# ---------------------------------------------------------------- etapa DEV + VAL
class Runner:
    def __init__(self, md: MarketData, scenario: str, cfg: BacktestConfig, out: Path, n_monkey: int, n_anchor: int,
                 workers: int, seed: int, registry: Path | None, data_sha: str, log=print):
        self.md, self.scenario, self.scen, self.cfg = md, scenario, SCENARIOS[scenario], cfg
        self.out, self.n_monkey, self.n_anchor, self.workers, self.seed = out, n_monkey, n_anchor, workers, seed
        self.registry, self.data_sha, self.log = registry, data_sha, log
        self.windows = walk_forward_windows(self.scen["wf_start"], self.scen["val"][1], self.scen["train_months"],
                                            self.scen["test_months"])
        if not self.windows:
            raise ValueError("no hay ventanas de walk-forward en el periodo de datos")
        self.oos_start, self.oos_end = self.windows[0].test_start, self.windows[-1].test_end
        self.trials = []   # (id, n_configs)

    def _cfg(self, start, end) -> BacktestConfig:
        return replace(self.cfg, start=start, end=end)

    def _register(self, record: dict):
        if self.registry is None:
            return
        import uuid
        rec = {"experiment_id": f"{self.scenario}-{record.get('hypothesis_id', 'x')}-{uuid.uuid4().hex[:10]}",
               "protocol": PROTOCOL_VERSION, "scenario": self.scenario, "data": {"sha256": self.data_sha},
               **record}
        rec.update(git_info())
        append_experiment(sanitize(rec), self.registry)

    # --- walk-forward de una familia (o de una variante con filtro de régimen)
    def run_family(self, fam_id: str, fam: dict, extra_gate: dict | None = None, label: str | None = None) -> dict:
        label = label or fam_id
        t0 = time.perf_counter()
        grid = fam["grid"]
        base = _with_gate(fam["base"], extra_gate)
        if extra_gate and "regime_gate" in grid:
            grid = dict(grid)
            grid["regime_gate"] = [_with_gate({"regime_gate": g}, extra_gate)["regime_gate"] for g in grid["regime_gate"]]
            base.pop("regime_gate", None)
        wf = walk_forward(self.md, fam["strategy"], grid, self.cfg, self.windows, base_params=base,
                          objective="expectancy_r", min_trades=MIN_TRAIN_TRADES)
        wrows = wf["windows"]
        # repetición de las ventanas de prueba para encadenar la equidad M1 (drawdown exacto)
        results, chosen = [], []
        for _, row in wrows.iterrows():
            if row["chosen"] is None:
                continue
            params = {**base, **row["chosen"]}
            chosen.append(_params_key(fam["strategy"], params))
            results.append(run_backtest(self.md, make_strategy(fam["strategy"], params),
                                        self._cfg(row["test_start"], row["test_end"])))
        chained = _chained_equity(results)
        # configuración modal (la más elegida; empate -> la de la última ventana)
        modal = None
        if chosen:
            counts = pd.Series(chosen).value_counts()
            top = counts[counts == counts.max()].index
            last = [c for c in chosen if c in top][-1]
            for _, row in wrows.iterrows():
                if row["chosen"] is not None and _params_key(fam["strategy"], {**base, **row["chosen"]}) == last:
                    modal = {**base, **row["chosen"]}
        # congelado: mejor configuración en la última ventana de entrenamiento que acaba al final de VAL
        frozen = self._freeze(fam["strategy"], grid, base)
        res = {"family": fam_id, "label": label, "strategy": fam["strategy"], "title": fam["title"],
               "extra_gate": extra_gate, "grid": grid, "base": base, "n_configs": len(_grid(grid)),
               "config_keys": {_params_key(fam["strategy"], {**base, **c}) for c in _grid(grid)},
               "windows": [{"window": int(r["window"]), "train": f"{r['train_start']:%Y-%m-%d} -> {r['train_end']:%Y-%m-%d}",
                            "test": f"{r['test_start']:%Y-%m-%d} -> {r['test_end']:%Y-%m-%d}",
                            "chosen": r["chosen"], "train_expectancy_r": r["train_score"],
                            "train_n": _int0(r["train_n_trades"]), "test_n": _int0(r.get("test_n_trades")),
                            "test_expectancy_r": r.get("test_expectancy_r")} for _, r in wrows.iterrows()],
               "oos_trades": wf["oos_trades"], "oos_daily": wf["oos_daily_returns"], "chained_equity": chained,
               "modal_params": modal, "frozen_params": frozen}
        self.log(f"  {label}: {len(wf['oos_trades'])} operaciones OOS, "
                 f"esperanza {wf['oos_metrics'].get('expectancy_r', float('nan')):+.3f} R "
                 f"({time.perf_counter() - t0:.0f} s)")
        return res

    def _freeze(self, strategy: str, grid: dict, base: dict) -> dict | None:
        end = _ts(self.scen["val"][1])
        start = end - pd.DateOffset(months=self.scen["train_months"])
        best, best_sc = None, -np.inf
        for combo in _grid(grid):
            params = {**base, **combo}
            res = run_backtest(self.md, make_strategy(strategy, params), self._cfg(start, end))
            tm = trade_metrics(res.trades)
            sc = tm.get("expectancy_r", np.nan) if tm.get("n_trades", 0) >= MIN_TRAIN_TRADES else np.nan
            if np.isfinite(sc) and sc > best_sc:
                best, best_sc = params, sc
        return best

    def neighbours(self, fam: dict, base: dict, grid: dict) -> list[dict]:
        cfgs = []
        if grid:
            cfgs = [{**base, **c} for c in _grid(grid)]
        else:
            cfgs = [dict(base)] + [{**base, k: v} for k, vals in fam.get("neighbours", {}).items() for v in vals]
        out = []
        for p in cfgs:
            res = run_backtest(self.md, make_strategy(fam["strategy"], p), self._cfg(self.oos_start, self.oos_end))
            tm = trade_metrics(res.trades)
            out.append({"config": _describe({k: v for k, v in p.items() if k in grid or k in fam.get("neighbours", {})}),
                        "n_trades": int(tm.get("n_trades", 0)), "expectancy_r": float(tm.get("expectancy_r", np.nan))})
        return out

    def _static(self, strategy: str, params: dict):
        """La configuración fija sobre todo el periodo fuera de muestra: (esperanza R, stop mediano)."""
        res = run_backtest(self.md, make_strategy(strategy, params), self._cfg(self.oos_start, self.oos_end))
        e = float(trade_metrics(res.trades).get("expectancy_r", np.nan))
        rp = float(np.median(res.trades["r_price"].to_numpy(float))) if len(res.trades) else float("nan")
        return e, rp

    def monkey(self, strategy: str, params: dict, real_exp: float) -> dict:
        cfg = self._cfg(self.oos_start, self.oos_end)
        cal = calibrate_random_entry(self.md, strategy, params, cfg)
        static_e, static_stop = self._static(strategy, params)
        jobs = [("RANDOM_ENTRY", {"target": strategy, "target_params": dict(params), "p_entry": cal["p_entry"],
                                  "seed": self.seed + k, "use_target_exits": True}, cfg) for k in range(self.n_monkey)]
        out = _control(real_exp, static_e, static_stop, _pmap(self.md, jobs, self.workers), "entradas aleatorias (B3)")
        out["p_entry"] = cal["p_entry"]
        out["params"] = params
        return out

    def anchor_controls(self, modal: dict, real_exp: float) -> dict:
        cfg = self._cfg(self.oos_start, self.oos_end)
        base = {k: v for k, v in modal.items() if k not in ("anchor_mode", "anchor_seed")}
        jobs = [("SESSION_BREAKOUT", {**base, "anchor_mode": "random", "anchor_seed": self.seed + k}, cfg)
                for k in range(self.n_anchor)]
        static_e, static_stop = self._static("SESSION_BREAKOUT", base)
        # las anclas aleatorias conservan la regla real del stop (otro lado de SU rango): la relación de
        # stops se informa, pero no invalida el control
        anchor = _control(real_exp, static_e, static_stop, _pmap(self.md, jobs, self.workers),
                          "anclas aleatorias (H2)", check_stop_ratio=False)
        # mejora del filtro de compresión frente a su coste (enmienda 2)
        cond = {**base, "c_max": 0.4}
        unc = {**base, "c_max": None}
        rc = run_backtest(self.md, make_strategy("SESSION_BREAKOUT", cond), cfg)
        ru = run_backtest(self.md, make_strategy("SESSION_BREAKOUT", unc), cfg)
        ec = trade_metrics(rc.trades).get("expectancy_r", np.nan)
        eu = trade_metrics(ru.trades).get("expectancy_r", np.nan)
        cost10 = float(np.mean(FILTER_COST_USD / rc.trades["r_price"].to_numpy(float))) if len(rc.trades) else np.nan
        filt = {"expectancy_r_con_filtro": ec, "expectancy_r_sin_filtro": eu, "mejora": ec - eu,
                "coste_010_USD_en_R": cost10,
                "pass": bool(np.isfinite(ec) and np.isfinite(eu) and np.isfinite(cost10) and ec - eu > cost10)}
        return {"anchor": anchor, "compression_filter": filt,
                "pass": bool(anchor.get("beats_p95") and filt["pass"])}

    def h3b(self) -> dict:
        dev0, dev1 = self.scen["dev"]
        t0 = time.perf_counter()
        scan = scan_session_windows(self.md, dev0, dev1, self.cfg.costs, self.cfg.account_units_per_usd,
                                    rollover_from_min=self.cfg.rollover_from_min,
                                    rollover_to_min=self.cfg.rollover_to_min,
                                    max_spread_points=self.cfg.max_spread_points)
        table = scan["table"]
        best = scan["best"]
        out = {"n_tried": scan["n_tried"], "best": best, "table_top10": table[table["tried"]].sort_values(
            "t_stat", ascending=False).head(10).to_dict("records")}
        # posición de H3a (largo 00 -> 08) entre todas las ventanas probadas
        tried = table[table["tried"]].sort_values("t_stat", ascending=False).reset_index(drop=True)
        m = tried[(tried["h_in"] == 0) & (tried["duration_h"] == 8) & (tried["side"] == 1)]
        out["h3a_rank"] = {"rank": int(m.index[0]) + 1 if len(m) else None, "of": int(len(tried)),
                           "t_stat": float(m["t_stat"].iloc[0]) if len(m) else None}
        if best is None:
            out["pass"] = False
            return out
        params = {"h_in": int(best["h_in"]), "h_out": int(best["h_out"]), "side": int(best["side"]),
                  "sl_atr": 3.0, "atr_period": 14}
        rd = run_backtest(self.md, make_strategy("SESSION_DRIFT", params), self._cfg(dev0, dev1))
        rv = run_backtest(self.md, make_strategy("SESSION_DRIFT", params), self._cfg(*self.scen["val"]))
        dr = rd.daily_returns().to_numpy(float)
        dsr_samp = deflated_sharpe_ratio(dr, n_trials=max(scan["n_tried"], 1))
        tried_tab = table[table["tried"] & (table["sd_pts"] > 0)]
        sr_windows = (tried_tab["mean_pts"] / tried_tab["sd_pts"]).to_numpy(float)
        var_cross = float(np.var(sr_windows, ddof=1)) if len(sr_windows) > 2 else 0.0
        var_samp = (1 - dsr_samp["skew"] * dsr_samp["sr_per_period"]
                    + (dsr_samp["kurtosis"] - 1) / 4 * dsr_samp["sr_per_period"] ** 2) / max(dsr_samp["n_obs"] - 1, 1)
        # Decide la varianza bajo H0 (todas las ventanas sin ventaja real), con N = todas las ventanas
        # aunque estén muy correlacionadas (conservador en N). La dispersión entre ventanas incluye
        # la señal cuando la hay (con una deriva plantada de +0.30 USD/h daba DSR 0.05), así que
        # solo se informa.
        dsr = dict(dsr_samp)
        dsr["sr_variance_used"] = "muestral bajo H0 (enmienda 2, punto 17)"
        dsr["sr_variance_cross_windows"] = var_cross
        dsr["sr_variance_sampling"] = var_samp
        dsr["dsr_with_cross_variance_info"] = deflated_sharpe_ratio(
            dr, n_trials=max(scan["n_tried"], 1), sr_variance_trials=max(var_cross, var_samp)).get("dsr")
        tv = trade_metrics(rv.trades)
        out.update({"params": params, "dev_metrics": trade_metrics(rd.trades), "val_metrics": tv, "dsr_dev": dsr,
                    "pass_dsr": bool(dsr.get("dsr", 0) >= 0.95),
                    "pass_val_sign": bool(tv.get("expectancy_r", -1) > 0)})
        out["pass"] = out["pass_dsr"] and out["pass_val_sign"]
        self.log(f"  H3b: {scan['n_tried']} ventanas; mejor {params}; DSR {dsr.get('dsr', float('nan')):.3f}; "
                 f"VAL {tv.get('expectancy_r', float('nan')):+.3f} R ({time.perf_counter() - t0:.0f} s)")
        return out

    def parity(self) -> dict:
        out = {}
        start, end = _ts("2022-01-01"), _ts("2025-01-01")
        if self.md.first_time > start + pd.Timedelta(days=10) or self.md.last_time < end - pd.Timedelta(days=10):
            return {"note": "los datos no cubren 2022-2024"}
        pcfg = replace(self.cfg, start=start, end=end, costs=replace(self.cfg.costs, slippage_points=0.0),
                       rollover_from_min=0, rollover_to_min=0,
                       max_spread_points=usd_to_points(PARITY_MAX_SPREAD_USD, self.md.spec), entry_deadline_min=None)
        for k, ref in PARITY.items():
            res = run_backtest(self.md, make_strategy(ref["strategy"], ref["params"]), pcfg)
            tm = trade_metrics(res.trades)
            out[k] = {"python": {"n_trades": tm.get("n_trades"), "profit_factor": tm.get("profit_factor"),
                                 "net_profit": tm.get("net_profit"), "expectancy_r": tm.get("expectancy_r")},
                      "mt5": ref["mt5"]}
        return out

    def benchmarks(self) -> dict:
        bh = buy_and_hold_returns(self.md, self.oos_start, self.oos_end)
        vs = buy_hold_volscaled(self.md, self.oos_start, self.oos_end, self.cfg.costs, self.cfg.initial_equity,
                                self.cfg.account_units_per_usd, rollover_from_min=self.cfg.rollover_from_min,
                                rollover_to_min=self.cfg.rollover_to_min, max_spread_points=self.cfg.max_spread_points)
        return {"buy_hold": {"total_return_pct": float(100 * (np.prod(1 + bh.to_numpy()) - 1)),
                             **{k: v for k, v in daily_return_stats(bh).items() if k in ("sharpe_ann", "ann_vol")}},
                "buy_hold_volscaled": {k: vs["metrics"].get(k) for k in ("total_return_pct", "sharpe_ann", "ann_vol",
                                                                          "max_dd_pct_daily")},
                "volscaled_daily": vs["daily_returns"]}

    # --- etapa completa
    def run(self) -> dict:
        t_start = time.perf_counter()
        if self.registry is not None:
            v = verify_registry(self.registry)
            if not v["ok"]:
                raise RuntimeError(f"el registro no supera la verificación: {v['problems']}")
        order = PRIORITY[self.scenario]
        self.log(f"Escenario {self.scenario}: walk-forward {len(self.windows)} ventanas, "
                 f"fuera de muestra {self.oos_start:%Y-%m-%d} -> {self.oos_end:%Y-%m-%d}")
        bench = self.benchmarks()
        bench_sharpe = float(bench["buy_hold_volscaled"].get("sharpe_ann") or np.nan)
        fams = {fid: self.run_family(fid, FAMILIES[fid]) for fid in order}
        h3b = self.h3b()

        # estudios adicionales, solo para familias que superan el walk-forward (criterio b)
        def passes_b(fr):
            r = fr["oos_trades"]["r_net"].to_numpy(float) if len(fr["oos_trades"]) else np.array([])
            return len(r) > 1 and np.nanmean(r) > 0 and t_stat(r) >= 2.0
        survivors = [fid for fid in order if passes_b(fams[fid])]
        extras = {}
        max_regime = BUDGET_EXTRAS - 2          # 2 por familia; quedan 1 para la combinación y 1 para ML
        for fid in survivors:
            for k, gate in enumerate(FAMILIES[fid]["regime_extras"]):
                if len(extras) >= max_regime:
                    break
                lab = f"{fid}+regimen{k + 1}"
                extras[lab] = self.run_family(fid, FAMILIES[fid], extra_gate=gate, label=lab)
        combo = None
        if len(survivors) >= 2:
            combo = self.combination({fid: fams[fid] for fid in survivors})

        n_formula = PRIOR_TRIALS + sum(fr["n_configs"] for fr in fams.values()) + 1 + 2 * len(
            {e["family"] for e in extras.values()}) + (1 if combo else 0)
        # N = max(fórmula, configuraciones distintas del registro + las de esta ejecución + fase v4)
        this_keys = set()
        for fr in list(fams.values()) + list(extras.values()):
            this_keys.update(fr["config_keys"])
        prior_keys = distinct_config_keys(read_registry(self.registry)) if self.registry is not None else set()
        n_registry = PRIOR_TRIALS + len(prior_keys | this_keys) + 1 + (1 if combo else 0)
        n_trials = max(n_formula, n_registry)
        self.trials = {"formula": n_formula, "registry": n_registry, "used": n_trials}
        n_configs_budget = sum(fr["n_configs"] for fr in fams.values()) + 1
        assert n_configs_budget <= BUDGET_CANDIDATES, n_configs_budget

        evals = {}
        for lab, fr in list(fams.items()) + list(extras.items()):
            fam = FAMILIES[fr["family"]]
            nb = self.neighbours(fam, fr["base"], fr["grid"])
            real = float(np.nanmean(fr["oos_trades"]["r_net"])) if len(fr["oos_trades"]) else float("nan")
            mk = self.monkey(fr["strategy"], fr["modal_params"], real) if fr["modal_params"] is not None else None
            ev = evaluate_oos(fr["oos_trades"], fr["oos_daily"], fr["chained_equity"], self.md, self.cfg, self.scen,
                              n_trials, bench_sharpe, fam["direction_rule"], nb, mk, self.seed)
            ev["monkey"] = mk
            ev["neighbours"] = nb
            if fr["family"] == "H2" and fr["modal_params"] is not None:
                ev["h2_controls"] = self.anchor_controls(fr["modal_params"], real)
                ev["defensible"] = ev["defensible"] and ev["h2_controls"]["pass"]
            if fr["family"] == "H1" and self.scenario == "A":
                ev["note"] = "Infrapotenciada en el escenario A (enmienda 1): se informa, no se puede aceptar."
                ev["defensible"] = False
            evals[lab] = ev
            self.log(f"  {lab}: criterios {''.join(k for k, c in ev['criteria'].items() if c['pass']) or '-'} "
                     f"-> {'DEFENDIBLE' if ev['defensible'] else 'no defendible'}")
        # se registra cuando TODO se ha evaluado: un control que falle a mitad no deja registros a medias
        for lab, ev in evals.items():
            fr = fams.get(lab) or extras[lab]
            self._register({"hypothesis_id": lab, "split": "dev+val walk-forward", "strategy": fr["strategy"],
                            "grid": fr["grid"], "base": fr["base"], "windows": fr["windows"],
                            "config_keys": sorted(fr["config_keys"]),
                            "metrics": ev["metrics"], "criteria": ev["criteria"], "defensible": ev["defensible"],
                            "n_trials": n_trials})
        self._register({"hypothesis_id": "H3b", "split": "dev scan + val", "strategy": "SESSION_DRIFT",
                        "metrics": {"n_tried": h3b["n_tried"], "dsr_dev": h3b.get("dsr_dev"),
                                    "val": h3b.get("val_metrics")}, "pass": h3b.get("pass")})

        # Holm-Bonferroni sobre las cuatro hipótesis confirmatorias (p unilateral de la media de R)
        pv = [evals[f]["metrics"].get("p_value_r", 1.0) for f in order]
        pv = [1.0 if p is None or not np.isfinite(p) else p for p in pv]
        holm = holm_bonferroni(pv)
        holm_tab = {f: {"p": p, "p_holm": float(a), "rechaza_H0": bool(rj)}
                    for f, p, a, rj in zip(order, pv, holm["p_adjusted"], holm["reject"])}

        # H3b solo puede ser candidata si H3a lo es
        h3b_candidate = bool(h3b.get("pass") and evals.get("H3a", {}).get("defensible"))

        cands = [lab for lab, ev in evals.items() if ev["defensible"]]
        rank = sorted(cands, key=lambda lab: (-_num(evals[lab]["metrics"].get("sharpe_ann"), -np.inf),
                                              _num(evals[lab]["criteria"]["f"]["value"]["dd"], np.inf),
                                              FAMILIES[(fams.get(lab) or extras[lab])["family"]]["n_components"]))
        frozen = []
        for lab in rank[:3]:
            fr = fams.get(lab) or extras[lab]
            if fr["frozen_params"] is None:
                continue
            frozen.append({"label": lab, "family": fr["family"], "strategy": fr["strategy"],
                           "params": fr["frozen_params"], "key": _params_key(fr["strategy"], fr["frozen_params"]),
                           "scenario": self.scenario, "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                           "data_sha256": self.data_sha})
        if h3b_candidate and len(frozen) < 3:
            frozen.append({"label": "H3b", "family": "H3b", "strategy": "SESSION_DRIFT", "params": h3b["params"],
                           "key": _params_key("SESSION_DRIFT", h3b["params"]), "scenario": self.scenario,
                           "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(), "data_sha256": self.data_sha})
        report = {"protocol": PROTOCOL_VERSION, "scenario": self.scenario, "data_sha256": self.data_sha,
                  "data_range": [str(self.md.first_time), str(self.md.last_time)],
                  "oos_range": [str(self.oos_start), str(self.oos_end)],
                  "windows": [{"train": [str(w.train_start), str(w.train_end)], "test": [str(w.test_start), str(w.test_end)]}
                              for w in self.windows],
                  "config": self.cfg.to_dict(), "n_trials": n_trials, "trials_detail": self.trials,
                  "prior_trials": PRIOR_TRIALS, "cost_inputs": getattr(self, "cost_inputs", {}),
                  "benchmarks": {k: v for k, v in bench.items() if k != "volscaled_daily"},
                  "parity": self.parity(), "families": {}, "h3b": h3b, "holm": holm_tab, "survivors_b": survivors,
                  "combination": combo, "ml": "no ejecutado: excluido en el escenario A; en B solo si una familia sobrevive",
                  "candidates_ranked": rank, "frozen": frozen, "runtime_s": time.perf_counter() - t_start,
                  "git": git_info()}
        for lab, ev in evals.items():
            fr = fams.get(lab) or extras[lab]
            report["families"][lab] = {k: fr[k] for k in ("family", "title", "strategy", "base", "grid", "extra_gate",
                                                          "windows", "modal_params", "frozen_params")}
            report["families"][lab].update({k: v for k, v in ev.items()})
            fr["oos_trades"].to_csv(self.out / f"oos_trades_{lab}.csv", index=False)
        return report

    def combination(self, fams: dict) -> dict:
        daily = pd.concat({k: v["oos_daily"] for k, v in fams.items()}, axis=1).fillna(0.0)
        corr = daily.corr()
        off = corr.where(~np.eye(len(corr), dtype=bool)).abs().max().max()
        if not np.isfinite(off) or off >= 0.5:
            return {"members": list(fams), "max_abs_corr": float(off), "run": False,
                    "note": "correlación >= 0.5: no se combina"}
        comb = daily.mean(axis=1)
        s = daily_return_stats(comb).get("sharpe_ann", np.nan)
        comp = {k: daily_return_stats(daily[k]).get("sharpe_ann", np.nan) for k in daily}
        return {"members": list(fams), "max_abs_corr": float(off), "run": True, "sharpe_ann": s,
                "components_sharpe": comp, "beats_each": bool(all(s > v for v in comp.values()))}


# ---------------------------------------------------------------- etapa HOLD
def holdout_locks(registry: Path) -> list[dict]:
    return [r for r in read_registry(registry) if r.get("record_type") == "holdout_lock"]


def run_holdout(md: MarketData, scenario: str, cfg: BacktestConfig, frozen: list[dict], registry: Path,
                contaminated_rerun: bool, data_sha: str, out_dir: Path, log=print) -> dict:
    """Una sola ejecución por candidata. El bloqueo se escribe en el registro encadenado ANTES
    de calcular el resultado; si ya existe uno para la misma candidata y escenario, se rechaza."""
    if registry is None:
        raise ValueError("la reserva final siempre se anota: no se admite --no-registry")
    v = verify_registry(registry)
    if not v["ok"]:
        raise RuntimeError(f"el registro no supera la verificación: {v['problems']}")
    scen = SCENARIOS[scenario]
    start = _ts(scen["hold_start"])
    end = md.last_time + pd.Timedelta(minutes=1)
    out = {"scenario": scenario, "range": [str(start), str(end)], "results": {}}
    for c in frozen:
        key = c["key"]
        if key != _params_key(c["strategy"], c["params"]):
            raise ValueError(f"{c['label']}: la clave no coincide con los parámetros congelados")
        used = {r["key"] for r in holdout_locks(registry) if r.get("scenario") == scenario}
        contaminated = key in used
        if contaminated and not contaminated_rerun:
            log(f"  {c['label']}: la reserva final YA se usó con esta candidata. Rechazado (usa datos nuevos o la demo).")
            out["results"][c["label"]] = {"refused": True}
            continue
        import uuid
        append_experiment(sanitize({
            "experiment_id": f"lock-{scenario}-{key}-{uuid.uuid4().hex[:8]}", "record_type": "holdout_lock",
            "protocol": PROTOCOL_VERSION, "key": key, "scenario": scenario, "label": c["label"],
            "strategy": c["strategy"], "params": c["params"], "data": {"sha256": data_sha}, "range": out["range"],
            "contaminated": contaminated, **git_info()}), registry)          # ANTES de ver el resultado
        res = run_backtest(md, make_strategy(c["strategy"], c["params"]), replace(cfg, start=start, end=end))
        tm = trade_metrics(res.trades)
        dd = _max_dd_pct(np.asarray(res.equity, float) / res.initial_equity)
        n = int(tm.get("n_trades", 0))
        pf, e = tm.get("profit_factor", np.nan), tm.get("expectancy_r", np.nan)
        crit = {"PF >= 1.10": bool(np.isfinite(pf) and pf >= 1.10), "esperanza > 0": bool(np.isfinite(e) and e > 0),
                "drawdown <= 20 %": bool(dd <= 20.0), "operaciones >= 30": n >= 30}
        r = {"metrics": {**tm, "max_dd_pct": dd, **daily_return_stats(res.daily_returns())}, "criteria": crit,
             "pass": all(crit.values()) and not contaminated, "contaminated": contaminated}
        out["results"][c["label"]] = r
        res.trades.to_csv(out_dir / f"holdout_trades_{c['label']}.csv", index=False)
        append_experiment(sanitize({
            "experiment_id": f"hold-{scenario}-{key}-{uuid.uuid4().hex[:8]}", "record_type": "holdout_result",
            "protocol": PROTOCOL_VERSION, "scenario": scenario, "hypothesis_id": c["label"], "split": "holdout",
            "key": key, "config_keys": [key], "strategy": c["strategy"], "params": c["params"],
            "data": {"sha256": data_sha}, "metrics": r["metrics"], "criteria": crit, "pass": r["pass"],
            "contaminated": contaminated, **git_info()}), registry)
        log(f"  {c['label']}: {n} operaciones, PF {pf:.2f}, esperanza {e:+.3f} R, DD {dd:.1f} % -> "
            f"{'SUPERA' if r['pass'] else 'NO supera'} la reserva final")
    return out


# ---------------------------------------------------------------- informe
def _fmt(v, nd=2):
    if v is None:
        return "–"
    if isinstance(v, (bool, np.bool_)):
        return "sí" if v else "no"
    if isinstance(v, (int, np.integer)):
        return f"{int(v)}"
    if isinstance(v, (float, np.floating)):
        return "–" if not np.isfinite(v) else f"{v:.{nd}f}"
    if isinstance(v, dict):
        return ", ".join(f"{k} {_fmt(x, nd)}" for k, x in v.items())
    if isinstance(v, list):
        return "; ".join(f"{x.get('config')}: n {x.get('n_trades')}, {_fmt(x.get('expectancy_r'), 3)} R"
                         if isinstance(x, dict) else str(x) for x in v)
    return str(v)


def render_markdown(rep: dict) -> str:
    L = [f"# Informe del protocolo v5: escenario {rep['scenario']}", "",
         f"- Protocolo: {rep['protocol']}. Datos: `{rep['data_sha256'][:16]}…`, {rep['data_range'][0]} → {rep['data_range'][1]}.",
         f"- Fuera de muestra (walk-forward DEV + VAL concatenado): {rep['oos_range'][0][:10]} → {rep['oos_range'][1][:10]}, "
         f"{len(rep['windows'])} ventanas.",
         f"- Costes: deslizamiento {_fmt(rep['config']['costs']['slippage_points'])} puntos por ejecución "
         f"(base {_fmt((rep.get('cost_inputs') or {}).get('slippage_usd'))} USD + la mitad del spread adicional "
         f"{_fmt(((rep.get('cost_inputs') or {}).get('extra_spread_usd') or 0) + ((rep.get('cost_inputs') or {}).get('spread_audit_extra_usd') or 0))} USD), comisión "
         f"{rep['config']['costs']['commission_per_lot_rt']} por lote ida y vuelta, swap {'sí' if rep['config']['costs']['apply_swap'] else 'no'}. "
         f"Riesgo {rep['config']['risk_pct']} % por operación.",
         f"- Pruebas contadas para el Deflated Sharpe: **{rep['n_trials']}** (incluye {rep['prior_trials']} de la fase v4).",
         f"- Commit: `{str(rep.get('git', {}).get('git_commit', ''))[:10]}`. Duración: {rep['runtime_s']:.0f} s.", ""]
    par = rep.get("parity", {})
    if par and "note" not in par:
        L += ["## Contraste con el probador de MT5 (2022-2024)", "", "| Referencia | Python: operaciones | Python: PF | MT5: operaciones | MT5: PF |",
              "|---|---|---|---|---|"]
        for k, v in par.items():
            L.append(f"| {k} | {_fmt(v['python']['n_trades'])} | {_fmt(v['python']['profit_factor'])} | "
                     f"{v['mt5']['n_trades']} | {v['mt5']['profit_factor']} |")
        L.append("")
    b = rep["benchmarks"]
    L += ["## Referencias en el mismo periodo fuera de muestra", "",
          f"- Comprar y mantener: {_fmt(b['buy_hold'].get('total_return_pct'))} %, Sharpe {_fmt(b['buy_hold'].get('sharpe_ann'))}.",
          f"- Comprar y mantener escalado por volatilidad: {_fmt(b['buy_hold_volscaled'].get('total_return_pct'))} %, "
          f"Sharpe {_fmt(b['buy_hold_volscaled'].get('sharpe_ann'))}.", ""]
    L += ["## Resumen por familia", "", "| Familia | Operaciones | Esperanza R | t | PF | Sharpe | DD % | Criterios cumplidos | Defendible |",
          "|---|---|---|---|---|---|---|---|---|"]
    for lab, f in rep["families"].items():
        m = f["metrics"]
        passed = "".join(k for k, c in f["criteria"].items() if c["pass"]) or "ninguno"
        dd = f["criteria"].get("f", {}).get("value")
        L.append(f"| {lab} | {_fmt(m.get('n_trades'))} | {_fmt(m.get('expectancy_r'), 3)} | {_fmt(m.get('t_stat_r'))} | "
                 f"{_fmt(m.get('profit_factor'))} | {_fmt(m.get('sharpe_ann'))} | "
                 f"{_fmt(dd.get('dd') if isinstance(dd, dict) else None, 1)} | {passed} | "
                 f"{'**sí**' if f['defensible'] else 'no'} |")
    L.append("")
    for lab, f in rep["families"].items():
        L += [f"## {lab}: {f['title']}", "", f"Estrategia `{f['strategy']}`; base {_describe(f['base'])}; "
              f"rejilla {_describe(f['grid']) if f['grid'] else 'ninguna (configuración fija)'}"
              + (f"; filtro añadido {_describe(f['extra_gate'])}" if f.get("extra_gate") else "") + ".", "",
              "| Ventana | Entrenamiento | Prueba | Elegida | Esperanza R (entr.) | Operaciones (prueba) | Esperanza R (prueba) |",
              "|---|---|---|---|---|---|---|"]
        for w in f["windows"]:
            L.append(f"| {w['window']} | {w['train']} | {w['test']} | {_describe(w['chosen']) if w['chosen'] is not None else 'ninguna (n < 30)'} | "
                     f"{_fmt(w['train_expectancy_r'], 3)} | {w['test_n']} | {_fmt(w['test_expectancy_r'], 3)} |")
        L += ["", "| Criterio | Umbral | Valor | Cumple |", "|---|---|---|---|"]
        for k, c in f["criteria"].items():
            L.append(f"| {k} | {c['desc']} | {_fmt(c['value'], 3)} | {'✔' if c['pass'] else '✘'} |")
        if f.get("h2_controls"):
            h = f["h2_controls"]
            L += ["", f"Controles de H2: anclas aleatorias p95 {_fmt(h['anchor'].get('random_p95'), 3)} R "
                      f"(real {_fmt(h['anchor'].get('real_expectancy_r'), 3)}); mejora del filtro de compresión "
                      f"{_fmt(h['compression_filter']['mejora'], 3)} R frente a un coste de 0.10 USD de "
                      f"{_fmt(h['compression_filter']['coste_010_USD_en_R'], 3)} R → {'cumple' if h['pass'] else 'no cumple'}."]
        if f.get("note"):
            L += ["", f"**Nota:** {f['note']}"]
        L += ["", f"Parámetros que se congelarían (última ventana de entrenamiento): {_describe(f['frozen_params']) if f['frozen_params'] else 'ninguno'}.", ""]
    h = rep["h3b"]
    L += ["## H3b: barrido exploratorio de ventanas horarias (solo DEV)", "",
          f"- Ventanas probadas: {h['n_tried']}. Mejor: {_describe(h.get('params') or {})}.",
          f"- Deflated Sharpe en DEV con N = {h['n_tried']}: {_fmt((h.get('dsr_dev') or {}).get('dsr'), 3)}; "
          f"esperanza en VAL {_fmt((h.get('val_metrics') or {}).get('expectancy_r'), 3)} R.",
          f"- Puesto de H3a (largo 00→08 UTC) en DEV: {h['h3a_rank']['rank']} de {h['h3a_rank']['of']}.",
          f"- Resultado: {'cumple' if h.get('pass') else 'no cumple'} (además necesita que H3a sea defendible).", ""]
    L += ["## Holm-Bonferroni (cuatro hipótesis confirmatorias)", "", "| Hipótesis | p | p ajustado | Rechaza H0 al 5 % |", "|---|---|---|---|"]
    for k, v in rep["holm"].items():
        L.append(f"| {k} | {_fmt(v['p'], 4)} | {_fmt(v['p_holm'], 4)} | {'sí' if v['rechaza_H0'] else 'no'} |")
    L.append("")
    if rep.get("combination"):
        c = rep["combination"]
        L += ["## Combinación", "", f"Miembros {', '.join(c['members'])}; correlación máxima {_fmt(c['max_abs_corr'])}; "
              + (f"Sharpe {_fmt(c.get('sharpe_ann'))}, mejora a cada componente: {'sí' if c.get('beats_each') else 'no'}." if c.get("run") else c.get("note", "")), ""]
    L += ["## Conclusión", ""]
    if rep["frozen"]:
        L.append("Candidatas congeladas para la reserva final (una sola ejecución cada una):")
        for c in rep["frozen"]:
            L.append(f"- **{c['label']}** `{c['strategy']}` {_describe(c['params'])} (clave `{c['key']}`)")
    else:
        L.append("**Ninguna configuración es defendible** con los criterios prerregistrados. No se congela nada y la "
                 "reserva final no se consulta.")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- CLI
def spread_audit_extra_usd(path, spec) -> float:
    """Spread que las velas M1 no recogen: media por hora de max(0, spread de ticks - spread M1)
    del archivo ``KQ_<SÍMBOLO>_spread_por_hora.csv`` del script de auditoría, en USD."""
    df = pd.read_csv(path)
    m1_col = "spread_m1_media_mismos_dias"
    if m1_col not in df.columns:
        raise ValueError(f"{path}: falta la columna {m1_col}. Repite la auditoría con la versión actual de "
                         "KQ_AuditoriaEntorno, que compara ticks y velas M1 de los mismos días")
    if "spread_ticks_media" not in df.columns:
        raise ValueError(f"{path}: falta la columna spread_ticks_media")
    d = (df["spread_ticks_media"] - df[m1_col]).clip(lower=0.0)
    d = d[np.isfinite(d) & (df["spread_ticks_media"] > 0)]
    return float(d.mean() * spec.point) if len(d) else 0.0


def build_config(md: MarketData, a) -> BacktestConfig:
    spec = md.spec
    units = a.units_per_usd if a.units_per_usd is not None else spec.default_units_per_usd()
    chk = spec.money_per_lot_check(units)
    if not chk["ok"]:
        raise ValueError(f"valor por lote incoherente: el motor supone {chk['expected']} por 1.0 de precio y lote "
                         f"(contract_size x units), el bróker dice {chk['observed']} ({chk['source']}). "
                         "Revisa --units-per-usd o el spec.")
    off = spec.server_offset_check()
    if not off["ok"]:
        raise ValueError(f"la hora del servidor no es NY+7: offset esperado {off['expected_seconds']} s, "
                         f"auditado {off['observed_seconds']} s")
    brk = daily_break_check(md.t)
    if not brk["ok"]:
        raise ValueError(f"la pausa diaria del oro cambia de hora en las semanas en que los horarios de verano de "
                         f"EE. UU. y Europa no coinciden ({brk}): el servidor no parece NY+7")
    comm = a.commission
    if comm is None:
        comm = commission_rt_from_spec(spec) or 0.0
    extra_usd = a.extra_spread_usd
    audit_extra = spread_audit_extra_usd(a.spread_audit, spec) if a.spread_audit else 0.0
    extra_usd += audit_extra
    slip_pts = usd_to_points(a.slippage_usd + extra_usd / 2.0, spec)
    costs = CostModel(slippage_points=slip_pts, commission_per_lot_rt=comm, apply_swap=not a.no_swap)
    cfg = BacktestConfig(initial_equity=a.initial_equity, risk_pct=1.0, account_units_per_usd=units,
                         costs=costs, rollover_from_min=1425, rollover_to_min=75,
                         max_spread_points=usd_to_points(a.max_spread_usd, spec), entry_deadline_min=90.0)
    cfg_inputs = {"point": spec.point, "units_per_usd": units, "money_per_lot": chk, "server_offset": off,
                  "daily_break": brk,
                  "slippage_usd": a.slippage_usd, "extra_spread_usd": a.extra_spread_usd,
                  "spread_audit_extra_usd": audit_extra, "slippage_points_per_fill": slip_pts,
                  "max_spread_usd": a.max_spread_usd, "commission_per_lot_rt": comm}
    return cfg, cfg_inputs


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Protocolo prerregistrado v5: walk-forward DEV+VAL y reserva final")
    p.add_argument("stage", choices=["devval", "holdout"])
    p.add_argument("--scenario", choices=list(SCENARIOS), required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--spec", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--frozen", help="frozen_candidates.json (etapa holdout)")
    p.add_argument("--commission", type=float, default=None, help="por lote ida y vuelta (defecto: la del spec o 0)")
    p.add_argument("--slippage-usd", type=float, default=SLIPPAGE_USD, help="deslizamiento por ejecución, USD/oz")
    p.add_argument("--extra-spread-usd", type=float, default=0.0,
                   help="spread adicional por operación en USD/oz (p. ej. HFM - Dukascopy); se reparte entre "
                        "entrada y salida")
    p.add_argument("--spread-audit", default=None,
                   help="KQ_<SÍMBOLO>_spread_por_hora.csv: añade el spread de ticks que las velas M1 no recogen")
    p.add_argument("--no-swap", action="store_true")
    p.add_argument("--max-spread-usd", type=float, default=MAX_SPREAD_USD)
    p.add_argument("--initial-equity", type=float, default=10_000.0)
    p.add_argument("--units-per-usd", type=float, default=None, help="por defecto, según la divisa del spec")
    p.add_argument("--n-monkey", type=int, default=1000)
    p.add_argument("--n-anchor", type=int, default=1000)
    p.add_argument("--workers", type=int, default=mp.cpu_count() or 1)
    p.add_argument("--seed", type=int, default=20260929)
    p.add_argument("--registry", default=str(REGISTRY_PATH))
    p.add_argument("--no-registry", action="store_true")
    p.add_argument("--contaminated-rerun", action="store_true")
    a = p.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    scen = SCENARIOS[a.scenario]
    data_sha = file_sha256(a.data)
    registry = None if a.no_registry else Path(a.registry)
    logf = open(out / "log.txt", "a")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    if registry is not None:
        dirty = [f.name for f in (registry, head_path(registry)) if git_uncommitted(f)]
        if dirty and a.stage == "holdout":
            p.error(f"el registro tiene cambios sin commit ({dirty}): haz commit antes de consultar la reserva final")
        if dirty:
            log(f"AVISO: el registro tiene cambios sin commit ({dirty}). Haz commit tras cada ejecución con datos reales.")
    if a.stage == "holdout" and (registry is None or registry.resolve() != REGISTRY_PATH.resolve()):
        p.error("la reserva final solo se ejecuta con el registro canónico del repositorio (research/registry)")

    if a.stage == "devval":
        md = MarketData.from_csv(a.data, a.spec, end=scen["val"][1])   # la reserva final no se carga
        log(f"Datos cargados hasta {md.last_time} ({len(md)} velas M1); reserva final excluida.")
        cfg, cost_inputs = build_config(md, a)
        log(f"Costes: {json.dumps(sanitize(cost_inputs), ensure_ascii=False)}")
        runner = Runner(md, a.scenario, cfg, out, a.n_monkey, a.n_anchor, a.workers, a.seed, registry, data_sha, log)
        runner.cost_inputs = cost_inputs
        rep = runner.run()
        (out / "report.json").write_text(json.dumps(sanitize(rep), indent=2, ensure_ascii=False, default=str))
        (out / "REPORTE.md").write_text(render_markdown(rep))
        (out / "frozen_candidates.json").write_text(json.dumps(sanitize(rep["frozen"]), indent=2, ensure_ascii=False))
        log(f"Informe: {out / 'REPORTE.md'}")
    else:
        if not a.frozen:
            p.error("--frozen es obligatorio en la etapa holdout")
        frozen = json.loads(Path(a.frozen).read_text())
        if not frozen:
            log("No hay candidatas congeladas: la reserva final no se consulta.")
            return 0
        md = MarketData.from_csv(a.data, a.spec)
        cfg, _ = build_config(md, a)
        rep = run_holdout(md, a.scenario, cfg, frozen, registry, a.contaminated_rerun, data_sha, out, log)
        (out / "holdout_report.json").write_text(json.dumps(sanitize(rep), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
