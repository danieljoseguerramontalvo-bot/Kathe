"""Metrics on known inputs."""
import numpy as np
import pandas as pd
import pytest

from kq.engine import BacktestConfig, run_backtest
from kq.metrics import (break_even_cost, cagr, compute_metrics, concentration, cost_stress, drawdown_stats,
                        max_consecutive, profit_factor, t_stat, trade_metrics)
from kq.strategies import make_strategy


def _trades(pnl, r, lots=None, r_price=None):
    n = len(pnl)
    t = pd.date_range("2024-01-02 10:00", periods=n, freq="D")
    return pd.DataFrame({
        "net_pnl": pnl, "r_net": r, "lots": lots if lots is not None else [1.0] * n,
        "r_price": r_price if r_price is not None else [1.0] * n, "commission": 0.0, "swap": 0.0,
        "hold_minutes": 60.0, "exit_reason": "sl", "side": 1, "entry_time": t, "entry_time_utc": t,
    })


def test_profit_factor_tstat_and_streaks_on_known_list():
    pnl = [100.0, -50.0, 200.0, -100.0, 50.0]
    r = [1.0, -0.5, 2.0, -1.0, 0.5]
    m = trade_metrics(_trades(pnl, r))
    assert m["profit_factor"] == pytest.approx(350 / 150)
    assert m["win_rate"] == pytest.approx(0.6)
    assert m["expectancy"] == pytest.approx(40.0)
    assert m["expectancy_r"] == pytest.approx(0.4)
    sd = np.std(r, ddof=1)
    assert m["sd_r"] == pytest.approx(sd)
    assert m["t_stat_r"] == pytest.approx(0.4 / (sd / np.sqrt(5)))
    assert m["avg_win"] == pytest.approx(350 / 3) and m["avg_loss"] == pytest.approx(-75.0)
    assert max_consecutive([False, True, True, False, True, True, True]) == 3
    assert profit_factor([1, 2]) == float("inf") and np.isnan(profit_factor([]))
    assert np.isnan(t_stat([1.0]))


def test_drawdown_on_known_equity():
    eq = np.array([100, 110, 99, 105, 121, 90, 95], float)
    t = pd.date_range("2024-01-01", periods=7, freq="D").as_unit("ns").asi8
    d = drawdown_stats(eq, t, 100.0)
    assert d["max_dd_pct"] == pytest.approx((121 - 90) / 121 * 100)
    assert d["max_dd_money"] == pytest.approx(31.0)
    assert d["max_dd_peak_time"] == "2024-01-05 00:00:00"
    assert d["max_dd_trough_time"] == "2024-01-06 00:00:00"
    assert d["max_dd_recovered"] is False and d["time_to_recovery_days"] is None
    # underwater spells: 01-02 -> 01-05 (3 days) and 01-05 -> end (2 days, unrecovered)
    assert d["longest_dd_days"] == pytest.approx(3.0)
    eq2 = np.array([100, 90, 95, 101, 100], float)
    d2 = drawdown_stats(eq2, t[:5], 100.0)
    assert d2["max_dd_recovered"] and d2["time_to_recovery_days"] == pytest.approx(2.0)
    assert d2["max_dd_duration_days"] == pytest.approx(3.0)


def test_cost_stress_and_break_even():
    tr = _trades([50.0, -20.0, 30.0], [0.5, -0.2, 0.3], lots=[1.0, 1.0, 1.0], r_price=[1.0, 1.0, 1.0])
    # point 0.01, 100 per price per lot -> 10 points = 0.10 * 100 = 10 money per trade
    cs = cost_stress(tr, 0.01, 100.0, (10,))
    assert cs["+10pts"]["net_profit"] == pytest.approx(60.0 - 30.0)
    assert cs["+10pts"]["expectancy_r"] == pytest.approx(0.2 - 0.1)
    be = break_even_cost(tr, 0.01, 100.0)
    assert be["break_even_extra_points_money"] == pytest.approx(60.0 / (0.01 * 100 * 3))
    assert be["break_even_extra_points_r"] == pytest.approx(0.2 / 0.01)
    # at the break-even cost the expectancy is zero
    cs2 = cost_stress(tr, 0.01, 100.0, (be["break_even_extra_points_r"],))
    assert list(cs2.values())[0]["expectancy_r"] == pytest.approx(0.0, abs=1e-12)


def test_concentration_and_cagr():
    tr = _trades([100.0, 50.0, 10.0, -60.0, 5.0, 3.0, 2.0], [0.0] * 7)
    c = concentration(tr, pd.Series([100.0, -60.0, 70.0]))
    assert c["top5_trades_share_of_net"] == pytest.approx((100 + 50 + 10 + 5 + 3) / 110)
    assert c["top5_days_share_of_net"] == pytest.approx(110 / 110)
    assert cagr(100, 121, 2 * 365.25) == pytest.approx(0.1)
    assert cagr(100, -5, 100) == -1.0


def test_compute_metrics_full_report(synth_md):
    res = run_backtest(synth_md, make_strategy("REF_T0", {}), BacktestConfig(start="2023-03-01"))
    m = compute_metrics(res, md=synth_md)
    for k in ("n_trades", "win_rate", "profit_factor", "expectancy", "expectancy_r", "sd_r", "t_stat_r",
              "sharpe_ann", "cagr", "max_dd_pct", "max_dd_intrabar_pct", "longest_dd_days", "max_consecutive_losses",
              "by_year", "by_side", "by_entry_hour_utc", "exposure_pct", "top5_trades_share_of_net",
              "cost_stress", "skipped_by_reason", "break_even_extra_points_r", "long_net_profit",
              "short_net_profit", "benchmarks", "return_by_year_pct"):
        assert k in m, k
    assert m["max_dd_intrabar_pct"] >= m["max_dd_pct"] - 1e-9
    assert m["long_net_profit"] + m["short_net_profit"] == pytest.approx(m["net_profit"])
    assert set(m["cost_stress"]) == {"+10pts", "+20pts", "+40pts"}
    b = m["benchmarks"]
    assert {"buy_hold", "buy_hold_volscaled", "exposure_matched_long", "strategy_vs_buy_hold_volscaled"} <= set(b)
    assert m["final_equity"] == pytest.approx(res.initial_equity + res.trades.net_pnl.sum())
