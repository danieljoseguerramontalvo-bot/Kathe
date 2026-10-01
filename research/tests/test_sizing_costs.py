"""Position sizing, commission, swap and account units."""
import pandas as pd
import pytest

from conftest import cfg, flat_rows, make_md
from kq.costs import CostModel, floor_to_step, rollover_events
from kq.data import SymbolSpec
from kq.engine import run_backtest
from kq.strategies import Enter, Exit, make_strategy
from kq.timeutil import to_ns

T0 = "2024-01-09 10:00"   # Tuesday


def scripted(script, tf="M1"):
    return make_strategy("SCRIPTED", {"timeframe": tf, "script": script})


def ts(m):
    return pd.Timestamp(T0) + pd.Timedelta(minutes=m)


def one_trade(md, config, side=1, sl=5.0):
    return run_backtest(md, scripted({ts(1): [Enter(side, sl_dist=sl)], ts(5): [Exit()]}), config)


def test_floor_to_step_never_rounds_up():
    assert floor_to_step(0.019, 0.01) == 0.01
    assert floor_to_step(0.03, 0.01) == 0.03          # float noise 2.9999 -> still 0.03
    assert floor_to_step(0.0999, 0.01) == 0.09


def test_min_lot_skip_instead_of_rounding_up():
    md = make_md(flat_rows(T0, 10, spread=0))
    res = one_trade(md, cfg(risk_pct=1.0, fixed_lots=None, initial_equity=100.0))
    assert len(res.trades) == 0
    sk = res.skipped.iloc[0]
    assert sk.kind == "sizing" and sk.reason == "min_lot_exceeds_risk"
    assert res.equity[-1] == pytest.approx(100.0)


def test_risk_sizing_floors_to_step_and_includes_commission():
    md = make_md(flat_rows(T0, 10, spread=0))
    # 950 * 1% = 9.5; loss per lot at a 5.00 stop = 500 -> 0.019 lots -> 0.01 (floored)
    tr = one_trade(md, cfg(risk_pct=1.0, fixed_lots=None, initial_equity=950.0)).trades.iloc[0]
    assert tr.lots == pytest.approx(0.01)
    # 10000 * 1% = 100; loss per lot = 2.00 * 100 + 7 commission = 207 -> 0.483 -> 0.48
    tr = one_trade(md, cfg(risk_pct=1.0, fixed_lots=None, costs=CostModel(commission_per_lot_rt=7.0)),
                   sl=2.0).trades.iloc[0]
    assert tr.lots == pytest.approx(0.48)
    assert tr.risk_money == pytest.approx(0.48 * 207)


def test_volume_max_cap_is_logged():
    md = make_md(flat_rows(T0, 10, spread=0), SymbolSpec(volume_max=0.5))
    res = one_trade(md, cfg(risk_pct=1.0, fixed_lots=None, initial_equity=1e6))
    assert res.trades.iloc[0].lots == 0.5
    assert "capped_at_volume_max" in set(res.skipped.reason)


def test_r_multiple_full_stop_is_minus_one_and_costs_reduce_it():
    rows = flat_rows(T0, 20, spread=0)
    for r in rows[6:]:
        r[1:5] = [1990.0] * 4
    rows[5][3] = 1994.0          # bar 10:05 trades through the 1995.00 stop
    md = make_md(rows)
    s = scripted({ts(1): [Enter(1, sl_dist=5.0)]})
    tr = run_backtest(md, s, cfg()).trades.iloc[0]
    assert tr.exit_reason == "sl" and tr.r_net == pytest.approx(-1.0) and tr.r_gross == pytest.approx(-1.0)
    s = scripted({ts(1): [Enter(1, sl_dist=5.0)]})
    tr = run_backtest(md, s, cfg(costs=CostModel(commission_per_lot_rt=10.0))).trades.iloc[0]
    assert tr.r_net == pytest.approx(-1.0 - 10.0 / (1 * 100 * 5.0))
    assert tr.net_pnl == pytest.approx(-500.0 - 10.0)


def _hourly_rows(start, end, price=2000.0, spread=0):
    t = pd.date_range(start, end, freq="1h")
    return [[x, price, price, price, price, spread] for x in t if x.dayofweek < 5 and x.hour >= 1]


def test_commission_and_swap_accounting_with_triple_wednesday():
    spec = SymbolSpec(swap_long=-50.0, swap_short=20.0, swap_3days=3)      # MT5: 3 = Wednesday
    md = make_md(_hourly_rows("2024-01-09 01:00", "2024-01-12 23:00"), spec)
    script = {"2024-01-09 10:00": [Enter(1, sl_dist=10.0)], "2024-01-12 10:00": [Exit()]}
    costs = CostModel(commission_per_lot_rt=7.0, apply_swap=True)
    res = run_backtest(md, scripted(script, "H1"), cfg(fixed_lots=0.5, costs=costs))
    tr = res.trades.iloc[0]
    # nights ending Tue (x1), Wed (x3), Thu (x1) = 5 nights * 0.5 lot * (-50 pts * 0.01 * 100)
    assert tr.swap == pytest.approx(-125.0)
    assert tr.commission == pytest.approx(3.5)
    assert tr.gross_pnl == pytest.approx(0.0)
    assert tr.net_pnl == pytest.approx(-128.5)
    assert res.equity[-1] == pytest.approx(10_000 - 128.5)
    # swap accrues in equity at the first bar after each rollover
    t_wed = to_ns("2024-01-10 01:00")
    j = int((md.t == t_wed).nonzero()[0][0])
    assert res.equity[j] == pytest.approx(10_000 - 3.5 - 25.0)


def test_weekend_is_one_night_and_short_swap_sign():
    spec = SymbolSpec(swap_long=-50.0, swap_short=20.0, swap_3days=3)
    md = make_md(_hourly_rows("2024-01-12 01:00", "2024-01-15 23:00"), spec)     # Fri -> Mon
    script = {"2024-01-12 10:00": [Enter(-1, sl_dist=10.0)], "2024-01-15 10:00": [Exit()]}
    res = run_backtest(md, scripted(script, "H1"), cfg(fixed_lots=0.5, costs=CostModel(apply_swap=True)))
    assert res.trades.iloc[0].swap == pytest.approx(+10.0)                        # 1 night * 0.5 * 20


def test_rollover_events_rule():
    tw = 2        # Python weekday of Wednesday
    ev = rollover_events(to_ns("2024-01-09 10:00"), to_ns("2024-01-12 10:00"), tw)
    assert [m for _, m in ev] == [1, 3, 1]
    assert rollover_events(to_ns("2024-01-09 10:00"), to_ns("2024-01-09 23:00"), tw) == []


def test_cent_account_scales_money_but_not_r():
    md = make_md(flat_rows(T0, 10, spread=0))
    rows = flat_rows(T0, 10, spread=0)
    for r in rows[5:]:
        r[1:5] = [2001.0] * 4
    md = make_md(rows)
    usd = one_trade(md, cfg(fixed_lots=0.1)).trades.iloc[0]
    usc = one_trade(md, cfg(fixed_lots=0.1, account_units_per_usd=100.0, initial_equity=1_000_000)).trades.iloc[0]
    assert usd.gross_pnl == pytest.approx(0.1 * 100 * 1.0)
    assert usc.gross_pnl == pytest.approx(usd.gross_pnl * 100)
    assert usc.r_net == pytest.approx(usd.r_net)
    assert SymbolSpec(account_currency="USC").default_units_per_usd() == 100.0


def test_risk_sizing_is_size_invariant_in_r():
    rows = flat_rows(T0, 10, spread=10)
    for r in rows[5:]:
        r[1:5] = [2003.0] * 4
    md = make_md(rows)
    a = one_trade(md, cfg(risk_pct=1.0, fixed_lots=None, initial_equity=10_000)).trades.iloc[0]
    b = one_trade(md, cfg(risk_pct=2.0, fixed_lots=None, initial_equity=50_000)).trades.iloc[0]
    assert b.lots > a.lots
    assert a.r_net == pytest.approx(b.r_net)


def test_commission_from_mt5_audit_field_uses_absolute_value():
    from kq.costs import commission_rt_from_spec
    spec = SymbolSpec.from_dict({"symbol": "XAUUSD", "commission_per_lot_side_observed": -3.5})
    assert commission_rt_from_spec(spec) == pytest.approx(7.0)
    assert commission_rt_from_spec(SymbolSpec()) is None
