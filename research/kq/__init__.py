"""KQ research engine: reproducible backtesting of XAUUSD strategies on MT5 M1 exports.

Public API (see README.md):
    MarketData, SymbolSpec, load_mt5_csv, load_spec, resample_bars, server_to_utc, utc_to_server
    CostModel, BacktestConfig, BacktestResult, run_backtest
    make_strategy, STRATEGIES
    compute_metrics
    kq.validation (walk-forward, bootstrap, Monte Carlo, DSR, Holm, monkey/anchor controls)
    kq.benchmark (buy & hold, BUY_HOLD_VOLSCALED, exposure-matched long)
    kq.registry (append-only experiment registry)
"""
__version__ = "0.1.0"

from .costs import CostModel
from .data import MarketData, SymbolSpec, load_mt5_csv, load_spec, resample_bars
from .engine import BacktestConfig, BacktestResult, run_backtest
from .metrics import compute_metrics
from .strategies import STRATEGIES, make_strategy
from .timeutil import server_to_utc, utc_to_server

__all__ = ["MarketData", "SymbolSpec", "load_mt5_csv", "load_spec", "resample_bars", "server_to_utc",
           "utc_to_server", "CostModel", "BacktestConfig", "BacktestResult", "run_backtest", "make_strategy",
           "STRATEGIES", "compute_metrics"]
