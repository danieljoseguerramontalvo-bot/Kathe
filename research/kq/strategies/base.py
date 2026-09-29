"""Strategy interface.

A strategy is called once per *decision time*: by default the close of each bar of its
timeframe (a bar that opens at t with length L is closed at t + L). It may only use data of
bars that are closed at that time. It returns a list of actions that the engine executes at
the OPEN of the first M1 bar with time >= decision time:

* ``Enter``   open a position (stop/target given as distances from the quoted entry price or
              as absolute levels);
* ``Exit``    close positions at that M1 open;
* ``SetStop`` move a stop (the engine only accepts tightening moves), effective from that M1
              bar onwards;
* ``Skip``    log a signal that a filter discarded (no trade).

The default ``on_bar`` composes four hooks that subclasses override:
``signal(i)`` (raw direction from closed bar i), ``entry_block_reason(ctx, side)`` (filters),
``stops(ctx, side)`` (initial SL/TP) and ``manage(ctx, pos)`` (trailing / exits).
Keeping them separate lets RANDOM_ENTRY reuse the exits of any target strategy.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..data import MarketData


# ---------------------------------------------------------------------------- actions
@dataclass(frozen=True)
class Enter:
    side: int                              # +1 long, -1 short
    sl_dist: float | None = None           # stop distance (price) from the quoted entry price
    sl_price: float | None = None          # or an absolute stop level
    tp_dist: float | None = None           # target distance (price) from the quoted entry price
    tp_price: float | None = None          # or an absolute target level
    tag: str = ""
    max_spread_points: float | None = None  # wait (until the next decision) for spread <= this


@dataclass(frozen=True)
class Exit:
    position_id: int | None = None         # None = every position (optionally only ``side``)
    side: int | None = None
    reason: str = "signal"


@dataclass(frozen=True)
class SetStop:
    position_id: int
    price: float
    reason: str = "trail"


@dataclass(frozen=True)
class Skip:
    side: int
    reason: str
    kind: str = "filter"


@dataclass(frozen=True)
class PositionView:
    """Read-only snapshot of an open position given to strategies."""

    id: int
    side: int
    lots: float
    entry_index: int          # M1 index of the entry bar
    entry_time: int           # ns, server
    entry_time_utc: int       # ns, UTC
    entry_price: float        # fill price (incl. spread and slippage)
    stop: float | None
    tp: float | None
    initial_stop: float | None
    decision_index: int       # decision index that opened it
    tag: str = ""


@dataclass
class BarContext:
    i: int                    # decision index (= bar index of the closed bar for bar strategies)
    decision_time: int        # ns server (close time of bar i)
    decision_time_utc: int    # ns UTC
    exec_index: int           # M1 index where actions execute
    exec_time: int            # ns server of that M1 bar
    positions: list = field(default_factory=list)
    balance: float = 0.0
    md: MarketData | None = None


# ---------------------------------------------------------------------------- base class
class Strategy:
    name = "BASE"
    default_params: dict = {}
    max_positions = 1

    def __init__(self, **params):
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unknown parameters {sorted(unknown)}; "
                             f"valid: {sorted(self.default_params)}")
        self.params = copy.deepcopy(self.default_params)
        self.params.update(params)
        self.stats = {}
        self.md: MarketData | None = None
        self.bars: pd.DataFrame | None = None

    # ------------------------------------------------------------------ description
    @property
    def timeframe(self) -> str:
        return str(self.params.get("timeframe", "H4")).upper()

    def describe(self) -> dict:
        return {"name": self.name, "timeframe": self.timeframe, "params": _jsonable(self.params)}

    # ------------------------------------------------------------------ lifecycle
    def prepare(self, md: MarketData) -> None:
        """Compute indicators (past-only) and reset state. Subclasses call super()."""
        self.md = md
        self.bars = md.bars(self.timeframe)
        self.b_open = self.bars["open"].to_numpy(float)
        self.b_high = self.bars["high"].to_numpy(float)
        self.b_low = self.bars["low"].to_numpy(float)
        self.b_close = self.bars["close"].to_numpy(float)
        self.b_spread = self.bars["spread"].to_numpy(float)
        self.b_m1_start = self.bars["m1_start"].to_numpy()
        self.stats = {"decisions": 0, "flat_eligible_decisions": 0, "entries_emitted": 0}

    def decision_times(self) -> np.ndarray:
        """Decision times (int64 ns server, sorted). Default: close time of every bar."""
        return self.bars["close_time_ns"].to_numpy(dtype="int64")

    def bar_index_of_m1(self, j: int) -> int:
        """Index of the strategy-TF bar that contains M1 bar ``j``."""
        return int(np.searchsorted(self.b_m1_start, j, side="right") - 1)

    # ------------------------------------------------------------------ hooks
    def ready(self, i: int) -> bool:
        return True

    def signal(self, i: int) -> int:
        return 0

    def entry_block_reason(self, ctx: BarContext, side: int) -> str | None:
        return None

    def entry_window_ok(self, ctx: BarContext) -> bool:
        """Whether a (random) entry is allowed at this decision regardless of direction."""
        return True

    def stops(self, ctx: BarContext, side: int) -> dict | None:
        return None

    def manage(self, ctx: BarContext, pos: PositionView) -> list:
        return []

    def on_enter(self, ctx: BarContext, side: int) -> None:
        """Called when an Enter action is emitted (state such as 'one trade per day')."""

    def direction_allowed(self, side: int) -> bool:
        d = str(self.params.get("direction", "both")).lower()
        return d == "both" or (d == "long" and side > 0) or (d == "short" and side < 0)

    # ------------------------------------------------------------------ composition
    def on_bar(self, ctx: BarContext) -> list:
        self.stats["decisions"] += 1
        if not self.ready(ctx.i):
            return []
        acts: list = []
        for p in ctx.positions:
            acts.extend(self.manage(ctx, p))
        exiting = {a.position_id for a in acts if isinstance(a, Exit)}
        remaining = [p for p in ctx.positions if p.id not in exiting]
        if not remaining and self.entry_window_ok(ctx):
            self.stats["flat_eligible_decisions"] += 1
        side = int(self.signal(ctx.i))
        if side == 0:
            return acts
        if self.params.get("close_on_opposite", True):
            for p in remaining:
                if p.side == -side:
                    acts.append(Exit(p.id, reason="opposite_signal"))
                    exiting.add(p.id)
            remaining = [p for p in remaining if p.id not in exiting]
        if any(p.side == side for p in remaining):
            return acts                       # already positioned in that direction
        if len(remaining) >= self.max_positions:
            acts.append(Skip(side, "max_positions", "position"))
            return acts
        if not self.direction_allowed(side):
            acts.append(Skip(side, "direction_disabled"))
            return acts
        reason = self.entry_block_reason(ctx, side)
        if reason:
            acts.append(Skip(side, reason))
            return acts
        st = self.stops(ctx, side)
        if st is None:
            acts.append(Skip(side, "stops_unavailable"))
            return acts
        acts.append(Enter(side, max_spread_points=self.params.get("max_spread_points"), **st))
        self.stats["entries_emitted"] += 1
        self.on_enter(ctx, side)
        return acts

    # ------------------------------------------------------------------ helpers
    def warmup(self, default: int) -> int:
        w = self.params.get("warmup_bars")
        return int(default if w is None else w)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def utc_minutes(hhmm: str) -> int:
    """'07:30' -> 450."""
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)
