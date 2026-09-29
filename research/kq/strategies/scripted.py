"""SCRIPTED — deterministic actions at given decision times (engine tests and debugging).

``script`` is either a callable ``f(ctx) -> list[action]`` or a dict mapping a decision time
(bar CLOSE time, server; str/Timestamp) to a list of actions.
"""
from __future__ import annotations

import pandas as pd

from ..timeutil import to_ns
from .base import Strategy


class Scripted(Strategy):
    name = "SCRIPTED"
    default_params = {"timeframe": "M1", "script": None, "max_positions": 1}

    def __init__(self, **params):
        super().__init__(**params)
        self.max_positions = int(self.params["max_positions"])

    def prepare(self, md):
        super().prepare(md)
        s = self.params["script"]
        self._fn = s if callable(s) else None
        self._map = {} if callable(s) or s is None else {to_ns(pd.Timestamp(k)): list(v) for k, v in s.items()}
        self.contexts = []

    def on_bar(self, ctx):
        self.stats["decisions"] += 1
        self.contexts.append(ctx)
        if self._fn is not None:
            return list(self._fn(ctx) or [])
        return list(self._map.get(ctx.decision_time, []))
