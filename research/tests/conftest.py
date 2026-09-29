import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kq.costs import CostModel  # noqa: E402
from kq.data import MarketData, SymbolSpec  # noqa: E402
from kq.engine import BacktestConfig  # noqa: E402
from kq.synth import generate_m1  # noqa: E402


def make_md(rows, spec=None) -> MarketData:
    """rows: iterable of (time, open, high, low, close, spread_points)."""
    rows = list(rows)
    idx = pd.DatetimeIndex([pd.Timestamp(r[0]) for r in rows]).as_unit("ns")
    df = pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows],
                       "close": [r[4] for r in rows], "tick_volume": 1.0,
                       "spread": [float(r[5]) for r in rows], "real_volume": 0.0}, index=idx)
    return MarketData(df, spec or SymbolSpec())


def flat_rows(start, n, price=2000.0, spread=20, step="1min"):
    t = pd.date_range(start, periods=n, freq=step)
    return [[ts, price, price, price, price, spread] for ts in t]


def cfg(**kw) -> BacktestConfig:
    """Test config: fixed 1 lot, no costs, rollover window disabled unless given."""
    base = dict(risk_pct=None, fixed_lots=1.0, costs=CostModel(), rollover_from_min=0, rollover_to_min=0)
    base.update(kw)
    return BacktestConfig(**base)


@pytest.fixture(scope="session")
def synth_md():
    """One year of synthetic gold-like M1 data (~360k bars) with mild trend regimes."""
    df = generate_m1("2023-01-02", "2024-01-01", seed=7, trend_regime_annual=0.3)
    return MarketData(df, SymbolSpec(swap_long=-45.0, swap_short=20.0))


@pytest.fixture(scope="session")
def synth_df():
    return generate_m1("2023-01-02", "2024-01-01", seed=7, trend_regime_annual=0.3)


def perturb_after(md: MarketData, cut, seed=0) -> MarketData:
    """Copy of md where every M1 bar at or after ``cut`` is changed (prices and spreads)."""
    m = md.m1.copy()
    mask = m.index >= pd.Timestamp(cut)
    rng = np.random.default_rng(seed)
    k = int(mask.sum())
    shift = np.cumsum(rng.normal(0, 0.8, k)) + 15.0
    for c in ("open", "high", "low", "close"):
        m.loc[mask, c] = np.round(m.loc[mask, c].to_numpy() * 1.01 + shift, 2)
    m.loc[mask, "spread"] = m.loc[mask, "spread"].to_numpy() + 7
    return MarketData(m, md.spec)
