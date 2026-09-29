"""Validation utilities."""
import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from kq.engine import BacktestConfig
from kq.strategies import scan_session_windows
from kq.validation import (EULER_GAMMA, bootstrap_ci, breakout_anchor_control, calibrate_random_entry,
                           chronological_split, deflated_sharpe_ratio, expected_max_sharpe, holm_bonferroni,
                           monkey_test, monte_carlo_trades, param_neighbourhood, probabilistic_sharpe_ratio,
                           stationary_bootstrap_indices, walk_forward, walk_forward_windows)


@pytest.mark.parametrize("anchored", [False, True])
def test_walk_forward_windows_never_overlap(anchored):
    ws = walk_forward_windows("2022-01-01", "2026-07-01", train_months=12, test_months=3, anchored=anchored)
    assert len(ws) == 14
    for w in ws:
        assert w.train_start < w.train_end <= w.test_start < w.test_end
        assert w.train_end == w.test_start
    for a, b in zip(ws, ws[1:]):
        assert a.test_end <= b.test_start                      # test windows disjoint
        assert a.test_end == b.test_start                      # and contiguous
    if anchored:
        assert len({w.train_start for w in ws}) == 1
    else:
        assert all(w.test_start - pd.DateOffset(months=12) == w.train_start for w in ws)
    assert ws[-1].test_end <= pd.Timestamp("2026-07-01")


def test_walk_forward_run_oos_trades_inside_test_windows(synth_md):
    ws = walk_forward_windows("2023-01-02", "2024-01-01", train_months=4, test_months=2)
    cfg = BacktestConfig()
    wf = walk_forward(synth_md, "TREND_DONCHIAN", {"n": [10, 20]}, cfg, ws, min_trades=3)
    tr = wf["oos_trades"]
    assert len(wf["windows"]) == len(ws) and len(tr) > 0
    for w_id, g in tr.groupby("wf_window"):
        w = ws[int(w_id)]
        assert (g.decision_time >= w.test_start).all() and (g.entry_time < w.test_end).all()
        assert (g.exit_time < w.test_end).all()
    assert wf["windows"]["chosen"].notna().all()
    assert wf["oos_metrics"]["n_trades"] == len(tr)


def test_chronological_split():
    sp = chronological_split("2022-01-01", "2026-01-01", cuts=["2025-01-01", "2025-09-01"],
                             names=["dev", "validation", "holdout"])
    assert [s.name for s in sp] == ["dev", "validation", "holdout"]
    assert sp[0].end == sp[1].start and sp[1].end == sp[2].start
    sp2 = chronological_split("2022-01-01", "2026-01-01", fractions=(0.5, 0.25, 0.25))
    assert sp2[0].end == pd.Timestamp("2024-01-01")
    with pytest.raises(ValueError):
        chronological_split("2022-01-01", "2026-01-01", cuts=["2027-01-01"])


def test_stationary_bootstrap_indices_properties():
    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(500, 200, 10.0, rng)
    assert idx.shape == (200, 500) and idx.min() >= 0 and idx.max() < 500
    # average block length ~ 10: share of positions where the index does not continue the previous
    breaks = (idx[:, 1:] != (idx[:, :-1] + 1) % 500).mean()
    assert 0.08 < breaks < 0.12
    x = np.random.default_rng(1).normal(0.001, 0.01, 750)
    ci = bootstrap_ci(x, "sharpe", n_boot=500, seed=3)
    assert ci["ci_low"] < ci["point"] < ci["ci_high"]
    assert bootstrap_ci(x, "sharpe", n_boot=500, seed=3) == ci
    m = bootstrap_ci(x, "mean", n_boot=500)
    assert m["point"] == pytest.approx(x.mean())


def test_monte_carlo_trades():
    r = np.r_[np.full(40, 1.5), np.full(60, -1.0)]
    mc = monte_carlo_trades(r, n_sims=500, method="shuffle", seed=1)
    q = mc["max_dd_pct"]
    assert q["q5"] <= q["q50"] <= q["q95"] <= q["q99"]
    assert mc["observed"]["longest_losing_streak"] == 60          # ordered sequence: all losses at the end
    assert mc["observed_percentile"]["longest_losing_streak"] == 1.0
    assert monte_carlo_trades(r, n_sims=200, method="bootstrap")["n_sims"] == 200


def test_psr_dsr_and_expected_max_sharpe():
    assert probabilistic_sharpe_ratio(0.1, 0.0, 253, 0.0, 3.0) == pytest.approx(
        sps.norm.cdf(0.1 * np.sqrt(252) / np.sqrt(1 + 0.5 * 0.01)))
    assert expected_max_sharpe(1, 1.0) == 0.0
    want = (1 - EULER_GAMMA) * sps.norm.ppf(0.99) + EULER_GAMMA * sps.norm.ppf(1 - 1 / (100 * np.e))
    assert expected_max_sharpe(100, 1.0) == pytest.approx(want)
    x = np.random.default_rng(5).normal(0.0008, 0.01, 1000)
    d1 = deflated_sharpe_ratio(x, n_trials=1)
    assert d1["dsr"] == pytest.approx(d1["psr_vs_0"])
    d100 = deflated_sharpe_ratio(x, n_trials=100)
    assert d100["dsr"] < d1["dsr"] and d100["sr_star_per_period"] > 0


def test_holm_bonferroni_known_example():
    out = holm_bonferroni([0.01, 0.04, 0.03, 0.005], alpha=0.05)
    np.testing.assert_allclose(out["p_adjusted"], [0.03, 0.06, 0.06, 0.02])
    assert list(out["reject"]) == [True, False, False, True]


def test_monkey_test_and_calibration(synth_md):
    cfg = BacktestConfig(start="2023-03-01")
    cal = calibrate_random_entry(synth_md, "REF_T0", {}, cfg)
    assert 0 < cal["p_entry"] < 1
    mt = monkey_test(synth_md, "REF_T0", {}, cfg, n_runs=4, seed=10)
    assert mt["n_random"] == 4 and 0 <= mt["real_percentile"] <= 1 and 0 < mt["p_value"] <= 1


@pytest.mark.parametrize("unconditional", [False, True])
def test_breakout_anchor_control(synth_md, unconditional):
    out = breakout_anchor_control(synth_md, {"tp_mult": 2.0}, BacktestConfig(start="2023-02-01"),
                                  n_seeds=3, unconditional=unconditional)
    assert out["n_random"] == 3 and np.isfinite(out["real"])
    assert out["variant"] == ("unconditional" if unconditional else "conditional")
    assert out["random_p95"] >= out["random_p05"]


def test_param_neighbourhood(synth_md):
    tab = param_neighbourhood(synth_md, "TREND_DONCHIAN", {"n": 20, "k_trail": 3.0},
                              {"n": [10, 20, 30], "k_trail": [2.0, 3.0]}, BacktestConfig(start="2023-03-01"))
    assert len(tab) == 1 + 2 + 1 and tab["is_base"].sum() == 1
    assert {"param.n", "param.k_trail", "expectancy_r", "t_stat_r"} <= set(tab.columns)


def test_scan_session_windows_counts_trials(synth_md):
    out = scan_session_windows(synth_md, "2023-02-01", "2023-08-01", min_obs=20)
    tab = out["table"]
    assert len(tab) == 24 * 12 * 2
    assert out["n_tried"] == int(tab["tried"].sum()) and out["n_tried"] > 400
    assert out["best"]["t_stat"] == pytest.approx(tab.loc[tab["tried"], "t_stat"].max())
    assert (tab.loc[tab["tried"], "p_holm"] >= tab.loc[tab["tried"], "p_value"]).all()
