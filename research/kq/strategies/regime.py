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

    def regime_at(self, t_ns):
        """(is_trend or None, vol_tercile or None) from the last D1 bar closed at t_ns."""
        k = int(last_closed_index(self.reg["close_time_ns"], t_ns))
        if k < 0 or not np.isfinite(self.reg["er"][k]) or not np.isfinite(self.reg["vol_tercile"][k]):
            return None, None
        return bool(self.reg["is_trend"][k]), int(self.reg["vol_tercile"][k])

    def on_bar(self, ctx):
        acts = self.inner.on_bar(ctx)
        if not any(isinstance(a, Enter) for a in acts):
            return acts
        is_trend, terc = self.regime_at(ctx.decision_time)
        reason = None
        if is_trend is None:
            reason = "regime_warmup"
        else:
            want = self.params["allow_regime"]
            if want == "trend" and not is_trend:
                reason = "regime_not_trend"
            elif want == "range" and is_trend:
                reason = "regime_not_range"
            elif terc not in set(self.params["allow_vol"]):
                reason = f"regime_vol_tercile_{terc}"
        if reason is None:
            return acts
        self.stats["regime_blocked"] += 1
        return [Skip(a.side, reason) if isinstance(a, Enter) else a for a in acts]
