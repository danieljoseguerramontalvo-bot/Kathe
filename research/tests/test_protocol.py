"""Ejecutor del protocolo v5: criterios a-k, clave de congelado y bloqueo de la reserva final."""
import json

import numpy as np
import pandas as pd
import pytest

from kq import protocol as pr
from kq.data import MarketData, SymbolSpec
from kq.engine import BacktestConfig
from kq.synth import generate_m1


def _trades(r, start="2023-07-03", spacing_h=30, r_price=10.0):
    n = len(r)
    exit_t = pd.Timestamp(start) + pd.to_timedelta(np.arange(n) * spacing_h, unit="h")
    r = np.asarray(r, float)
    return pd.DataFrame({"r_net": r, "net_pnl": r * 100.0, "side": np.where(np.arange(n) % 2 == 0, 1, -1),
                         "exit_time": exit_t, "lots": 0.1, "r_price": r_price, "commission": 0.0, "swap": 0.0,
                         "hold_minutes": 240.0, "exit_reason": "tp"})


def _daily(trades):
    d = trades.groupby(trades["exit_time"].dt.normalize())["net_pnl"].sum() / 10_000.0
    return d


def _eval(trades, monkey_p95=0.0, neighbours=None):
    md = MarketData(generate_m1("2023-01-02", "2023-01-10", seed=1), SymbolSpec())
    daily = _daily(trades)
    eq = np.r_[1.0, np.cumprod(1 + daily.to_numpy())]
    nb = neighbours if neighbours is not None else [{"config": "x", "n_trades": 50, "expectancy_r": 0.2}]
    return pr.evaluate_oos(trades, daily, eq, md, BacktestConfig(), pr.SCENARIOS["A"], 22, -1.0,
                           "short_or_volscaled", nb, {"random_p95": monkey_p95})


def test_strong_edge_passes_core_criteria():
    rng = np.random.default_rng(0)
    r = rng.normal(0.35, 1.0, 400)
    ev = _eval(_trades(r))
    c = ev["criteria"]
    for k in ("a", "b", "d", "e", "i", "k"):
        assert c[k]["pass"], (k, c[k])


def test_no_edge_fails():
    rng = np.random.default_rng(1)
    ev = _eval(_trades(rng.normal(-0.02, 1.0, 400)))
    assert not ev["criteria"]["b"]["pass"]
    assert not ev["defensible"]


def test_concentration_and_neighbours_fail():
    r = np.r_[np.full(300, -0.05), np.full(5, 20.0)]      # todo el beneficio en 5 operaciones
    ev = _eval(_trades(r), neighbours=[{"config": "a", "n_trades": 50, "expectancy_r": 0.1},
                                       {"config": "b", "n_trades": 50, "expectancy_r": -0.01},
                                       {"config": "c", "n_trades": 3, "expectancy_r": -5.0}])
    assert not ev["criteria"]["h"]["pass"]
    assert not ev["criteria"]["i"]["pass"]


def test_neighbours_with_few_trades_are_not_counted():
    rng = np.random.default_rng(2)
    ev = _eval(_trades(rng.normal(0.3, 1.0, 300)), neighbours=[{"config": "a", "n_trades": 50, "expectancy_r": 0.1},
                                                               {"config": "c", "n_trades": 3, "expectancy_r": -5.0}])
    assert ev["criteria"]["i"]["pass"]


def test_monkey_threshold():
    rng = np.random.default_rng(3)
    ev = _eval(_trades(rng.normal(0.1, 1.0, 300)), monkey_p95=0.5)
    assert not ev["criteria"]["k"]["pass"]


def test_budget_and_trials():
    n_grid = sum(len(pr._grid(f["grid"])) for f in pr.FAMILIES.values())
    assert n_grid + 1 == pr.BUDGET_CANDIDATES       # 13 de las rejillas + H3b
    assert pr.PRIORITY["A"][0] == "H3a" and pr.PRIORITY["B"][0] == "H1"


def test_params_key_is_order_independent():
    a = pr._params_key("SESSION_DRIFT", {"h_in": 0, "h_out": 8})
    b = pr._params_key("SESSION_DRIFT", {"h_out": 8, "h_in": 0})
    assert a == b and a != pr._params_key("SESSION_DRIFT", {"h_in": 1, "h_out": 8})


def test_holdout_runs_once_per_candidate(tmp_path):
    md = MarketData(generate_m1("2025-04-01", "2025-09-01", seed=5), SymbolSpec())
    params = {"h_in": 0, "h_out": 8, "side": 1, "sl_atr": 3.0, "atr_period": 14}
    frozen = [{"label": "H3a", "strategy": "SESSION_DRIFT", "params": params,
               "key": pr._params_key("SESSION_DRIFT", params)}]
    lock = tmp_path / "lock.jsonl"
    cfg = BacktestConfig()
    first = pr.run_holdout(md, "A", cfg, frozen, lock, False, None, "sha", tmp_path, log=lambda *_: None)
    assert "metrics" in first["results"]["H3a"]
    assert len(lock.read_text().splitlines()) == 1
    second = pr.run_holdout(md, "A", cfg, frozen, lock, False, None, "sha", tmp_path, log=lambda *_: None)
    assert second["results"]["H3a"] == {"refused": True}
    third = pr.run_holdout(md, "A", cfg, frozen, lock, True, None, "sha", tmp_path, log=lambda *_: None)
    assert third["results"]["H3a"]["contaminated"] is True and third["results"]["H3a"]["pass"] is False
    assert json.loads(lock.read_text().splitlines()[-1])["contaminated"] is True


def test_holdout_rejects_tampered_key(tmp_path):
    md = MarketData(generate_m1("2025-06-01", "2025-08-01", seed=5), SymbolSpec())
    frozen = [{"label": "X", "strategy": "SESSION_DRIFT", "params": {"h_in": 1, "h_out": 8}, "key": "deadbeef"}]
    with pytest.raises(ValueError):
        pr.run_holdout(md, "A", BacktestConfig(), frozen, tmp_path / "l.jsonl", False, None, "sha", tmp_path,
                       log=lambda *_: None)
