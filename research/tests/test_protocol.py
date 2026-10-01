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
    exp = float(np.mean(trades["r_net"]))
    md = MarketData(generate_m1("2023-01-02", "2023-01-10", seed=1), SymbolSpec())
    daily = _daily(trades)
    eq = np.r_[1.0, np.cumprod(1 + daily.to_numpy())]
    nb = neighbours if neighbours is not None else [{"config": "x", "n_trades": 50, "expectancy_r": 0.2}]
    return pr.evaluate_oos(trades, daily, eq, md, BacktestConfig(), pr.SCENARIOS["A"], 22, -1.0,
                           "short_or_volscaled", nb, {"random_p95": monkey_p95, "beats_p95": exp > monkey_p95})


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
    reg = tmp_path / "experiments.jsonl"
    cfg = BacktestConfig()
    quiet = lambda *_: None  # noqa: E731
    first = pr.run_holdout(md, "A", cfg, frozen, reg, False, "sha", tmp_path, log=quiet)
    assert "metrics" in first["results"]["H3a"]
    assert len(pr.holdout_locks(reg)) == 1
    second = pr.run_holdout(md, "A", cfg, frozen, reg, False, "sha", tmp_path, log=quiet)
    assert second["results"]["H3a"] == {"refused": True}
    third = pr.run_holdout(md, "A", cfg, frozen, reg, True, "sha", tmp_path, log=quiet)
    assert third["results"]["H3a"]["contaminated"] is True and third["results"]["H3a"]["pass"] is False
    assert pr.holdout_locks(reg)[-1]["contaminated"] is True
    # deleting the lock (the last records) is detected and blocks any further holdout run
    lines = reg.read_text().splitlines()
    reg.write_text("\n".join(lines[:1]) + "\n")
    with pytest.raises(RuntimeError):
        pr.run_holdout(md, "A", cfg, frozen, reg, False, "sha", tmp_path, log=quiet)
    with pytest.raises(ValueError):
        pr.run_holdout(md, "A", cfg, frozen, None, False, "sha", tmp_path, log=quiet)


def test_holdout_rejects_tampered_key(tmp_path):
    md = MarketData(generate_m1("2025-06-01", "2025-08-01", seed=5), SymbolSpec())
    frozen = [{"label": "X", "strategy": "SESSION_DRIFT", "params": {"h_in": 1, "h_out": 8}, "key": "deadbeef"}]
    with pytest.raises(ValueError):
        pr.run_holdout(md, "A", BacktestConfig(), frozen, tmp_path / "r.jsonl", False, "sha", tmp_path,
                       log=lambda *_: None)


def test_control_requires_random_runs_and_similar_stops():
    with pytest.raises(RuntimeError):
        pr._control(0.1, 0.1, 5.0, [(float("nan"), 0, float("nan"))] * 3, "x")
    vals = [(0.0 + 0.001 * k, 100, 5.0) for k in range(100)]
    ok = pr._control(0.5, 0.4, 5.0, vals, "x")
    assert ok["valid"] and ok["beats_p95"]
    biased = pr._control(0.5, 0.4, 5.0, [(v, n, 2.0) for v, n, _ in vals], "x")   # random stops 2.5x tighter
    assert not biased["valid"] and not biased["beats_p95"]
    only_wf = pr._control(0.5, -0.1, 5.0, vals, "x")                              # modal config does not beat it
    assert not only_wf["beats_p95"]


def test_costs_are_defined_in_usd_for_any_digits():
    import argparse
    a = argparse.Namespace(units_per_usd=None, commission=0.0, extra_spread_usd=0.0, spread_audit=None,
                           slippage_usd=0.03, no_swap=False, initial_equity=10_000.0, max_spread_usd=0.60)
    md2 = MarketData(generate_m1("2023-01-02", "2023-01-10", seed=1), SymbolSpec())
    md3 = MarketData(generate_m1("2023-01-02", "2023-01-10", seed=1),
                     SymbolSpec(digits=3, point=0.001, tick_size=0.001, tick_value=0.1))
    c2, _ = pr.build_config(md2, a)
    c3, _ = pr.build_config(md3, a)
    assert c2.costs.slippage_points == pytest.approx(3.0) and c3.costs.slippage_points == pytest.approx(30.0)
    assert c2.max_spread_points == pytest.approx(60.0) and c3.max_spread_points == pytest.approx(600.0)


def test_money_per_lot_mismatch_is_rejected():
    import argparse
    a = argparse.Namespace(units_per_usd=1.0, commission=0.0, extra_spread_usd=0.0, spread_audit=None,
                           slippage_usd=0.03, no_swap=False, initial_equity=10_000.0, max_spread_usd=0.60)
    spec = SymbolSpec(account_currency="USC")          # broker: tick_value 1.0 per 0.01 -> 100 per 1.0 move
    spec.extra["money_per_price_unit_per_lot"] = 10_000.0   # but the audit says 10 000 USC
    md = MarketData(generate_m1("2023-01-02", "2023-01-10", seed=1), spec)
    with pytest.raises(ValueError):
        pr.build_config(md, a)                      # units 1 contradicts the audit
    a.units_per_usd = None                           # default from the spec currency: 100
    cfg, info = pr.build_config(md, a)
    assert cfg.account_units_per_usd == 100.0 and info["money_per_lot"]["ok"]


def test_daily_break_check_detects_eu_based_server():
    from kq.data import daily_break_check
    from kq.timeutil import server_to_utc
    df = generate_m1("2023-01-02", "2024-01-01", seed=2)
    t = df.index.as_unit("ns").asi8
    ok = daily_break_check(t)
    assert ok["checked"] and ok["ok"]
    utc = pd.DatetimeIndex(server_to_utc(df.index))
    eet = utc.tz_localize("UTC").tz_convert("Europe/Athens").tz_localize(None)   # EET/EEST server
    bad = daily_break_check(eet.as_unit("ns").asi8)
    assert bad["checked"] and not bad["ok"]


def test_usd_to_points_is_exact_and_spread_audit_uses_same_days(tmp_path):
    spec = SymbolSpec()
    assert pr.usd_to_points(0.29, spec) == 29.0
    csv = tmp_path / "a.csv"
    csv.write_text("hora_servidor,spread_m1_media,spread_m1_p50,spread_m1_p90,spread_ticks_media,"
                   "spread_m1_media_mismos_dias\n0,20,20,30,35,25\n1,20,20,30,18,20\n2,20,20,30,0,20\n")
    # hour 0: 35 - 25 = 10 points; hour 1: negative -> 0; hour 2: no ticks -> ignored; mean 5 points = 0.05 USD
    assert pr.spread_audit_extra_usd(csv, spec) == pytest.approx(0.05)
    old = tmp_path / "old.csv"
    old.write_text("hora_servidor,spread_m1_media,spread_m1_p50,spread_m1_p90,spread_ticks_media\n0,20,20,30,35\n")
    with pytest.raises(ValueError):
        pr.spread_audit_extra_usd(old, spec)
