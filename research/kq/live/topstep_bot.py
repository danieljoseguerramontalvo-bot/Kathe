"""Bot para TopstepX (API ProjectX) que ejecuta una estrategia del motor ``kq`` sobre futuros de oro.

Cómo decide: en cada vela M1 cerrada vuelve a pasar el motor de backtesting por el historial
cargado (el mismo código que se valida con el protocolo). Si al final queda una posición «abierta»
en el backtest, esa es la posición que la estrategia quiere ahora; el bot copia su dirección, stop y
objetivo. Así el bot en vivo y el backtest aplican exactamente las mismas reglas (entradas, rollover,
plazo de entrada, trailing y salidas).

Seguridad (reglas del proyecto y de Topstep):
* por defecto SOLO SEÑALES (``execute: false``): registra lo que haría, sin enviar órdenes;
* para ejecutar hacen falta ``execute: true``, que la cuenta esté en ``account_ids`` y que la API la
  marque como simulada (Trading Combine / Express / práctica). Nunca opera una cuenta no simulada:
  Topstep no admite bots en la Live Funded Account y las cuentas reales del proyecto van solo con señales;
* contratos = riesgo en USD / pérdida al stop de 1 contrato, redondeado hacia abajo; si 1 contrato
  arriesga más de lo permitido, no entra (nunca sube el riesgo); sin martingala ni grid; una posición;
* toda posición lleva stop: si los brackets no aparecen en el lado correcto, pone un stop propio y, si
  tampoco puede, cierra la posición y se bloquea;
* bloqueos: pérdida diaria (día de Topstep, cierre a las 17:00 de Chicago) y margen hasta el
  Maximum Loss Limit estimado; quedan guardados en ``state.json``;
* Topstep prohíbe usar VPS, VPN o servidores remotos con la API: ejecútalo en tu propio PC y vigílalo.

Uso (el bot pide el usuario y la API key al arrancar; la clave no se muestra en pantalla):
    python -m kq.live.topstep_bot --config topstep.json          (bucle)
    python -m kq.live.topstep_bot --config topstep.json --once   (un solo paso)
    python -m kq.live.topstep_bot --config topstep.json --export-bars 365 --out KQ_MGC_M1.csv
"""
from __future__ import annotations

import argparse
import atexit
import csv
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..costs import CostModel
from ..data import MarketData, SymbolSpec
from ..engine import BacktestConfig, run_backtest
from ..strategies import make_strategy
from ..timeutil import server_to_utc, utc_to_server
from . import panel
from .projectx import SIDE_BUY, SIDE_SELL, TYPE_LIMIT, TYPE_MARKET, TYPE_STOP, ProjectXClient, ProjectXError

DEFAULTS = {
    "base_url": "https://api.topstepx.com",
    "symbol_search": "MGC",            # micro oro (10 oz; tick 0.10 = 1 USD)
    "contract_id": None,               # opcional: fija el contrato (p. ej. CON.F.US.MGC.Z26)
    "account_ids": [],                 # cuentas en las que se permite EJECUTAR
    "execute": False,                  # False = solo señales
    "strategy": "REF_T0",
    "params": {},
    "warmup_days": 150,
    "risk_usd_per_trade": 200.0,       # 10 % del MLL de una cuenta de 50K
    "max_contracts": 5,
    "daily_loss_limit_usd": 500.0,
    "initial_balance": 50000.0,
    "mll_usd": 2000.0,                 # Maximum Loss Limit de la cuenta
    "mll_floor_override": None,        # si lo conoces, el nivel exacto del MLL que muestra TopstepX
    "mll_buffer_usd": 500.0,           # no se acerca al MLL a menos de esto
    "commission_per_contract_rt": 1.0,
    "slippage_ticks": 1,
    "entry_max_age_min": 10,           # no persigue señales más antiguas que esto
    "poll_seconds": 15,
    "state_dir": "topstep_state",
    "display_tz": "America/Aruba",     # hora local en pantalla y en el panel (Aruba = Venezuela = UTC-4)
    "open_panel": True,                # abrir topstep_state/panel.html en el navegador al arrancar
    "label": None,                     # nombre en pantalla y en Telegram (p. ej. «ORO DÍA»); por defecto, el símbolo
    "heartbeat_url": None,             # opcional: URL de un vigilante externo (p. ej. healthchecks.io) que avisa si el PC se apaga
    "trades_days": 60,                 # días de ejecuciones de la cuenta que muestra el panel
    "profit_target_usd": 3000.0,       # objetivo de beneficio del Combine (50K); compruébalo en TopstepX
    "consistency_pct": 50.0,           # regla de consistencia: el mejor día, menos de este % del beneficio total
}
FORBIDDEN_CONFIG_KEYS = {"api_key", "apikey", "apiKey", "password", "token", "secret"}


def load_config(path) -> dict:
    cfg = dict(DEFAULTS)
    user = json.loads(Path(path).read_text(encoding="utf-8-sig")) if path else {}   # -sig: el Bloc de notas puede añadir BOM
    bad = [k for k in user if k in FORBIDDEN_CONFIG_KEYS or k.lower() in FORBIDDEN_CONFIG_KEYS]
    if bad:
        raise ValueError(f"la configuración no puede contener credenciales ({bad}): usa las variables de entorno "
                         "TOPSTEPX_USERNAME y TOPSTEPX_API_KEY")
    unknown = set(user) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"claves desconocidas en la configuración: {sorted(unknown)}")
    cfg.update(user)
    return cfg


def topstep_day_key(now_utc: datetime) -> str:
    """Día de negociación de Topstep: cambia a las 17:00 de Chicago."""
    ts = pd.Timestamp(now_utc)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return (ts.tz_convert("America/Chicago") + pd.Timedelta(hours=7)).strftime("%Y-%m-%d")


def futures_spec(contract: dict, max_contracts: int) -> SymbolSpec:
    from decimal import Decimal
    tick = float(contract["tickSize"])
    tick_value = float(contract["tickValue"])
    exp = Decimal(str(contract["tickSize"])).normalize().as_tuple().exponent
    digits = max(0, -int(exp))
    return SymbolSpec(symbol=str(contract.get("name") or contract.get("id")), digits=digits, point=tick,
                      tick_size=tick, tick_value=tick_value, contract_size=tick_value / tick, volume_min=1.0,
                      volume_max=float(max_contracts), volume_step=1.0, swap_long=0.0, swap_short=0.0,
                      swap_mode="disabled", account_currency="USD")


def bars_to_frame(bars: list[dict]) -> pd.DataFrame:
    """Velas de ProjectX (t en UTC; o, h, l, c, v) -> formato del motor, en hora del servidor NY+7.
    Los futuros no traen spread por vela: se usa 1 tick (spread = 1 punto, con point = tick)."""
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
    df = pd.DataFrame(bars)
    t = pd.to_datetime(df["t"], utc=True).dt.tz_convert(None)
    idx = pd.DatetimeIndex(utc_to_server(pd.DatetimeIndex(t))).as_unit("ns")
    out = pd.DataFrame({"open": df["o"].astype(float).to_numpy(), "high": df["h"].astype(float).to_numpy(),
                        "low": df["l"].astype(float).to_numpy(), "close": df["c"].astype(float).to_numpy(),
                        "tick_volume": df.get("v", pd.Series(0, index=df.index)).astype(float).to_numpy(),
                        "spread": 1.0, "real_volume": 0.0}, index=idx)
    out.index.name = "time"
    return out.sort_index()[~out.sort_index().index.duplicated(keep="last")]


@dataclass
class Target:
    key: str
    side: int
    entry_time_utc: pd.Timestamp
    entry_price: float          # precio de referencia (cotizado) de la entrada: stop y objetivo se miden desde aquí
    stop: float
    tp: float | None


@dataclass
class State:
    last_entry_key: str | None = None
    position_key: str | None = None
    position_side: int = 0
    position_stop: float | None = None
    day_key: str | None = None
    day_start_balance: float | None = None
    last_balance: float | None = None
    max_eod_balance: float | None = None
    locked_day: str | None = None
    locked_reason: str | None = None
    hard_lock: str | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "State":
        if path.exists():
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        return cls()

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)


class TopstepBot:
    def __init__(self, cfg: dict, client: ProjectXClient, now_fn=None, strategy_factory=None, log=print,
                 sleep=time.sleep, notifier=None):
        self.cfg = cfg
        self.notifier = notifier
        self.client = client
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.strategy_factory = strategy_factory or (lambda: make_strategy(cfg["strategy"], dict(cfg["params"])))
        self.log_fn, self.sleep = log, sleep
        self.dir = Path(cfg["state_dir"])
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"
        self.state = State.load(self.state_path)
        self.account: dict | None = None
        self.contract: dict | None = None
        self.spec: SymbolSpec | None = None
        self.bars = pd.DataFrame()
        self.last_eval_bar = None
        self.execute = False
        self._heartbeat_hour = None
        self._bt_trades = None
        self._foreign_pos = None
        self._last_panel: dict | None = None
        self.daily_summary = True              # con varios turnos en ejecución, solo uno manda el resumen diario
        self._risk_now: tuple[bool | None, str] = (None, "")
        self._trades: list[dict] = []
        self._trades_at: datetime | None = None
        self._panel_error: str | None = None

    # ------------------------------------------------------------------ registro
    def log(self, msg: str):
        tz = self.cfg.get("display_tz")
        self.log_fn(f"[{panel.fmt_local(self.now_fn(), tz, '%d/%m %H:%M:%S')} {panel.tz_label(tz)}] [{self.name}] {msg}")

    @property
    def name(self) -> str:
        return self.cfg.get("label") or self.cfg["symbol_search"]

    def journal(self, event: str, **kw):
        path = self.dir / "diario.csv"
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            if new:
                w.writerow(["time_utc", "mode", "event", "side", "contracts", "price", "stop", "tp", "detail"])
            w.writerow([f"{self.now_fn():%Y-%m-%d %H:%M:%S}", "EJECUCION" if self.execute else "SENALES", event,
                        kw.get("side", ""), kw.get("contracts", ""), kw.get("price", ""), kw.get("stop", ""),
                        kw.get("tp", ""), kw.get("detail", "")])
        extra = " ".join(f"{k}={kw[k]}" for k in ("side", "contracts", "price", "stop", "tp") if kw.get(k) not in (None, ""))
        self.log(f"{event} {extra} {kw.get('detail', '')}".replace("  ", " ").strip())   # también en pantalla
        if event == "EXIT" and self.execute:          # el resultado se avisa cuando el saldo ya lo refleja
            self.state.extra["exit_pending"] = self.now_fn().isoformat()
            self.state.extra["exit_why"] = kw.get("detail", "")
        self._notify_event(event, kw)

    # ------------------------------------------------------------------ avisos (Telegram)
    def notify(self, text: str):
        if self.notifier is not None:
            self.notifier.send(f"[{self.name}] {text}")

    def _hora(self, ts=None) -> str:
        return panel.fmt_local(ts or self.now_fn(), self.cfg.get("display_tz"), "%H:%M")

    def _progress_text(self, balance: float) -> str:
        total = balance - float(self.cfg["initial_balance"])
        target = float(self.cfg["profit_target_usd"])
        return (f"Saldo {balance:,.2f} · total {total:+,.2f} USD · objetivo +{target:,.0f}: "
                f"faltan {max(0.0, target - total):,.0f}")

    def _next_entry_text(self) -> str:
        sch = panel.session_schedule(self.cfg, self.now_fn(), upcoming_only=True)
        return f"Próxima entrada: {panel.fmt_day(sch['start'], self.cfg.get('display_tz'))}" if sch else ""

    def _planned_exit_text(self) -> str:
        sch = panel.session_schedule(self.cfg, self.now_fn())
        if sch and sch["active"]:
            return f"cierre previsto {panel.clock(panel.to_local(sch['end'], self.cfg.get('display_tz')))}"
        return ""

    def _levels_text(self, kw: dict) -> str:
        """«Entrada ~X · Stop Y (riesgo Z USD) · Objetivo W / sin objetivo fijo · cierre previsto HH»."""
        parts = [f"Entrada ~{kw.get('price')}"]
        try:
            n = int(kw.get("contracts") or 1)
            risk = abs(float(kw["price"]) - float(kw["stop"])) / self.spec.tick_size * self.spec.tick_value * n
            parts.append(f"Stop {kw.get('stop')} (riesgo {risk:,.0f} USD)")
        except (KeyError, TypeError, ValueError, AttributeError):
            parts.append(f"Stop {kw.get('stop')}")
        parts.append(f"Objetivo {kw['tp']}" if kw.get("tp") not in (None, "") else "Sin objetivo fijo")
        exit_txt = self._planned_exit_text()
        if exit_txt:
            parts.append(exit_txt)
        return " · ".join(parts)

    def _notify_event(self, event: str, kw: dict):
        if self.notifier is None:
            return
        side = {1: "COMPRA", -1: "VENTA"}.get(int(kw["side"]) if str(kw.get("side", "")).lstrip("-").isdigit() else 0, "")
        detail = str(kw.get("detail", ""))
        if event == "FILL":
            self.notify(f"🟢 ENTRADA {side} {kw.get('contracts')} {self.cfg['symbol_search']} ({self._hora()})\n"
                        f"{self._levels_text(kw)}")
        elif event == "SIGNAL" and not self.execute:
            self.notify(f"📣 SEÑAL {side} {kw.get('contracts')} {self.cfg['symbol_search']} ({self._hora()}) — solo "
                        f"señal, no se envía la orden\n{self._levels_text(kw)}")
        elif event == "EXIT" and not self.execute:
            self.notify(f"⚪ SALIDA de la señal ({self._hora()}): {detail}")
        elif event == "SKIP" and "no se persigue" not in detail:
            if kw.get("price") not in (None, ""):
                self.notify(f"⏭️ SEÑAL {side} {self.cfg['symbol_search']} ({self._hora()}) — NO SE OPERA\n"
                            f"{self._levels_text(kw)}\nMotivo: {detail}")
            else:
                self.notify(f"⏭️ Hoy no se opera ({self._hora()}): {detail}")
        elif event == "STOP_PROPIO":
            self.notify(f"🛡️ El bracket no dejó un stop válido: el bot puso su propio stop en {kw.get('stop')}.")
        elif event == "ERROR":
            last = self.state.extra.get("last_error_msg")
            if last != detail:
                self.state.extra["last_error_msg"] = detail
                self.notify(f"⚠️ Error ({self._hora()}): {detail}")

    # ------------------------------------------------------------------ arranque
    def startup(self):
        self.client.login()
        accounts = self.client.accounts(only_active=True)
        for a in accounts:
            self.log(f"Cuenta disponible: id {a.get('id')} | {a.get('name')} | saldo {a.get('balance')} | "
                     f"simulada={a.get('simulated')} | puede operar={a.get('canTrade')}")
        allowed = set(int(a) for a in self.cfg["account_ids"])
        if allowed:
            cands = [a for a in accounts if int(a["id"]) in allowed]
            if not cands:
                raise ValueError(f"ninguna cuenta activa coincide con account_ids {sorted(allowed)}; "
                                 f"disponibles: {[(a['id'], a.get('name')) for a in accounts]}")
            self.account = cands[0]
        else:
            if not accounts:
                raise ValueError("la API no devuelve cuentas activas")
            self.account = accounts[0]
        simulated = self.account.get("simulated") is True
        self.execute = bool(self.cfg["execute"])
        if self.execute:
            problems = []
            if int(self.account["id"]) not in allowed:
                problems.append("la cuenta no está en account_ids")
            if not simulated:
                problems.append("la API no la marca como simulada (Topstep no admite bots en la Live Funded "
                                "Account y el proyecto solo automatiza cuentas simuladas)")
            if not self.account.get("canTrade", False):
                problems.append("la cuenta no puede operar (canTrade = false)")
            if problems:
                raise ValueError("no se permite ejecutar: " + "; ".join(problems))
        self.contract = self._pick_contract()
        self.spec = futures_spec(self.contract, int(self.cfg["max_contracts"]))
        self.log(f"Cuenta {self.account['id']} ({self.account.get('name')}), saldo {self.account.get('balance')}, "
                 f"simulada={simulated}. Contrato {self.contract['id']} tick {self.spec.tick_size} = "
                 f"{self.spec.tick_value} USD. Modo: {'EJECUCION' if self.execute else 'SOLO SENALES'}. "
                 f"Estrategia {self.cfg['strategy']} {self.cfg['params']}.")
        self.log("Recuerda: Topstep prohíbe VPS/VPN con la API; ejecuta el bot en tu PC y vigílalo.")
        sch = panel.session_schedule(self.cfg, self.now_fn())
        if sch:
            self.log(f"Horario: {panel.schedule_text(sch, self.cfg.get('display_tz'))}.")
        now = self.now_fn()
        self.bars = self._load_bars(now - timedelta(days=int(self.cfg["warmup_days"])), now)
        self.log(f"Historial cargado: {len(self.bars)} velas M1 desde {self.bars.index[0] if len(self.bars) else '-'}")
        bal = float(self.account.get("balance") or self.cfg["initial_balance"])
        self.notify(f"🤖 KatheBot arrancado en {'EJECUCIÓN' if self.execute else 'SOLO SEÑALES'} · cuenta "
                    f"{self.account['id']}\n{self._progress_text(bal)}\n{self._next_entry_text()}".strip())

    def _pick_contract(self) -> dict:
        found = self.client.contracts(self.cfg["symbol_search"], live=False)
        if self.cfg["contract_id"]:
            found = [c for c in found if c.get("id") == self.cfg["contract_id"]]
        active = [c for c in found if c.get("activeContract", True)]
        if not active:
            raise ValueError(f"no se encontró un contrato activo para {self.cfg['symbol_search']!r}: {found}")
        return active[0]

    def _load_bars(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Velas M1 cerradas entre start y end (UTC), pedidas en ventanas de 10 días (<= 14 400 velas,
        por debajo del límite de 20 000 por petición, sea cual sea el orden en que las devuelva la API)."""
        frames, cur = [], start
        while cur < end:
            nxt = min(end, cur + timedelta(days=10))
            chunk = self.client.bars(self.contract["id"], cur, nxt, limit=20000)
            if chunk:
                frames.append(bars_to_frame(chunk))
            cur = nxt
        if not frames:
            return pd.DataFrame(columns=["open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
        df = pd.concat(frames).sort_index()
        return df[~df.index.duplicated(keep="last")]

    # ------------------------------------------------------------------ decisión (motor de backtesting)
    def target(self) -> tuple[Target | None, dict]:
        md = MarketData(self.bars.copy(), self.spec)
        cfg = BacktestConfig(initial_equity=float(self.cfg["initial_balance"]), risk_pct=None, fixed_lots=1.0,
                             costs=CostModel(slippage_points=float(self.cfg["slippage_ticks"]),
                                             commission_per_lot_rt=float(self.cfg["commission_per_contract_rt"])),
                             max_spread_points=0.0)
        res = run_backtest(md, self.strategy_factory(), cfg)
        self._bt_trades = res.trades
        info = {"n_trades": int(len(res.trades)), "n_skipped": int(len(res.skipped))}
        tr = res.trades
        open_tr = tr[tr["exit_reason"] == "end_of_test"] if len(tr) else tr
        if not len(open_tr):
            return None, info
        r = open_tr.iloc[-1]
        tp = float(r["initial_tp"]) if pd.notna(r["initial_tp"]) else None
        return Target(key=f"{pd.Timestamp(r['entry_time']):%Y%m%d%H%M}{'L' if r['side'] > 0 else 'S'}",
                      side=int(r["side"]), entry_time_utc=pd.Timestamp(r["entry_time_utc"]),
                      entry_price=float(r["entry_ref_price"]) if pd.notna(r.get("entry_ref_price")) else float(r["entry_price"]),
                      stop=float(r["final_stop"]), tp=tp), info

    # ------------------------------------------------------------------ riesgo
    def _update_risk(self, balance: float) -> tuple[bool, str]:
        """Devuelve (se permite abrir, motivo). Actualiza el día, el máximo de fin de día y los bloqueos."""
        st, c = self.state, self.cfg
        day = topstep_day_key(self.now_fn())
        if st.max_eod_balance is None:
            st.max_eod_balance = float(c["initial_balance"])
        if st.day_key != day:
            if st.day_key is not None and st.last_balance is not None:
                st.max_eod_balance = max(st.max_eod_balance, st.last_balance)
            st.day_key, st.day_start_balance = day, balance
        st.last_balance = balance
        floor = (float(c["mll_floor_override"]) if c["mll_floor_override"] is not None
                 else min(float(c["initial_balance"]), st.max_eod_balance - float(c["mll_usd"])))
        room = balance - floor
        pnl_day = balance - (st.day_start_balance if st.day_start_balance is not None else balance)
        risk = float(c["risk_usd_per_trade"])
        if st.hard_lock:
            return False, f"bloqueo permanente: {st.hard_lock}"
        if room < float(c["mll_buffer_usd"]):
            st.hard_lock = f"a {room:.0f} USD del Maximum Loss Limit estimado ({floor:.0f})"
            return False, st.hard_lock
        if pnl_day <= -float(c["daily_loss_limit_usd"]):
            st.locked_day, st.locked_reason = day, f"pérdida del día {pnl_day:.0f} USD"
        if st.locked_day == day:
            return False, f"bloqueado hoy: {st.locked_reason}"
        if pnl_day - risk <= -float(c["daily_loss_limit_usd"]):
            return False, "otra pérdida completa superaría la pérdida diaria máxima"
        if room - risk < float(c["mll_buffer_usd"]):
            return False, "otra pérdida completa acercaría demasiado la cuenta al Maximum Loss Limit"
        return True, ""

    def contracts_for(self, stop_ticks: int) -> int:
        per_contract = stop_ticks * self.spec.tick_value + float(self.cfg["commission_per_contract_rt"])
        n = int(math.floor(float(self.cfg["risk_usd_per_trade"]) / per_contract)) if per_contract > 0 else 0
        return min(n, int(self.cfg["max_contracts"]))

    # ------------------------------------------------------------------ órdenes
    def _my_position(self) -> dict | None:
        cid = self.contract["id"]
        pos = [p for p in self.client.open_positions(int(self.account["id"])) if p.get("contractId") == cid]
        return pos[0] if pos else None

    def _my_orders(self) -> list[dict]:
        cid = self.contract["id"]
        return [o for o in self.client.open_orders(int(self.account["id"])) if o.get("contractId") == cid]

    def _round(self, price: float) -> float:
        t = self.spec.tick_size
        return round(round(price / t) * t, self.spec.digits)

    def _cancel_all_orders(self):
        for o in self._my_orders():
            try:
                self.client.cancel_order(int(self.account["id"]), int(o["id"]))
            except ProjectXError as e:
                self.log(f"No se pudo cancelar la orden {o.get('id')}: {e}")

    def _close(self, why: str):
        if self.execute:
            try:
                self.client.close_position(int(self.account["id"]), self.contract["id"])
            except ProjectXError as e:
                self.log(f"ERROR al cerrar: {e}")
                self.journal("ERROR", detail=f"cierre: {e}")
                return
            self._cancel_all_orders()
        else:
            why += self._virtual_result()
        self.journal("EXIT", side=self.state.position_side, detail=why)
        self.log(f"Cierre: {why}")
        self._set_position()

    def _virtual_result(self) -> str:
        """Modo señales: resultado teórico de la señal que se cierra, según el mismo backtest (costes incluidos),
        y acumulado de todas las señales. Sirve de validación prospectiva sin arriesgar la cuenta."""
        tr = getattr(self, "_bt_trades", None)
        key = self.state.position_key
        if tr is None or not len(tr) or not key:
            return ""
        keys = [f"{pd.Timestamp(t):%Y%m%d%H%M}{'L' if sd > 0 else 'S'}" for t, sd in zip(tr["entry_time"], tr["side"])]
        rows = tr[[k == key for k in keys]]
        rows = rows[rows["exit_reason"] != "end_of_test"]
        if not len(rows):
            return ""
        n = int(self.state.extra.get("virtual_contracts") or 1)
        pnl = float(rows.iloc[-1]["net_pnl"]) * n
        ex = self.state.extra
        ex["virtual_n"] = int(ex.get("virtual_n", 0)) + 1
        ex["virtual_wins"] = int(ex.get("virtual_wins", 0)) + (1 if pnl > 0 else 0)
        ex["virtual_total"] = round(float(ex.get("virtual_total", 0.0)) + pnl, 2)
        return (f"; resultado teórico {pnl:+.2f} USD ({n} contrato(s)); acumulado {ex['virtual_total']:+.2f} USD "
                f"en {ex['virtual_n']} señales ({ex['virtual_wins']} ganadoras)")

    def ensure_protection(self, pos: dict, stop_price: float, tp_price: float | None) -> bool:
        """Toda posición debe tener un stop del lado correcto. Si falta, lo pone; si no puede, cierra."""
        side = 1 if int(pos.get("type", 1)) == 1 else -1
        avg = float(pos.get("averagePrice") or 0.0)
        prot_side = SIDE_SELL if side > 0 else SIDE_BUY
        stops = [o for o in self._my_orders() if int(o.get("type", 0)) == TYPE_STOP and int(o.get("side", -1)) == prot_side]
        good = [o for o in stops if o.get("stopPrice") is not None and
                ((side > 0 and float(o["stopPrice"]) < avg) or (side < 0 and float(o["stopPrice"]) > avg))]
        for o in stops:
            if o not in good:
                self.client.cancel_order(int(self.account["id"]), int(o["id"]))
                self.log(f"Stop en el lado equivocado cancelado ({o.get('stopPrice')}).")
        if good:
            return True
        try:
            self.client.place_order(int(self.account["id"]), self.contract["id"], TYPE_STOP, prot_side,
                                    int(pos["size"]), stop_price=self._round(stop_price), custom_tag="KQ-SL")
            self.journal("STOP_PROPIO", stop=self._round(stop_price), detail="el bracket no dejó un stop válido")
            if tp_price is not None and not any(int(o.get("type", 0)) == TYPE_LIMIT and int(o.get("side", -1)) == prot_side
                                                for o in self._my_orders()):
                self.client.place_order(int(self.account["id"]), self.contract["id"], TYPE_LIMIT, prot_side,
                                        int(pos["size"]), limit_price=self._round(tp_price), custom_tag="KQ-TP")
            return True
        except ProjectXError as e:
            self.log(f"ERROR: no se pudo poner el stop ({e}). Se cierra la posición y se bloquea el bot.")
            self.state.hard_lock = f"no se pudo proteger una posición: {e}"
            self._close("sin stop de protección")
            return False

    def _enter(self, tgt: Target, ref_price: float) -> bool:
        """True si entra (o, en modo señales, si entraría)."""
        stop_dist = abs(tgt.entry_price - tgt.stop)
        stop_ticks = int(round(stop_dist / self.spec.tick_size))
        tp_ticks = int(round(abs(tgt.tp - tgt.entry_price) / self.spec.tick_size)) if tgt.tp else None
        n = self.contracts_for(stop_ticks)
        side_txt = "COMPRA" if tgt.side > 0 else "VENTA"
        self.state.last_entry_key = tgt.key
        if stop_ticks <= 0:
            self.journal("SKIP", side=tgt.side, detail="distancia de stop nula")
            return False
        stop_px = ref_price - tgt.side * stop_ticks * self.spec.tick_size
        tp_px = ref_price + tgt.side * tp_ticks * self.spec.tick_size if tp_ticks else None
        if n < 1:
            per = stop_ticks * self.spec.tick_value + float(self.cfg["commission_per_contract_rt"])
            msg = (f"1 contrato arriesgaría {per:.0f} USD, más que el riesgo permitido "
                   f"({float(self.cfg['risk_usd_per_trade']):.0f}); no se entra")
            self.journal("SKIP", side=tgt.side, price=ref_price, stop=self._round(stop_px),
                         tp=self._round(tp_px) if tp_px else "", detail=msg)
            self.log(f"Señal {side_txt} descartada: {msg}.")
            return False
        self.journal("SIGNAL", side=tgt.side, contracts=n, price=ref_price, stop=self._round(stop_px),
                     tp=self._round(tp_px) if tp_px else "", detail=f"{stop_ticks} ticks de stop; clave {tgt.key}")
        if not self.execute:
            self.state.extra["virtual_contracts"] = n
            self.log(f"SEÑAL {side_txt} {n} contrato(s) ~{ref_price} | SL {self._round(stop_px)} | "
                     f"TP {self._round(tp_px) if tp_px else '-'} (solo señales: no se envía la orden)")
            return True
        side_code = SIDE_BUY if tgt.side > 0 else SIDE_SELL
        try:
            oid = self.client.place_order(int(self.account["id"]), self.contract["id"], TYPE_MARKET, side_code, n,
                                          custom_tag=f"KQ-{tgt.key}", stop_loss_ticks=stop_ticks,
                                          take_profit_ticks=tp_ticks)
        except ProjectXError as e:
            # p. ej. brackets no admitidos (modo «Position Brackets») o convención de signo distinta:
            # se reintenta sin brackets y ensure_protection pone el stop y el objetivo a continuación
            self.journal("ERROR", side=tgt.side, contracts=n, detail=f"entrada con brackets rechazada: {e}; reintento sin brackets")
            self.log(f"Entrada con brackets rechazada ({e}); se reintenta sin brackets.")
            try:
                oid = self.client.place_order(int(self.account["id"]), self.contract["id"], TYPE_MARKET, side_code, n,
                                              custom_tag=f"KQ-{tgt.key}-nb")
            except ProjectXError as e2:
                self.journal("ERROR", side=tgt.side, contracts=n, detail=f"entrada rechazada: {e2}")
                self.log(f"Entrada rechazada: {e2}")
                return False
        pos = None
        for _ in range(10):
            pos = self._my_position()
            if pos:
                break
            self.sleep(1.0)
        if not pos:
            self.journal("ERROR", detail=f"orden {oid} sin posición tras 10 s; se cancelan órdenes")
            self._cancel_all_orders()
            return False
        avg = float(pos.get("averagePrice") or ref_price)
        stop_px = avg - tgt.side * stop_ticks * self.spec.tick_size
        tp_px = avg + tgt.side * tp_ticks * self.spec.tick_size if tp_ticks else None
        self.state.position_key, self.state.position_side, self.state.position_stop = tgt.key, tgt.side, self._round(stop_px)
        self.state.extra["entry_balance"] = self.state.last_balance
        self.journal("FILL", side=tgt.side, contracts=int(pos.get("size", n)), price=avg, stop=self._round(stop_px),
                     tp=self._round(tp_px) if tp_px else "", detail=f"orden {oid}; esperado ~{ref_price}")
        self.log(f"ENTRADA {side_txt} {pos.get('size', n)} a {avg} | SL {self._round(stop_px)}")
        return self.ensure_protection(pos, stop_px, tp_px)

    def _sync_stop(self, pos: dict, new_stop: float):
        """Trailing: solo acerca el stop, nunca lo aleja."""
        side = self.state.position_side
        cur = self.state.position_stop
        new_stop = self._round(new_stop)
        if cur is not None and ((side > 0 and new_stop <= cur) or (side < 0 and new_stop >= cur)):
            return
        prot_side = SIDE_SELL if side > 0 else SIDE_BUY
        stops = [o for o in self._my_orders() if int(o.get("type", 0)) == TYPE_STOP and int(o.get("side", -1)) == prot_side]
        if not self.execute:
            self.journal("MODIFY", side=side, stop=new_stop, detail="trailing (solo señales)")
            self.state.position_stop = new_stop
            return
        for o in stops:
            try:
                self.client.modify_order(int(self.account["id"]), int(o["id"]), stop_price=new_stop)
            except ProjectXError as e:
                self.journal("ERROR", detail=f"no se pudo mover el stop: {e}")
                return
        self.state.position_stop = new_stop
        self.journal("MODIFY", side=side, stop=new_stop, detail="trailing")

    # ------------------------------------------------------------------ paso
    def _refresh_bars(self, now: datetime):
        if len(self.bars):
            last_utc = pd.Timestamp(server_to_utc(pd.DatetimeIndex([self.bars.index[-1]]))[0]).to_pydatetime()
            start = last_utc.replace(tzinfo=timezone.utc) - timedelta(minutes=5)
        else:
            start = now - timedelta(days=int(self.cfg["warmup_days"]))
        fresh = self._load_bars(start, now)
        if len(fresh):
            self.bars = pd.concat([self.bars, fresh]).sort_index()
            self.bars = self.bars[~self.bars.index.duplicated(keep="last")]

    def _set_position(self, key=None, side=0, stop=None):
        self.state.position_key, self.state.position_side, self.state.position_stop = key, side, stop

    def step(self) -> dict:
        now = self.now_fn()
        self._refresh_bars(now)
        out = {"new_bar": False}
        acct = next((a for a in self.client.accounts(only_active=True) if int(a["id"]) == int(self.account["id"])), None)
        balance = float(acct["balance"]) if acct else float(self.state.last_balance or self.cfg["initial_balance"])
        st = self.state
        prev_day, prev_hard, prev_locked = st.day_key, st.hard_lock, st.locked_day
        prev_pnl = (st.last_balance - st.day_start_balance) if st.last_balance is not None and st.day_start_balance is not None else None
        can_open, why = self._update_risk(balance)
        out["can_open"], out["why"] = can_open, why
        self._risk_now = (can_open, why)
        panel.append_balance(self.dir / "saldo.csv", now, balance)
        if self.execute and self.daily_summary and prev_day is not None and st.day_key != prev_day and prev_pnl is not None:
            self.notify(f"📊 Resumen del día {prev_day}: {prev_pnl:+,.2f} USD\n{self._progress_text(balance)}\n"
                        f"Distancia al MLL: {self._risk_snapshot()['room']:,.0f} USD\n{self._next_entry_text()}".strip())
        if st.hard_lock and st.hard_lock != prev_hard:
            self.notify(f"⛔ Bot bloqueado: {st.hard_lock}. No abrirá más operaciones hasta que lo revises.")
        elif st.locked_day and st.locked_day != prev_locked:
            self.notify(f"⏸️ Sin más operaciones hoy: {st.locked_reason}.")
        pend = st.extra.get("exit_pending")
        if pend and now - datetime.fromisoformat(pend) >= timedelta(seconds=45):
            eb = st.extra.pop("entry_balance", None)
            st.extra.pop("exit_pending", None)
            why_exit = st.extra.pop("exit_why", "")
            res = f"{balance - float(eb):+,.2f} USD" if eb is not None else "(sin saldo de entrada)"
            icon = "✅" if eb is not None and balance - float(eb) > 0 else "🔴"
            self.notify(f"{icon} SALIDA ({why_exit}): resultado {res} con comisiones\n{self._progress_text(balance)}")
        hour = pd.Timestamp(now).floor("h")
        if hour != self._heartbeat_hour:              # una línea por hora para vigilar que sigue vivo
            self._heartbeat_hour = hour
            self.log(f"Funcionando. Saldo {balance:.2f}; posición del bot: "
                     f"{ {1: 'compra', -1: 'venta'}.get(self.state.position_side, 'ninguna') }; "
                     f"última vela {self.bars.index[-1] if len(self.bars) else '-'} (hora servidor).")
        pos = self._my_position() if self.execute else None
        hard_or_day = bool(self.state.hard_lock) or self.state.locked_day == self.state.day_key
        if hard_or_day and ((self.execute and pos and self.state.position_key) or (not self.execute and self.state.position_key)):
            self._close(f"bloqueo de riesgo: {why}")
            pos = None
        last_bar = self.bars.index[-1] if len(self.bars) else None
        if last_bar is None or last_bar == self.last_eval_bar:
            self.state.save(self.state_path)
            return out
        self.last_eval_bar = last_bar
        out["new_bar"] = True
        tgt, info = self.target()
        out.update(info)
        out["target"] = None if tgt is None else {"key": tgt.key, "side": tgt.side, "stop": tgt.stop, "tp": tgt.tp}
        ref_price = float(self.bars["close"].iloc[-1])
        if self.execute:
            if pos and self.state.position_key is None:
                if self._foreign_pos != pos.get("id"):             # una vez por posición, no en cada vela
                    self._foreign_pos = pos.get("id")
                    self.log("Hay una posición en este contrato que no abrió este turno (otro turno o a mano): "
                             "no opera mientras exista.")
                self.state.save(self.state_path)
                return out
            if not pos and self.state.position_key is not None:
                self.journal("EXIT", side=self.state.position_side, detail="cerrada por el bróker (stop u objetivo)")
                self._cancel_all_orders()
                self._set_position()
        # salidas: la estrategia ya no quiere la posición, o quiere otra
        if self.state.position_key and (tgt is None or tgt.key != self.state.position_key):
            self._close("la estrategia ya no quiere la posición" if tgt is None else "la estrategia cambió de posición")
            pos = None
        elif self.state.position_key and tgt is not None:
            if self.execute and pos:
                self.ensure_protection(pos, tgt.stop, tgt.tp)
            if self.state.position_key:
                self._sync_stop(pos, tgt.stop)
        # entradas
        if tgt is not None and not self.state.position_key and tgt.key != self.state.last_entry_key:
            now_ts = pd.Timestamp(now)
            now_naive = now_ts.tz_convert(None) if now_ts.tzinfo else now_ts
            age = now_naive - tgt.entry_time_utc
            if age > pd.Timedelta(minutes=int(self.cfg["entry_max_age_min"])):
                self.state.last_entry_key = tgt.key
                self.journal("SKIP", side=tgt.side, detail=f"señal de hace {age}; no se persigue")
            elif not can_open:
                self.state.last_entry_key = tgt.key
                dist = abs(tgt.entry_price - tgt.stop)
                self.journal("SKIP", side=tgt.side, price=ref_price, stop=self._round(ref_price - tgt.side * dist),
                             tp=self._round(ref_price + tgt.side * abs(tgt.tp - tgt.entry_price)) if tgt.tp else "",
                             detail=why)
                self.log(f"Señal descartada: {why}")
            elif self._enter(tgt, ref_price) and not self.execute:
                # en modo señales se sigue una posición virtual para registrar el trailing y la salida
                self._set_position(tgt.key, tgt.side, self._round(tgt.stop))
        if self.execute and self.state.position_key is None and not self._my_position():
            orphans = self._my_orders()
            if orphans:
                self._cancel_all_orders()
                self.journal("CANCEL", detail=f"{len(orphans)} órdenes huérfanas canceladas")
        self.state.save(self.state_path)
        return out

    # ------------------------------------------------------------------ panel
    @property
    def panel_path(self) -> Path:
        return self.dir / "panel.html"

    def _risk_snapshot(self) -> dict:
        st, c = self.state, self.cfg
        bal = st.last_balance if st.last_balance is not None else (self.account or {}).get("balance")
        bal = float(bal) if bal is not None else None
        floor = (float(c["mll_floor_override"]) if c["mll_floor_override"] is not None
                 else min(float(c["initial_balance"]), float(st.max_eod_balance or c["initial_balance"]) - float(c["mll_usd"])))
        can_open, why = self._risk_now
        return {"balance": bal, "initial": float(c["initial_balance"]),
                "pnl_total": None if bal is None else bal - float(c["initial_balance"]),
                "pnl_day": None if bal is None or st.day_start_balance is None else bal - float(st.day_start_balance),
                "day_key": st.day_key, "floor": floor, "room": None if bal is None else bal - floor,
                "buffer": float(c["mll_buffer_usd"]), "dll": float(c["daily_loss_limit_usd"]),
                "risk_per_trade": float(c["risk_usd_per_trade"]), "max_contracts": int(c["max_contracts"]),
                "can_open": can_open, "why": why, "hard_lock": st.hard_lock,
                "locked_today": st.locked_day is not None and st.locked_day == st.day_key,
                "target": float(c["profit_target_usd"]) if c.get("profit_target_usd") else None,
                "consistency_pct": float(c["consistency_pct"])}

    def _position_snapshot(self, last_price: float | None) -> dict | None:
        if self.execute:
            pos = self._my_position()
            if not pos:
                return None
            side = 1 if int(pos.get("type", 1)) == 1 else -1
            size, avg = int(pos.get("size", 0)), float(pos.get("averagePrice") or 0.0)
            unreal = None
            if last_price is not None and avg:
                unreal = (last_price - avg) / self.spec.tick_size * self.spec.tick_value * size * side
            return {"side": side, "size": size, "avg": avg, "stop": self.state.position_stop,
                    "unrealized": unreal, "orders": self._my_orders(), "mine": self.state.position_key is not None}
        if self.state.position_key:
            return {"side": self.state.position_side, "size": "(señal)", "avg": "–", "stop": self.state.position_stop,
                    "unrealized": None, "orders": []}
        return None

    def panel_data(self) -> dict:
        now = self.now_fn()
        if self._trades_at is None or now - self._trades_at >= timedelta(minutes=5):
            self._trades_at = now
            try:
                self._trades = self.client.trades(int(self.account["id"]), now - timedelta(days=int(self.cfg["trades_days"])))
            except ProjectXError as e:
                self.log(f"No se pudieron leer las ejecuciones de la cuenta para el panel: {e}")
        last_price = float(self.bars["close"].iloc[-1]) if len(self.bars) else None
        last_bar_local = "-"
        if len(self.bars):
            last_bar_local = panel.fmt_local(server_to_utc(pd.DatetimeIndex([self.bars.index[-1]]))[0],
                                             self.cfg.get("display_tz"), "%d/%m %H:%M")
        pos = self._position_snapshot(last_price)
        alerts = []
        if pos and self.execute and not pos.get("mine"):
            alerts.append("Hay una posición en este contrato que no abrió este turno (otro turno o a mano): "
                          "este turno no opera mientras exista.")
        panel_file = self.dir / "panel.html"
        href = panel_file.as_posix() if not panel_file.is_absolute() else panel_file.resolve().as_uri()
        return {"generated_utc": now, "tz": self.cfg.get("display_tz"), "name": self.name, "panel_href": href,
                "mode": "EJECUCION" if self.execute else "SENALES",
                "account": {k: (self.account or {}).get(k) for k in ("id", "name", "simulated")},
                "contract": (self.contract or {}).get("id"), "tick_size": self.spec.tick_size if self.spec else None,
                "tick_value": self.spec.tick_value if self.spec else None,
                "strategy": self.cfg["strategy"], "params": self.cfg["params"],
                "schedule": panel.session_schedule(self.cfg, now, upcoming_only=self.state.position_key is None),
                "risk": self._risk_snapshot(), "position": pos, "alerts": alerts,
                "last_price": last_price, "last_bar_local": last_bar_local,
                "journal": panel.read_journal(self.dir / "diario.csv"),
                "balance_hist": panel.read_balance(self.dir / "saldo.csv"),
                "trades": self._trades, "stats": panel.trade_stats(self._trades, topstep_day_key),
                "trades_days": int(self.cfg["trades_days"])}

    def write_panel(self) -> Path | None:
        """Reescribe panel.html. Un fallo del panel nunca detiene el bot."""
        try:
            self._last_panel = self.panel_data()
            panel.write_atomic(self.panel_path, panel.render_panel(self._last_panel))
            self._panel_error = None
            return self.panel_path
        except Exception as e:  # noqa: BLE001 - el panel es informativo
            if str(e) != self._panel_error:
                self._panel_error = str(e)
                self.log(f"No se pudo actualizar el panel: {e}")
            return None

    def run(self):
        run_many([self], sleep=self.sleep)


def run_many(bots: list[TopstepBot], sleep=time.sleep, rounds: int | None = None,
             overview: str | Path | None = None):
    """Bucle de varios mercados con una sola sesión de la API: cada ronda da un paso a cada bot y
    actualiza su panel. Un error de un mercado no para a los demás."""
    from .notify import Heartbeat
    errors = 0
    poll = min(float(b.cfg["poll_seconds"]) for b in bots)
    beats = [Heartbeat(u) for u in sorted({b.cfg.get("heartbeat_url") for b in bots} - {None, ""})]
    done = 0
    while rounds is None or done < rounds:
        failed = False
        for b in bots:
            try:
                b.step()
                b.write_panel()
            except ProjectXError as e:
                failed = True
                b.log(f"Error de la API ({errors + 1}): {e}")
                b.journal("ERROR", detail=str(e))
        write_overview(bots, overview or OVERVIEW_FILE)
        for hb in beats:
            hb.beat()
        errors = errors + 1 if failed else 0
        if errors:
            sleep(min(300, 15 * errors))
        sleep(poll)
        done += 1


def session_hours(cfg: dict) -> set[int] | None:
    """Horas UTC que ocupa un turno SESSION_DRIFT, incluida la hora de salida; None para otras estrategias."""
    if cfg.get("strategy") != "SESSION_DRIFT":
        return None
    p = cfg.get("params") or {}
    h_in, h_out = int(p.get("h_in", 0)), int(p.get("h_out", 8))
    return {(h_in + k) % 24 for k in range((h_out - h_in) % 24 + 1)}


OVERVIEW_FILE = "panel_general.html"


def write_overview(bots: list[TopstepBot], path: str | Path = OVERVIEW_FILE) -> Path | None:
    """Página única con todos los turnos (en la carpeta desde la que se arranca el bot)."""
    try:
        items = [b._last_panel for b in bots if b._last_panel]
        if not items:
            return None
        panel.write_atomic(Path(path), panel.render_overview(items))
        return Path(path)
    except Exception as e:  # noqa: BLE001 - el panel es informativo
        if bots:
            bots[0].log(f"No se pudo actualizar el panel general: {e}")
        return None


def check_configs(cfgs: list[dict]) -> None:
    """Varias configuraciones a la vez: cada una con su carpeta. En una misma cuenta solo pueden EJECUTAR
    varias si son turnos SESSION_DRIFT que no se solapan: así nunca hay dos posiciones abiertas a la vez, y la
    pérdida diaria y el colchón del MLL se controlan con el saldo común de la cuenta. Cualquier otra combinación
    en ejecución se rechaza (su riesgo conjunto no está coordinado)."""
    dirs = [str(Path(c["state_dir"]).resolve()) for c in cfgs]
    if len(set(dirs)) != len(dirs):
        raise ValueError("cada configuración necesita su propio state_dir (p. ej. topstep_state_mnq)")
    by_acc: dict = {}
    for c in cfgs:
        if c["execute"]:
            for acc in c["account_ids"]:
                by_acc.setdefault(acc, []).append(c)
    for acc, cs in by_acc.items():
        names = [c.get("label") or c["symbol_search"] for c in cs]
        hours = [session_hours(c) for c in cs]
        if len(cs) > 1 and any(h is None for h in hours):
            raise ValueError(f"la cuenta {acc} tiene varias configuraciones en EJECUCION ({', '.join(names)}): solo una "
                             "puede ejecutar, salvo turnos SESSION_DRIFT que no se solapen; pon las demás en \"execute\": false")
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                both = hours[i] & hours[j]
                if both:
                    raise ValueError(f"la cuenta {acc}: los turnos {names[i]} y {names[j]} se solapan (horas UTC "
                                     f"{sorted(both)}); solo pueden ejecutar a la vez turnos que no coincidan")


# ---------------------------------------------------------------------- utilidades de línea de órdenes
def pid_alive(pid: int) -> bool:
    """¿Sigue vivo el proceso? En Windows no se usa os.kill(pid, 0): allí os.kill TERMINA el proceso."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259               # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class InstanceLock:
    def __init__(self, path: Path):
        self.path = path

    def acquire(self, _retry: bool = True):
        self.path.parent.mkdir(parents=True, exist_ok=True)       # la carpeta de un mercado nuevo aún no existe
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(self.path.read_text().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if _retry and not pid_alive(pid):         # candado de un bot que se cerró de golpe (apagón, reinicio)
                self.path.unlink(missing_ok=True)
                return self.acquire(_retry=False)
            raise SystemExit(f"Ya hay otro bot usando {self.path.parent} (proceso {pid}). Ciérralo antes de "
                             f"arrancar otro.")
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        atexit.register(self.release)

    def release(self):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def export_bars(bot: TopstepBot, days: int, out: Path):
    """Descarga velas M1 del contrato activo en el formato de exportación de MT5 (hora NY+7, spread 1 tick),
    para el motor de investigación. Solo cubre el historial de ESTE contrato."""
    bot.client.login()
    bot.contract = bot._pick_contract()
    bot.spec = futures_spec(bot.contract, 1)
    now = datetime.now(timezone.utc)
    df = bot._load_bars(now - timedelta(days=days), now)
    out.parent.mkdir(parents=True, exist_ok=True)
    w = df.copy()
    w.index = w.index.strftime("%Y.%m.%d %H:%M")
    w.index.name = "time"
    w.to_csv(out, float_format=f"%.{bot.spec.digits}f")
    spec_path = out.with_name(out.stem.replace("_M1", "") + "_spec.json")
    spec_path.write_text(json.dumps({**bot.spec.to_dict(), "source": "TopstepX/ProjectX", "contract": bot.contract["id"]},
                                    indent=2, default=str), encoding="utf-8")
    print(f"{len(df)} velas -> {out} ; especificación -> {spec_path}")


PLACEHOLDERS = {"", "tu_usuario_de_topstepx", "tu_usuario", "la_clave_nueva", "tu_api_key", "pega_aquí_la_clave_nueva",
                "pega_aqui_la_clave_nueva"}


KEY_FILE = "clave_topstepx.txt"
USER_FILE = "usuario_topstepx.txt"


def ask_credentials(env=None, input_fn=input, getpass_fn=None, key_file: str | Path | None = KEY_FILE,
                    user_file: str | Path | None = USER_FILE, interactive: bool = True) -> tuple[str, str]:
    """Usuario y API key. La clave sale, por este orden, de la variable TOPSTEPX_API_KEY, del archivo
    ``clave_topstepx.txt`` de la carpeta actual (solo la clave, en la primera línea) o se pide por
    teclado sin mostrarla. El usuario sale de TOPSTEPX_USERNAME, de ``usuario_topstepx.txt`` o se pide por
    teclado. Sin ``interactive`` (arranque automático) nunca pregunta: si falta algo, termina."""
    import getpass
    env = os.environ if env is None else env
    getpass_fn = getpass_fn or getpass.getpass

    def clean(v):
        return (v or "").strip().strip('"').strip("'").strip().lstrip("\ufeff")

    def first_line(path):
        lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
        return clean(lines[0]) if lines else ""

    user = clean(env.get("TOPSTEPX_USERNAME"))
    key = clean(env.get("TOPSTEPX_API_KEY"))
    if key.lower() in PLACEHOLDERS and key_file and Path(key_file).exists():
        key = first_line(key_file)
        print(f"(clave leída de {key_file})")
    if user.lower() in PLACEHOLDERS and user_file and Path(user_file).exists():
        user = first_line(user_file)
    if not interactive and (user.lower() in PLACEHOLDERS or key.lower() in PLACEHOLDERS):
        raise SystemExit(f"Arranque automático: faltan {USER_FILE} o {KEY_FILE} en esta carpeta. "
                         "Créalos con  python -m kq.live.autoinicio --instalar")
    if user.lower() in PLACEHOLDERS:
        user = clean(input_fn("Usuario de TopstepX: "))
    if key.lower() in PLACEHOLDERS:
        key = clean(getpass_fn("API key de TopstepX (no se verá al escribir; pégala con clic derecho y pulsa Enter): "))
    if user.lower() in PLACEHOLDERS or key.lower() in PLACEHOLDERS:
        raise SystemExit("Falta el usuario o la API key de TopstepX.")
    print(f"(usuario '{user}'; clave recibida: {len(key)} caracteres)")
    return user, key


def run_bots(cfgs: list[dict], client: ProjectXClient, notifier=None, once: bool = False,
             open_panels: bool = True) -> int:
    """Crea y arranca un bot por configuración y los hace funcionar juntos hasta que se paren."""
    bots = [TopstepBot(c, client, notifier=notifier) for c in cfgs]
    for b in [b for b in bots if b.cfg["execute"]][1:]:
        b.daily_summary = False
    started = []
    for b in bots:
        try:
            b.startup()
            started.append(b)
        except (ValueError, ProjectXError) as e:
            if b.cfg["execute"] or len(bots) == 1:
                raise
            print(f"[{b.name}] no se pudo arrancar ({e}); los demás mercados siguen.")
    if once:
        for b in started:
            print(json.dumps(b.step(), default=str))
            b.write_panel()
        return 0
    for b in started:
        path = b.write_panel()
        if path:
            b.log(f"Panel del turno: {path.resolve()}")
    general = write_overview(started)
    if general:
        print(f"PANEL GENERAL (todos los turnos): {general.resolve()}  (ábrelo con doble clic; se actualiza solo)")
        if open_panels and any(b.cfg["open_panel"] for b in started):
            import webbrowser
            webbrowser.open(general.resolve().as_uri())
    run_many(started)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bot KatheQuant para TopstepX (ProjectX API)")
    ap.add_argument("--config", required=True, action="append",
                    help="archivo de configuración; repítelo para varios mercados (p. ej. oro y Nasdaq)")
    ap.add_argument("--once", action="store_true", help="un solo paso y termina")
    ap.add_argument("--auto", action="store_true",
                    help="modo desatendido: no pregunta nada (usuario y clave en archivos) y, si algo falla, "
                         "vuelve a arrancar cada 60 s")
    ap.add_argument("--export-bars", type=int, default=None, help="descargar N días de velas M1 y terminar")
    ap.add_argument("--out", default="KQ_MGC_M1.csv")
    ap.add_argument("--test-login", action="store_true", help="solo comprobar el inicio de sesión y listar las cuentas")
    a = ap.parse_args(argv)
    cfgs = [load_config(c) for c in a.config]
    check_configs(cfgs)
    cfg = cfgs[0]
    user, key = ask_credentials(interactive=not a.auto)
    client = ProjectXClient(username=user, api_key=key, base_url=cfg["base_url"])
    if a.test_login:
        try:
            client.login()
        except ProjectXError as e:
            print(f"NO se pudo iniciar sesión: {e}")
            return 1
        print("Inicio de sesión correcto. Cuentas activas:")
        for acc in client.accounts(only_active=True):
            print(f"  id {acc.get('id')} | {acc.get('name')} | saldo {acc.get('balance')} | "
                  f"simulada={acc.get('simulated')} | puede operar={acc.get('canTrade')}")
        return 0
    if a.export_bars:
        export_bars(TopstepBot(cfg, client), a.export_bars, Path(a.out))
        return 0
    from .notify import load_notifier
    notifier = load_notifier()
    print("Avisos por Telegram: activados." if notifier else
          "Avisos por Telegram: no configurados (opcional: python -m kq.live.notify --setup).")

    def tell(text):
        if notifier is not None:
            notifier.send(f"[KatheBot] {text}")

    locks = [InstanceLock(Path(c["state_dir"]) / "bot.lock") for c in cfgs]
    for lock in locks:
        lock.acquire()
    first, last_err = True, None
    try:
        while True:
            try:
                return run_bots(cfgs, client, notifier, once=a.once, open_panels=first)
            except KeyboardInterrupt:
                print("Detenido por el usuario. Las órdenes y posiciones abiertas NO se tocan al salir.")
                tell("⏹️ Bot detenido por el usuario. Si había una posición abierta, conserva su stop en Topstep.")
                return 0
            except Exception as e:
                if str(e) != last_err:
                    tell(f"💥 El bot se ha parado por un error: {e}. "
                         + ("Se vuelve a intentar cada 60 s." if a.auto else
                            "Revisa el PC. Las posiciones abiertas conservan su stop."))
                last_err = str(e)
                if not a.auto:
                    raise
                print(f"Error: {e}. Se vuelve a intentar en 60 s (Ctrl+C para parar).")
            first = False
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                print("Detenido por el usuario.")
                return 0
            client = ProjectXClient(username=user, api_key=key, base_url=cfg["base_url"])
    finally:
        for lock in locks:
            lock.release()
        if notifier is not None:
            notifier.flush()


if __name__ == "__main__":
    sys.exit(main())
