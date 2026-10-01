import numpy as np
import pandas as pd

from kq.costs import CostModel
from kq.data import MarketData, SymbolSpec
from kq.engine import BacktestConfig, run_backtest
from kq.indicators import atr_mt5
from kq.strategies import make_strategy
from kq.strategies.order_block import order_block_signals
from kq.synth import generate_m1


def test_bullish_order_block_hand_built():
    #        0     1     2     3     4     5     6     7     8     9
    o = np.array([10.0, 10.0, 10.8, 11.5, 11.0, 10.4, 10.1, 12.5, 12.2, 11.2])
    h = np.array([10.5, 11.0, 12.0, 11.6, 11.2, 10.6, 12.6, 12.8, 12.3, 11.3])
    l = np.array([9.5, 9.8, 10.5, 10.8, 10.2, 10.0, 10.1, 12.0, 11.0, 10.5])
    c = np.array([10.0, 10.8, 11.5, 11.0, 10.4, 10.1, 12.5, 12.2, 11.2, 10.9])
    atr = np.ones(10)
    sig, stop, top, bot = order_block_signals(o, h, l, c, atr, swing_w=2, lookback=10, disp_atr=1.5,
                                              max_age_bars=96, near_atr=0.5, sl_buffer_atr=0.1)
    # máximo de swing 12.0 (vela 2), ruptura en la 6, order block = vela bajista 5 [10.0, 10.6],
    # primera vuelta a la zona en la 9 -> compra con stop bajo la zona
    assert list(np.nonzero(sig)[0]) == [9] and sig[9] == 1
    assert top[9] == 10.6 and bot[9] == 10.0 and abs(stop[9] - 9.9) < 1e-12


def test_zone_is_used_once_and_invalidated_by_a_close_through_it():
    o = np.array([10.0, 10.0, 10.8, 11.5, 11.0, 10.4, 10.1, 12.5, 12.2, 11.2, 10.9, 10.8])
    h = np.array([10.5, 11.0, 12.0, 11.6, 11.2, 10.6, 12.6, 12.8, 12.3, 11.3, 11.0, 10.9])
    l = np.array([9.5, 9.8, 10.5, 10.8, 10.2, 10.0, 10.1, 12.0, 11.0, 9.8, 10.5, 10.4])
    c = np.array([10.0, 10.8, 11.5, 11.0, 10.4, 10.1, 12.5, 12.2, 11.2, 9.9, 10.8, 10.5])
    sig, *_ = order_block_signals(o, h, l, c, np.ones(12), swing_w=2, disp_atr=1.5)
    assert not (sig > 0).any()      # la vela 9 cierra por debajo de la zona alcista: se invalida, sin compras


def test_no_lookahead_signals_on_random_data():
    rng = np.random.default_rng(3)
    n = 800
    c = 2000 + np.cumsum(rng.normal(0, 2, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 2, n)
    l = np.minimum(o, c) - rng.uniform(0, 2, n)
    atr = atr_mt5(h, l, c, 14)
    full = order_block_signals(o, h, l, c, atr)
    assert full[0].any()
    for i in range(50, n, 37):
        part = order_block_signals(o[:i + 1], h[:i + 1], l[:i + 1], c[:i + 1], atr[:i + 1])
        assert part[0][i] == full[0][i]
        assert (np.isnan(part[1][i]) and np.isnan(full[1][i])) or part[1][i] == full[1][i]


def test_order_block_runs_in_the_engine_with_correct_stops():
    df = generate_m1("2026-08-03", "2026-09-04", seed=5)
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].round(1)
    df["spread"] = 1                                                   # futuros: 1 tick, como en el bot
    spec = SymbolSpec(symbol="MGC", digits=1, point=0.1, tick_size=0.1, tick_value=1.0, contract_size=10.0,
                      volume_min=1, volume_max=5, volume_step=1)
    md = MarketData(df, spec)
    cfg = BacktestConfig(initial_equity=50000, risk_pct=None, fixed_lots=1.0,
                         costs=CostModel(slippage_points=1, commission_per_lot_rt=1.5), max_spread_points=0.0)
    res = run_backtest(md, make_strategy("ORDER_BLOCK", {}), cfg)
    tr = res.trades
    assert len(tr) > 0
    longs, shorts = tr[tr["side"] > 0], tr[tr["side"] < 0]
    assert (longs["initial_stop"] < longs["entry_price"]).all() and (shorts["initial_stop"] > shorts["entry_price"]).all()
    ratio = (tr["initial_tp"] - tr["entry_price"]) / (tr["entry_price"] - tr["initial_stop"])
    assert ratio.median() > 1.7 and ratio.min() > 1.0                   # objetivo ≈ 2 veces el riesgo real (menos costes)
