"""Strategy registry and factory.

``make_strategy(name, params)`` builds a strategy; a ``"regime_gate": {...}`` entry in
``params`` wraps it in :class:`RegimeGate`. Benchmarks (``BUY_HOLD``,
``BUY_HOLD_VOLSCALED``) are not engine strategies: see :mod:`kq.benchmark`.
"""
from __future__ import annotations

from .base import (BarContext, Enter, Exit, PositionView, SetStop, Skip, Strategy)
from .random_entry import RandomEntry
from .ref_rsi2 import RefRsi2
from .ref_t0 import RefT0
from .regime import RegimeGate, regime_series
from .order_block import OrderBlock
from .scripted import Scripted
from .session_breakout import SessionBreakout
from .session_drift import SessionDrift, scan_session_windows
from .trend_donchian import TrendDonchian

STRATEGIES = {cls.name: cls for cls in (RefT0, RefRsi2, TrendDonchian, SessionBreakout,
                                        SessionDrift, OrderBlock, RandomEntry, Scripted)}
BENCHMARKS = ("BUY_HOLD", "BUY_HOLD_VOLSCALED")


def make_strategy(name: str, params: dict | None = None) -> Strategy:
    params = dict(params or {})
    gate = params.pop("regime_gate", None)
    key = str(name).upper()
    if key not in STRATEGIES:
        raise ValueError(f"unknown strategy {name!r}; available: {sorted(STRATEGIES)} "
                         f"(benchmarks: {BENCHMARKS})")
    strat = STRATEGIES[key](**params)
    if gate:
        strat = RegimeGate(strat, **(gate if isinstance(gate, dict) else {}))
    return strat


__all__ = ["STRATEGIES", "BENCHMARKS", "make_strategy", "Strategy", "BarContext", "Enter", "Exit",
           "SetStop", "Skip", "PositionView", "RefT0", "RefRsi2", "TrendDonchian", "SessionBreakout",
           "SessionDrift", "OrderBlock", "RandomEntry", "RegimeGate", "Scripted", "scan_session_windows",
           "regime_series"]
