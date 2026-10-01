"""Past-only regime classifier and a gate wrapper usable with any strategy.

Regime at decision time T is read from the last CLOSED D1 (server) bar:
* trend if ER(D1 close, er_period) >= er_threshold, else range;
* volatility tercile 0/1/2 (low/mid/high) from the past-only percentile rank of
  ATR(D1, atr_period) among the previous ``pct_window`` daily values.
The gate only blocks NEW entries (turned into Skip 'regime_*'); exits and stop management
of the inner strategy pass through unchanged.
"""
from __future__ import annotations

import numpy as np

from ..data import last_closed_index
from ..indicators import atr_mt5, efficiency_ratio, rolling_percentile_rank
from .base import Enter, Skip, Strategy


def regime_series(md, er_period=20, er_threshold=0.3, atr_period=14, pct_window=250) -> dict:
    d1 = md.bars("D1")
    c = d1["close"].to_numpy(float)
    er = efficiency_ratio(c, er_period)
    atr = atr_mt5(d1["high"].to_numpy(float), d1["low"].to_numpy(float), c, atr_period)
    pct = rolling_percentile_rank(atr, pct_window)
    terc = np.full(len(pct), np.nan)
    ok = np.isfinite(pct)
    terc[ok] = np.minimum(np.floor(pct[ok] * 3.0), 2.0)
    trend = np.where(np.isfinite(er), er >= er_threshold, False)
    return {"close_time_ns": d1["close_time_ns"].to_numpy("int64"), "er": er, "atr": atr,
            "atr_pct": pct, "vol_tercile": terc, "is_trend": trend, "time": d1.index}


class RegimeGate(Strategy):
    name = "REGIME_GATE"
    default_params = {
        "er_period": 20,
        "er_threshold": 0.3,
        "atr_period": 14,
        "pct_window": 250,
        "allow_regime": "any",       # 'trend' | 'range' | 'any'
        "allow_vol": [0, 1, 2],      # volatility terciles allowed
    }

    def __init__(self, inner: Strategy, **params):
        super().__init__(**params)
        if self.params["allow_regime"] not in ("trend", "range", "any"):
            raise ValueError("allow_regime must be 'trend', 'range' or 'any'")
        self.inner = inner
        self.name = f"{inner.name}"
        self.max_positions = inner.max_positions

    @property
    def timeframe(self):
        return self.inner.timeframe

    def describe(self):
        d = self.inner.describe()
        d["params"] = dict(d["params"])
        d["params"]["regime_gate"] = dict(self.params)
        d["name"] = self.inner.name
        return d

    def prepare(self, md):
        self.inner.prepare(md)
        self.md = md
        self.bars = self.inner.bars
        p = self.params
        self.reg = regime_series(md, p["er_period"], p["er_threshold"], p["atr_period"], p["pct_window"])
        self.stats = self.inner.stats
        self.stats["regime_blocked"] = 0

    def decision_times(self):
        return self.inner.decision_times()

    def _needs_trend(self) -> bool:
        return self.params["allow_regime"] != "any"

    def _needs_vol(self) -> bool:
        return set(int(v) for v in self.params["allow_vol"]) != {0, 1, 2}

    def regime_at(self, t_ns):
        """(is_trend or None, vol_tercile or None) from the last D1 bar closed at t_ns.
        Only the components the gate actually uses need to be warmed up: an ER-only gate does
        not wait for the 250-day ATR percentile (EA parity), and a volatility-only gate does
        not wait for the ER."""
        k = int(last_closed_index(self.reg["close_time_ns"], t_ns))
        if k < 0:
            return None, None
        er_ok = np.isfinite(self.reg["er"][k])
        vol_ok = np.isfinite(self.reg["vol_tercile"][k])
        if (self._needs_trend() and not er_ok) or (self._needs_vol() and not vol_ok):
            return None, None
        is_trend = bool(self.reg["is_trend"][k]) if er_ok else False
        terc = int(self.reg["vol_tercile"][k]) if vol_ok else -1
        return is_trend, terc

    def block_reason(self, t_ns):
        """None if the regime allows a NEW entry at ``t_ns``, else the skip reason."""
        is_trend, terc = self.regime_at(t_ns)
        if is_trend is None:
            return "regime_warmup"
        want = self.params["allow_regime"]
        if want == "trend" and not is_trend:
            return "regime_not_trend"
        if want == "range" and is_trend:
            return "regime_not_range"
        if self._needs_vol() and terc not in set(int(v) for v in self.params["allow_vol"]):
            return f"regime_vol_tercile_{terc}"
        return None

    # --- delegation, so that wrappers such as RANDOM_ENTRY see the inner strategy's rules
    def ready(self, i):
        return self.inner.ready(i)

    def signal(self, i):
        return self.inner.signal(i)

    def entry_block_reason(self, ctx, side):
        return self.inner.entry_block_reason(ctx, side) or self.block_reason(ctx.decision_time)

    def entry_window_ok(self, ctx):
        """Random entries face the same regime as the real ones."""
        return self.inner.entry_window_ok(ctx) and self.block_reason(ctx.decision_time) is None

    def stops(self, ctx, side):
        return self.inner.stops(ctx, side)

    def random_stops(self, ctx, side):
        f = getattr(self.inner, "random_stops", None)
        return f(ctx, side) if f else self.inner.stops(ctx, side)

    def manage(self, ctx, pos):
        return self.inner.manage(ctx, pos)

    def on_enter(self, ctx, side):
        self.inner.on_enter(ctx, side)

    @property
    def rule_params(self) -> dict:
        """Parameters of the wrapped strategy (close_on_opposite, max_spread_points...)."""
        return self.inner.params

    def on_bar(self, ctx):
        st = self.inner.stats
        eligible_before = st.get("flat_eligible_decisions", 0)
        acts = self.inner.on_bar(ctx)
        reason = self.block_reason(ctx.decision_time)
        if reason is not None and st.get("flat_eligible_decisions", 0) > eligible_before:
            # keep the random-entry calibration comparable: a decision blocked by the regime
            # is not an eligible entry opportunity
            st["flat_eligible_decisions"] = eligible_before
        if reason is None or not any(isinstance(a, Enter) for a in acts):
            return acts
        n_blocked = sum(isinstance(a, Enter) for a in acts)
        st["regime_blocked"] = st.get("regime_blocked", 0) + n_blocked
        st["entries_emitted"] = st.get("entries_emitted", 0) - n_blocked
        return [Skip(a.side, reason) if isinstance(a, Enter) else a for a in acts]
