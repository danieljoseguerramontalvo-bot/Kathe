"""Transaction-cost model: spread, slippage, commission and swap.

Money amounts are in ACCOUNT currency units. For a USD account ``account_units_per_usd`` is
1; for a USC (cent) account it is 100, so 1 USD of profit is 100 account units.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .data import SymbolSpec
from .timeutil import NS_PER_DAY, weekday_of_ns


@dataclass
class CostModel:
    """Execution costs.

    slippage_points        adverse slippage added to EVERY fill (entries, exits, SL, TP), points.
    commission_per_lot_rt  commission per 1.0 lot round turn, account currency; booked at entry.
    apply_swap             charge overnight swap when a position is open at 00:00 server.
    swap_long/swap_short   per lot per night; None -> use the SymbolSpec values.
    swap_mode              "points" (MT5 SYMBOL_SWAP_MODE_POINTS) or "money" (account currency
                           per lot); None -> SymbolSpec.swap_mode.
    swap_triple_weekday    MT5 numbering (0=Sunday ... 3=Wednesday); the rollover at the END of
                           that server day is charged x3. None -> SymbolSpec.swap_3days.
    spread_multiplier      multiplies the bar spread (stress test).
    spread_floor_points    minimum spread used for every bar (points).
    """

    slippage_points: float = 0.0
    commission_per_lot_rt: float = 0.0
    apply_swap: bool = False
    swap_long: float | None = None
    swap_short: float | None = None
    swap_mode: str | None = None
    swap_triple_weekday: int | None = None
    spread_multiplier: float = 1.0
    spread_floor_points: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "CostModel":
        return cls(**(d or {}))

    def effective_spread_points(self, spread_points: np.ndarray) -> np.ndarray:
        s = np.asarray(spread_points, dtype=float) * float(self.spread_multiplier)
        return np.maximum(s, float(self.spread_floor_points))

    def swap_money_per_lot_night(self, spec: SymbolSpec, units_per_usd: float) -> tuple[float, float]:
        """(long, short) swap per 1.0 lot per night in account currency (signed: <0 = cost)."""
        if not self.apply_swap:
            return 0.0, 0.0
        mode = (self.swap_mode or spec.swap_mode or "points").lower()
        sl = spec.swap_long if self.swap_long is None else self.swap_long
        ss = spec.swap_short if self.swap_short is None else self.swap_short
        if mode == "disabled":
            return 0.0, 0.0
        if mode == "points":
            k = spec.point * spec.contract_size * units_per_usd
            return float(sl) * k, float(ss) * k
        if mode == "money":
            return float(sl), float(ss)
        raise ValueError(f"unsupported swap_mode {mode!r}")

    def triple_weekday_python(self, spec: SymbolSpec) -> int:
        mt5 = spec.swap_3days if self.swap_triple_weekday is None else self.swap_triple_weekday
        return (int(mt5) - 1) % 7  # MT5 Sunday=0 -> Python Monday=0


def rollover_events(entry_ns: int, exit_ns: int, triple_weekday_py: int) -> list[tuple[int, int]]:
    """Server-midnight rollovers charged to a position open over them.

    A position is charged at midnight ``m`` if ``entry < m <= exit``. The night is charged when
    the day that ENDS at ``m`` is Monday..Friday (no rollover for Saturday/Sunday); the day
    equal to ``triple_weekday_py`` (Python numbering) is charged x3.
    Returns [(midnight_ns, multiplier), ...].
    """
    out = []
    m = (int(entry_ns) // NS_PER_DAY + 1) * NS_PER_DAY
    while m <= exit_ns:
        wd = int(weekday_of_ns(m - NS_PER_DAY))
        if wd < 5:
            out.append((m, 3 if wd == triple_weekday_py else 1))
        m += NS_PER_DAY
    return out


def floor_to_step(lots: float, step: float) -> float:
    """Round a volume DOWN to the volume step (with a tiny tolerance for float noise)."""
    if step <= 0:
        return float(lots)
    k = np.floor(lots / step + 1e-9)
    decimals = max(0, int(round(-np.log10(step))) + 2)
    return round(float(k * step), decimals)
