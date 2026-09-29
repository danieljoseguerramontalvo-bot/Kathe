"""Benchmarks."""
import numpy as np
import pytest

from kq.benchmark import buy_and_hold_returns, buy_hold_volscaled, exposure_matched_long, regression_vs
from kq.costs import CostModel
from kq.data import last_closed_index
from kq.engine import BacktestConfig, in_minute_window, run_backtest
from kq.indicators import atr_mt5
from kq.strategies import make_strategy


def test_buy_hold_volscaled_sizing_costs_and_timing(synth_md):
    costs = CostModel(commission_per_lot_rt=7.0, slippage_points=5, apply_swap=True)
    out = buy_hold_volscaled(synth_md, "2023-02-01", "2024-01-01", costs, initial_equity=10_000)
    f = out["fills"]
    assert len(f) > 20 and out["metrics"]["total_costs"] > 0 and out["metrics"]["total_swap"] < 0
    # never rebalanced inside the rollover window
    t = f["time"].to_numpy("datetime64[ns]").astype("int64")
    assert not in_minute_window(t, 1425, 75).any()
    # first fill: lots = 1 % of equity per ATR14(D1) move (nearest volume step)
    d1 = synth_md.bars("D1")
    atr = atr_mt5(d1.high.to_numpy(), d1.low.to_numpy(), d1.close.to_numpy(), 14)
    k = int(last_closed_index(d1.close_time_ns.to_numpy(), t[0]))
    want = round(0.01 * 10_000 / (atr[k] * 100), 2)
    assert f.lots_after.iloc[0] == pytest.approx(want, abs=0.011)
    assert f.atr_d1.iloc[0] == pytest.approx(atr[k])
    free = buy_hold_volscaled(synth_md, "2023-02-01", "2024-01-01", CostModel(spread_multiplier=0.0))
    assert free["metrics"]["total_costs"] == 0.0
    assert free["metrics"]["final_equity"] > out["metrics"]["final_equity"]


def test_exposure_matched_and_regression(synth_md):
    res = run_backtest(synth_md, make_strategy("TREND_DONCHIAN", {}), BacktestConfig(start="2023-03-01"))
    em = exposure_matched_long(synth_md, res)
    bh = buy_and_hold_returns(synth_md, "2023-03-01", "2024-01-01")
    assert len(em) == len(bh)
    # a strategy that is never in the market earns nothing in the matched benchmark
    res.in_pos[:] = False
    assert np.allclose(exposure_matched_long(synth_md, res).to_numpy(), 0.0)
    reg = regression_vs(bh * 2.0 + 0.0001, bh)
    assert reg["beta"] == pytest.approx(2.0) and reg["alpha_daily"] == pytest.approx(0.0001)
