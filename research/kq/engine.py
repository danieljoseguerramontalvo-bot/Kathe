"""Event-driven backtest engine on M1 BID bars.

Timeline (no look-ahead)
------------------------
For each decision time T of the strategy (by default the CLOSE time of each bar of its
timeframe, i.e. bar open + L):

1. open positions are advanced through every M1 bar with time < T and SL/TP are checked
   bar by bar (bid for longs, ask = bid + spread for shorts);
2. the strategy sees only closed bars and returns actions;
3. actions execute at the OPEN of the first M1 bar with time >= T (index ``e``):
   exits first, then entries. Stop moves take effect from bar ``e`` onwards.

Fills
-----
* buy entry = ask open = bid open + spread(bar e) * point; sell entry = bid open;
* long exits at bid, short exits at ask;
* long SL/TP trigger on bid low/high; short SL/TP trigger on ask high/low;
* SL and TP touched inside the same M1 bar -> SL (pessimistic);
* the M1 open already beyond the stop (gap) -> fill at that open (worse than the stop);
  the M1 open already beyond the target -> fill at the target level (never better);
* ``slippage_points`` is added adversely to every fill; commission per lot round turn is
  booked at entry; swap is accrued at each server-midnight rollover the position is open over.

Sizing
------
Fixed-fractional risk on the realised balance (as the reference EA, ACCOUNT_BALANCE):
``lots = floor_to_step(balance * risk% / loss_per_lot)`` with ``loss_per_lot =
|quoted entry - stop| * contract_size * units_per_usd + commission_per_lot``. If lots <
volume_min the trade is skipped and logged (never rounded up). Fixed lots are supported.

Equity
------
Marked to market at EVERY M1 close (longs at bid close, shorts at ask close, accrued swap
included). A second series marks to the worst intrabar price (bid low / ask high).
"""
from __future__ import annotations

import time as _time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .costs import CostModel, floor_to_step, rollover_events
from .data import MarketData
from .strategies.base import BarContext, Enter, Exit, PositionView, SetStop, Skip, Strategy
from .timeutil import NS_PER_DAY, server_to_utc, to_ns

ENGINE_VERSION = "1.0.0"


@dataclass
class BacktestConfig:
    start: object = None            # server time; decisions at or after it (inclusive)
    end: object = None              # server time; EXCLUSIVE
    initial_equity: float = 10_000.0
    risk_pct: float | None = 1.0    # % of balance risked per trade; None/0 -> fixed lots
    fixed_lots: float | None = None
    account_units_per_usd: float = 1.0
    costs: CostModel = field(default_factory=CostModel)
    # No NEW entries whose execution M1 bar falls in [from, to) minutes of the server day
    # (the window may cross midnight; from == to disables it). Default 23:45 -> 01:15 server,
    # as in the live EA. The entry is skipped (reason 'rollover'), never delayed.
    rollover_from_min: int = 1425
    rollover_to_min: int = 75

    @property
    def sizing(self) -> str:
        return "risk" if self.risk_pct is not None and self.risk_pct > 0 else "fixed"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = None if self.start is None else str(pd.Timestamp(self.start))
        d["end"] = None if self.end is None else str(pd.Timestamp(self.end))
        d["sizing"] = self.sizing
        return d


class _Pos:
    __slots__ = ("id", "side", "lots", "entry_idx", "entry_time", "entry_price", "entry_ref",
                 "entry_spread", "stop", "tp", "initial_stop", "initial_tp", "r_price", "commission",
                 "risk_money", "decision_index", "decision_time", "tag", "stop_updates",
                 "balance_before")

    def view(self, t_utc) -> PositionView:
        return PositionView(self.id, self.side, self.lots, self.entry_idx, self.entry_time,
                            int(t_utc[self.entry_idx]), self.entry_price, self.stop, self.tp,
                            self.initial_stop, self.decision_index, self.tag)


class BacktestResult:
    """Output of a run: trades, skipped signals, equity (M1 mark-to-market) and stats."""

    def __init__(self, strategy: dict, config: dict, trades: pd.DataFrame, skipped: pd.DataFrame,
                 eq_t: np.ndarray, equity: np.ndarray, equity_worst: np.ndarray, balance: np.ndarray,
                 in_pos: np.ndarray, m1_close: np.ndarray, stats: dict, data_info: dict, spec: dict):
        self.strategy = strategy
        self.config = config
        self.trades = trades
        self.skipped = skipped
        self.eq_t = eq_t
        self.equity = equity
        self.equity_worst = equity_worst
        self.balance = balance
        self.in_pos = in_pos
        self.m1_close = m1_close
        self.stats = stats
        self.data_info = data_info
        self.spec = spec

    @property
    def initial_equity(self) -> float:
        return float(self.config["initial_equity"])

    def _last_per_bucket(self, bucket: np.ndarray) -> np.ndarray:
        if len(bucket) == 0:
            return np.array([], dtype=int)
        return np.flatnonzero(np.r_[bucket[1:] != bucket[:-1], True])

    def equity_frame(self, freq: str = "H1") -> pd.DataFrame:
        """Equity sampled at the last M1 close of each ``freq`` bucket (server time)."""
        from .data import tf_ns
        if freq.upper() == "M1":
            idx = np.arange(len(self.eq_t))
        else:
            idx = self._last_per_bucket(self.eq_t // tf_ns(freq))
        t = self.eq_t[idx]
        eq = self.equity[idx]
        peak = np.maximum.accumulate(np.maximum(self.equity, self.initial_equity))[idx]
        return pd.DataFrame({
            "time": pd.to_datetime(t, unit="ns"),
            "time_utc": pd.to_datetime(server_to_utc(t), unit="ns"),
            "equity": eq,
            "equity_worst": self.equity_worst[idx],
            "balance": self.balance[idx],
            "in_position": self.in_pos[idx],
            "drawdown_pct": 100.0 * (eq / peak - 1.0),
        })

    def daily_equity(self) -> pd.Series:
        """Equity at the last M1 close of each server day with data."""
        idx = self._last_per_bucket(self.eq_t // NS_PER_DAY)
        days = pd.to_datetime((self.eq_t[idx] // NS_PER_DAY) * NS_PER_DAY, unit="ns")
        return pd.Series(self.equity[idx], index=days, name="equity")

    def daily_returns(self) -> pd.Series:
        eq = self.daily_equity()
        prev = np.r_[self.initial_equity, eq.to_numpy()[:-1]]
        return pd.Series(eq.to_numpy() / prev - 1.0, index=eq.index, name="ret")

    def daily_exposure(self) -> pd.Series:
        """Fraction of each server day's M1 closes with an open position."""
        day = self.eq_t // NS_PER_DAY
        s = pd.Series(self.in_pos.astype(float)).groupby(day).mean()
        s.index = pd.to_datetime(s.index.to_numpy() * NS_PER_DAY, unit="ns")
        return s

    def to_files(self, out_dir, equity_freq: str = "H1") -> dict:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = {"trades": out / "trades.csv", "equity": out / "equity.csv",
                 "skipped": out / "skipped.csv", "daily": out / "daily_returns.csv"}
        self.trades.to_csv(paths["trades"], index=False)
        self.equity_frame(equity_freq).to_csv(paths["equity"], index=False, float_format="%.4f")
        self.skipped.to_csv(paths["skipped"], index=False)
        dr = self.daily_returns().rename_axis("date").to_frame()
        dr["equity"] = self.daily_equity().to_numpy()
        dr.to_csv(paths["daily"], float_format="%.8f")
        return {k: str(v) for k, v in paths.items()}


TRADE_COLUMNS = [
    "trade_id", "strategy", "side", "tag", "decision_index", "decision_time", "entry_time",
    "entry_time_utc", "entry_price", "entry_ref_price", "entry_spread_pts", "lots", "risk_money",
    "initial_stop", "initial_tp", "final_stop", "stop_updates", "exit_time", "exit_time_utc",
    "exit_price", "exit_ref_price", "exit_reason", "hold_minutes", "gross_pnl", "commission", "swap",
    "net_pnl", "r_price", "r_gross", "r_net", "mae_r", "mfe_r", "balance_before", "balance_after",
]
SKIP_COLUMNS = ["time", "side", "kind", "reason", "detail"]


class Engine:
    def __init__(self, md: MarketData, strategy: Strategy, config: BacktestConfig):
        self.md, self.strategy, self.cfg = md, strategy, config
        spec = md.spec
        self.spec = spec
        self.point = float(spec.point)
        self.digits = int(spec.digits)
        self.vpl = float(spec.contract_size) * float(config.account_units_per_usd)
        costs = config.costs
        self.spr_pts = costs.effective_spread_points(md.spread)
        spr = self.spr_pts * self.point
        self.o, self.h, self.l, self.c, self.t = md.o, md.h, md.l, md.c, md.t
        d = self.digits
        self.ao = np.round(self.o + spr, d)
        self.ah = np.round(self.h + spr, d)
        self.al = np.round(self.l + spr, d)
        self.ac = np.round(self.c + spr, d)
        self.slip = float(costs.slippage_points) * self.point
        self.comm = float(costs.commission_per_lot_rt)
        self.swap_long, self.swap_short = costs.swap_money_per_lot_night(spec, config.account_units_per_usd)
        self.swap_on = costs.apply_swap and (self.swap_long != 0.0 or self.swap_short != 0.0)
        self.triple_wd = costs.triple_weekday_python(spec)
        self.min_stop = float(spec.stops_level) * self.point

    # ------------------------------------------------------------------ helpers
    def _rp(self, x: float) -> float:
        return round(float(x), self.digits)

    def _in_rollover(self, j) -> np.ndarray | bool:
        """True where the server minute-of-day of M1 bar(s) ``j`` is inside the rollover window."""
        return in_minute_window(self.t[j], self.cfg.rollover_from_min, self.cfg.rollover_to_min)

    def _skip(self, ctx: BarContext, side: int, kind: str, reason: str, detail: str = "") -> None:
        self.skips.append((ctx.decision_time, side, kind, reason, detail))

    # ------------------------------------------------------------------ main loop
    def run(self) -> BacktestResult:
        t_start = _time.perf_counter()
        md, cfg, strat = self.md, self.cfg, self.strategy
        t = self.t
        start_ns = to_ns(cfg.start) if cfg.start is not None else int(t[0])
        end_ns = to_ns(cfg.end) if cfg.end is not None else int(t[-1]) + 1
        j0 = int(np.searchsorted(t, start_ns, "left"))
        j1 = int(np.searchsorted(t, end_ns, "left"))
        if j1 <= j0:
            raise ValueError(f"no M1 data in [{cfg.start}, {cfg.end})")
        self.j0, self.j1 = j0, j1
        strat.prepare(md)
        dec_t = np.asarray(strat.decision_times(), dtype="int64")
        k0 = int(np.searchsorted(dec_t, start_ns, "left"))
        ex = np.searchsorted(t, dec_t[k0:], "left")
        n_valid = int(np.searchsorted(ex, j1, "left"))      # ex is non-decreasing
        ex = ex[:n_valid]
        dec_utc = server_to_utc(dec_t[k0:k0 + n_valid]) if n_valid else np.array([], dtype="int64")

        self.balance = float(cfg.initial_equity)
        self.closed: list[dict] = []
        self.skips: list[tuple] = []
        self.next_id = 1
        self.n_stop_moves = 0
        self.n_stop_rejected = 0
        positions: list[_Pos] = []
        cursor = j0
        n_flat = 0
        t_utc = md.t_utc
        for kk in range(n_valid):
            k = k0 + kk
            e = int(ex[kk])
            if positions:
                self._advance(positions, cursor, e)
            cursor = e
            if not positions:
                n_flat += 1
            ctx = BarContext(k, int(dec_t[k]), int(dec_utc[kk]), e, int(t[e]),
                             [p.view(t_utc) for p in positions], self.balance, md)
            acts = strat.on_bar(ctx)
            if acts:
                deadline = int(ex[kk + 1]) if kk + 1 < n_valid else j1
                self._apply(acts, ctx, positions, max(deadline, e + 1))
        if positions:
            self._advance(positions, cursor, j1)
        for p in list(positions):
            jl = j1 - 1
            ref = self.c[jl] if p.side > 0 else self.ac[jl]
            self._close(p, jl, ref, "end_of_test", intrabar=True)
            positions.remove(p)

        equity, worst, balance, in_pos = self._build_equity(j0, j1)
        trades = self._trades_frame()
        skipped = pd.DataFrame(self.skips, columns=SKIP_COLUMNS)
        if len(skipped):
            skipped["time"] = pd.to_datetime(skipped["time"].to_numpy(dtype="int64"), unit="ns")
        stats = {
            "engine_version": ENGINE_VERSION,
            "runtime_s": round(_time.perf_counter() - t_start, 4),
            "n_m1_bars_in_range": int(j1 - j0),
            "n_decisions": int(n_valid),
            "n_flat_decisions": int(n_flat),
            "n_stop_moves": int(self.n_stop_moves),
            "n_stop_moves_rejected": int(self.n_stop_rejected),
            "range_first_bar": str(pd.Timestamp(int(t[j0]), unit="ns")),
            "range_last_bar": str(pd.Timestamp(int(t[j1 - 1]), unit="ns")),
            "strategy_stats": dict(strat.stats),
            "equity_mark_to_market": "every M1 close (longs at bid close, shorts at ask close)",
        }
        return BacktestResult(strat.describe(), cfg.to_dict(), trades, skipped, t[j0:j1].copy(),
                              equity, worst, balance, in_pos, self.c[j0:j1].copy(), stats,
                              md.info(), md.spec.to_dict())

    # ------------------------------------------------------------------ exits on M1 path
    def _advance(self, positions: list, a: int, b: int) -> None:
        for p in list(positions):
            s = max(a, p.entry_idx)
            if s >= b:
                continue
            hit = self._scan(p, s, b)
            if hit is not None:
                j, ref, reason = hit
                self._close(p, j, ref, reason, intrabar=True)
                positions.remove(p)

    def _scan(self, p: _Pos, a: int, b: int):
        s, tp = p.stop, p.tp
        if s is None and tp is None:
            return None
        if p.side > 0:
            lo, hi = self.l[a:b], self.h[a:b]
            hit = (lo <= s) if s is not None else np.zeros(b - a, dtype=bool)
            if tp is not None:
                hit = hit | (hi >= tp)
            if not hit.any():
                return None
            j = a + int(hit.argmax())
            op = self.o[j]
            if s is not None and op <= s:
                return j, op, "sl_gap"
            if tp is not None and op >= tp:
                return j, tp, "tp_gap"
            if s is not None and self.l[j] <= s:
                both = tp is not None and self.h[j] >= tp
                return j, s, self._sl_reason(p, both)
            return j, tp, "tp"
        ahi, alo = self.ah[a:b], self.al[a:b]
        hit = (ahi >= s) if s is not None else np.zeros(b - a, dtype=bool)
        if tp is not None:
            hit = hit | (alo <= tp)
        if not hit.any():
            return None
        j = a + int(hit.argmax())
        op = self.ao[j]
        if s is not None and op >= s:
            return j, op, "sl_gap"
        if tp is not None and op <= tp:
            return j, tp, "tp_gap"
        if s is not None and self.ah[j] >= s:
            both = tp is not None and self.al[j] <= tp
            return j, s, self._sl_reason(p, both)
        return j, tp, "tp"

    @staticmethod
    def _sl_reason(p: _Pos, both: bool) -> str:
        base = "sl" if p.stop == p.initial_stop else "trail_sl"
        return base + ("_same_bar_as_tp" if both else "")

    # ------------------------------------------------------------------ actions
    def _apply(self, acts: list, ctx: BarContext, positions: list, deadline: int) -> None:
        order = {SetStop: 0, Exit: 1, Skip: 2, Enter: 3}
        for a in sorted(acts, key=lambda x: order[type(x)]):
            if isinstance(a, SetStop):
                self._set_stop(a, ctx, positions)
            elif isinstance(a, Exit):
                e = ctx.exec_index
                for p in [p for p in positions
                          if (a.position_id is None or p.id == a.position_id)
                          and (a.side is None or p.side == a.side)]:
                    ref = self.o[e] if p.side > 0 else self.ao[e]
                    self._close(p, e, ref, a.reason, intrabar=False)
                    positions.remove(p)
            elif isinstance(a, Skip):
                self._skip(ctx, a.side, a.kind, a.reason)
            elif isinstance(a, Enter):
                self._enter(a, ctx, positions, deadline)
            else:
                raise TypeError(f"unknown action {a!r}")

    def _set_stop(self, a: SetStop, ctx: BarContext, positions: list) -> None:
        p = next((q for q in positions if q.id == a.position_id), None)
        if p is None or a.price is None or not np.isfinite(a.price):
            return
        new = self._rp(a.price)
        # tighten only: a long stop can only go up, a short stop only down
        if p.stop is not None and ((p.side > 0 and new <= p.stop) or (p.side < 0 and new >= p.stop)):
            return
        # the move is decided at the bar close: it must be a valid stop at that price
        jc = max(ctx.exec_index - 1, 0)
        valid = (self.c[jc] - new > self.min_stop) if p.side > 0 else (new - self.ac[jc] > self.min_stop)
        if not valid:
            self.n_stop_rejected += 1
            return
        p.stop = new
        p.stop_updates += 1
        self.n_stop_moves += 1

    def _enter(self, a: Enter, ctx: BarContext, positions: list, deadline: int) -> None:
        cfg, spec = self.cfg, self.spec
        side = int(a.side)
        if side not in (1, -1):
            raise ValueError("Enter.side must be +1 or -1")
        if len(positions) >= self.strategy.max_positions:
            self._skip(ctx, side, "position", "max_positions")
            return
        e = ctx.exec_index
        j = e
        if self._in_rollover(e):
            self._skip(ctx, side, "execution", "rollover",
                       f"exec {pd.Timestamp(int(self.t[e]), unit='ns')} inside "
                       f"[{self.cfg.rollover_from_min}, {self.cfg.rollover_to_min}) min server")
            return
        if a.max_spread_points is not None:
            window = self.spr_pts[e:deadline]
            ok = np.flatnonzero((window <= a.max_spread_points) & ~self._in_rollover(np.arange(e, deadline)))
            if len(ok) == 0:
                self._skip(ctx, side, "execution", "spread_above_max",
                           f"max={a.max_spread_points} min_seen={window.min():.0f}")
                return
            j = e + int(ok[0])
        bid, ask = self.o[j], self.ao[j]
        ref = ask if side > 0 else bid
        fill = ref + side * self.slip
        sl = None
        if a.sl_price is not None:
            sl = self._rp(a.sl_price)
        elif a.sl_dist is not None:
            if not np.isfinite(a.sl_dist) or a.sl_dist <= 0:
                self._skip(ctx, side, "execution", "invalid_stop", f"sl_dist={a.sl_dist}")
                return
            sl = self._rp(ref - side * a.sl_dist)
        tp = None
        if a.tp_price is not None:
            tp = self._rp(a.tp_price)
        elif a.tp_dist is not None and np.isfinite(a.tp_dist) and a.tp_dist > 0:
            tp = self._rp(ref + side * a.tp_dist)
        if sl is not None:
            ok = (bid - sl > self.min_stop) if side > 0 else (sl - ask > self.min_stop)
            if not ok:
                self._skip(ctx, side, "execution", "invalid_stop",
                           f"stop {sl} vs bid {bid} / ask {ask}, stops_level {spec.stops_level}")
                return
        elif cfg.sizing == "risk":
            self._skip(ctx, side, "sizing", "no_stop_for_risk_sizing")
            return
        if tp is not None:
            ok = (tp - bid > self.min_stop) if side > 0 else (ask - tp > self.min_stop)
            if not ok:
                self._skip(ctx, side, "execution", "invalid_tp", f"tp {tp} vs bid {bid} / ask {ask}")
                return
        if self.balance <= 0:
            self._skip(ctx, side, "sizing", "no_balance")
            return
        loss_per_lot = abs(ref - sl) * self.vpl + self.comm if sl is not None else float("nan")
        if cfg.sizing == "risk":
            risk_target = self.balance * float(cfg.risk_pct) / 100.0
            raw = risk_target / loss_per_lot
            lots = floor_to_step(raw, spec.volume_step)
            if lots < spec.volume_min - 1e-12:
                self._skip(ctx, side, "sizing", "min_lot_exceeds_risk",
                           f"lots_raw={raw:.5f} volume_min={spec.volume_min} "
                           f"loss_at_min_lot={loss_per_lot * spec.volume_min:.2f} risk={risk_target:.2f}")
                return
        else:
            lots = floor_to_step(float(cfg.fixed_lots or 0.0), spec.volume_step)
            if lots < spec.volume_min - 1e-12:
                self._skip(ctx, side, "sizing", "fixed_lots_below_min", f"fixed_lots={cfg.fixed_lots}")
                return
        if lots > spec.volume_max:
            self._skip(ctx, side, "sizing", "capped_at_volume_max", f"lots={lots}")
            lots = float(spec.volume_max)
        p = _Pos()
        p.id = self.next_id
        self.next_id += 1
        p.side, p.lots = side, lots
        p.entry_idx, p.entry_time = j, int(self.t[j])
        p.entry_ref, p.entry_price = float(ref), float(fill)
        p.entry_spread = float(self.spr_pts[j])
        p.stop = p.initial_stop = sl
        p.tp = p.initial_tp = tp
        p.r_price = abs(fill - sl) if sl is not None else float("nan")
        p.commission = self.comm * lots
        p.risk_money = lots * loss_per_lot
        p.decision_index, p.decision_time = ctx.i, ctx.decision_time
        p.tag = a.tag
        p.stop_updates = 0
        p.balance_before = self.balance
        self.balance -= p.commission
        positions.append(p)

    def _close(self, p: _Pos, j: int, ref: float, reason: str, intrabar: bool) -> None:
        fill = float(ref) - p.side * self.slip
        exit_time = int(self.t[j])
        gross = p.side * (fill - p.entry_price) * p.lots * self.vpl
        swaps = []
        if self.swap_on:
            per = self.swap_long if p.side > 0 else self.swap_short
            for m, mult in rollover_events(p.entry_time, exit_time, self.triple_wd):
                idx = int(np.searchsorted(self.t, m, "left"))
                swaps.append((idx, p.lots * per * mult))
        swap_total = float(sum(x[1] for x in swaps))
        self.balance += gross + swap_total
        net = gross + swap_total - p.commission
        end = j + 1 if intrabar else j
        end = max(end, p.entry_idx + 1)
        if p.side > 0:
            worst = float(self.l[p.entry_idx:end].min()) - p.entry_price
            best = float(self.h[p.entry_idx:end].max()) - p.entry_price
        else:
            worst = p.entry_price - float(self.ah[p.entry_idx:end].max())
            best = p.entry_price - float(self.al[p.entry_idx:end].min())
        r = p.r_price
        money_r = p.lots * self.vpl * r if np.isfinite(r) and r > 0 else float("nan")
        self.closed.append({
            "trade_id": p.id, "strategy": self.strategy.name, "side": p.side, "tag": p.tag,
            "decision_index": p.decision_index, "decision_time": p.decision_time,
            "entry_idx": p.entry_idx, "exit_idx": j, "entry_time": p.entry_time,
            "entry_price": p.entry_price, "entry_ref_price": p.entry_ref, "entry_spread_pts": p.entry_spread,
            "lots": p.lots, "risk_money": p.risk_money, "initial_stop": p.initial_stop,
            "initial_tp": p.initial_tp, "final_stop": p.stop, "stop_updates": p.stop_updates,
            "exit_time": exit_time, "exit_price": fill, "exit_ref_price": float(ref), "exit_reason": reason,
            "gross_pnl": gross, "commission": p.commission, "swap": swap_total, "net_pnl": net,
            "r_price": r, "r_gross": p.side * (fill - p.entry_price) / r if money_r == money_r else float("nan"),
            "r_net": net / money_r if money_r == money_r else float("nan"),
            "mae_r": worst / r if money_r == money_r else float("nan"),
            "mfe_r": best / r if money_r == money_r else float("nan"),
            "balance_before": p.balance_before, "balance_after": self.balance, "_swaps": swaps,
        })

    # ------------------------------------------------------------------ outputs
    def _build_equity(self, j0: int, j1: int):
        n = j1 - j0
        cash = np.zeros(n)
        unreal = np.zeros(n)
        worst = np.zeros(n)
        in_pos = np.zeros(n, dtype=bool)
        for tr in self.closed:
            a, b = tr["entry_idx"] - j0, tr["exit_idx"] - j0
            cash[a] -= tr["commission"]
            cash[b] += tr["gross_pnl"] + tr["swap"]
            if b > a:
                k = tr["lots"] * self.vpl
                ent = tr["entry_price"]
                if tr["side"] > 0:
                    unreal[a:b] += (self.c[j0 + a:j0 + b] - ent) * k
                    worst[a:b] += (self.l[j0 + a:j0 + b] - ent) * k
                else:
                    unreal[a:b] += (ent - self.ac[j0 + a:j0 + b]) * k
                    worst[a:b] += (ent - self.ah[j0 + a:j0 + b]) * k
                in_pos[a:b] = True
                for idx, amt in tr["_swaps"]:
                    s = max(idx - j0, a)
                    if s < b:
                        unreal[s:b] += amt
                        worst[s:b] += amt
        balance = float(self.cfg.initial_equity) + np.cumsum(cash)
        return balance + unreal, balance + worst, balance, in_pos

    def _trades_frame(self) -> pd.DataFrame:
        if not self.closed:
            return pd.DataFrame(columns=TRADE_COLUMNS)
        df = pd.DataFrame(self.closed)
        for c in ("decision_time", "entry_time", "exit_time"):
            df[c] = pd.to_datetime(df[c].to_numpy(dtype="int64"), unit="ns")
        df["entry_time_utc"] = pd.to_datetime(self.md.t_utc[df["entry_idx"].to_numpy()], unit="ns")
        df["exit_time_utc"] = pd.to_datetime(self.md.t_utc[df["exit_idx"].to_numpy()], unit="ns")
        df["hold_minutes"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60.0
        df = df.sort_values(["entry_time", "trade_id"]).reset_index(drop=True)
        return df[TRADE_COLUMNS]


def in_minute_window(t_ns, from_min: int, to_min: int):
    """Whether server time(s) fall in the minute-of-day window [from, to) (may cross midnight;
    from == to means disabled)."""
    m = (np.asarray(t_ns, dtype="int64") % NS_PER_DAY) // 60_000_000_000
    f, t_ = int(from_min) % 1440, int(to_min) % 1440
    if f == t_:
        return np.zeros(np.shape(m), dtype=bool) if np.ndim(m) else False
    if f < t_:
        return (m >= f) & (m < t_)
    return (m >= f) | (m < t_)


def run_backtest(md: MarketData, strategy: Strategy, config: BacktestConfig | None = None) -> BacktestResult:
    """Run one backtest. ``strategy`` must be a fresh (or re-preparable) instance."""
    return Engine(md, strategy, config or BacktestConfig()).run()
