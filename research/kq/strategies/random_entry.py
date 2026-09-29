"""RANDOM_ENTRY — monkey test.

Random direction at random decision times (seeded) with the SAME exits as a target strategy:
the target's initial stop/target formula (``stops``), its position management (trailing,
indicator/time exits, ``manage``) and, optionally, its opposite-signal exits. Entries happen
with probability ``p_entry`` at each decision where the strategy is flat and the target's
entry window allows it (e.g. SESSION_BREAKOUT's 07-12 UTC window, one attempt per day).
Calibrate ``p_entry`` with :func:`kq.validation.calibrate_random_entry` (target entries per
flat eligible decision) so the entry frequency matches the target.
Two uniforms are drawn at EVERY decision, so a seed gives the same draw sequence whatever
the position state.
"""
from __future__ import annotations

import numpy as np

from .base import Enter, Exit, Strategy


class RandomEntry(Strategy):
    name = "RANDOM_ENTRY"
    default_params = {
        "target": "REF_T0",
        "target_params": {},
        "p_entry": None,
        "seed": 0,
        "use_target_exits": True,        # also exit on the target's opposite signals
        "respect_entry_window": True,
    }

    def __init__(self, **params):
        super().__init__(**params)
        from . import make_strategy
        self.target = make_strategy(self.params["target"], self.params["target_params"])
        if self.params["p_entry"] is None:
            raise ValueError("RANDOM_ENTRY needs p_entry (see kq.validation.calibrate_random_entry)")
        self.max_positions = 1

    @property
    def timeframe(self):
        return self.target.timeframe

    def describe(self):
        d = super().describe()
        d["target"] = self.target.describe()
        return d

    def prepare(self, md):
        self.target.prepare(md)
        self.md = md
        self.bars = self.target.bars
        self.rng = np.random.default_rng(self.params["seed"])
        self.stats = {"decisions": 0, "flat_eligible_decisions": 0, "entries_emitted": 0}

    def decision_times(self):
        return self.target.decision_times()

    def ready(self, i):
        return self.target.ready(i)

    def signal(self, i):
        u, d = self.rng.random(2)
        if u < float(self.params["p_entry"]):
            return 1 if d < 0.5 else -1
        return 0

    def on_bar(self, ctx):
        self.stats["decisions"] += 1
        side = self.signal(ctx.i)              # always draw (reproducibility)
        tgt = self.target
        if not tgt.ready(ctx.i):
            return []
        acts = []
        for p in ctx.positions:
            acts.extend(tgt.manage(ctx, p))
        exiting = {a.position_id for a in acts if isinstance(a, Exit)}
        if self.params["use_target_exits"] and tgt.params.get("close_on_opposite", True):
            ts = int(tgt.signal(ctx.i))
            if ts:
                for p in ctx.positions:
                    if p.id not in exiting and p.side == -ts:
                        acts.append(Exit(p.id, reason="target_opposite_signal"))
                        exiting.add(p.id)
        remaining = [p for p in ctx.positions if p.id not in exiting]
        if remaining:
            return acts
        window = (not self.params["respect_entry_window"]) or tgt.entry_window_ok(ctx)
        if not window:
            return acts
        self.stats["flat_eligible_decisions"] += 1
        if side == 0:
            return acts
        st = tgt.stops(ctx, side)
        if st is None:
            return acts
        acts.append(Enter(side, max_spread_points=tgt.params.get("max_spread_points"), tag="random", **st))
        self.stats["entries_emitted"] += 1
        tgt.on_enter(ctx, side)
        return acts
