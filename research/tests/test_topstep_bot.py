"""Bot de TopstepX contra un servidor ProjectX simulado (sin red ni cuentas reales)."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from kq.live import topstep_bot as tb
from kq.live.projectx import ProjectXClient, ProjectXError
from kq.strategies.base import Enter, Exit
from kq.strategies.scripted import Scripted
from kq.synth import generate_m1
from kq.timeutil import server_to_utc, to_ns


def _iso(ts):
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class FakeGateway:
    """Servidor ProjectX mínimo: cuentas, contrato MGC, velas, órdenes, brackets y posiciones."""

    def __init__(self, df_server, simulated=True, brackets="ok", fail_stop=False, balance=50000.0):
        utc = pd.DatetimeIndex(server_to_utc(df_server.index))
        self.all_bars = [{"t": _iso(t), "o": round(o, 1), "h": round(h, 1), "l": round(l, 1), "c": round(c, 1), "v": 10}
                         for t, o, h, l, c in zip(utc, df_server["open"], df_server["high"], df_server["low"], df_server["close"])]
        # «ahora» a media sesión (a las 23:59 del servidor el motor no entra: franja de rollover)
        self.visible = int(df_server.index.searchsorted(pd.Timestamp("2026-09-24 14:00"))) + 1
        self.account = {"id": 7, "name": "50KTC-V2-7", "balance": balance, "canTrade": True, "isVisible": True,
                        "simulated": simulated}
        self.contract = {"id": "CON.F.US.MGC.Z26", "name": "MGCZ6", "tickSize": 0.1, "tickValue": 1.0,
                         "activeContract": True}
        self.positions, self.orders, self.calls = [], [], []
        self.brackets, self.fail_stop, self.next_id = brackets, fail_stop, 100

    @property
    def price(self):
        return self.all_bars[self.visible - 1]["c"]

    def _id(self):
        self.next_id += 1
        return self.next_id

    def __call__(self, method, url, headers, body, timeout):
        path = url.split("api.topstepx.com", 1)[1]
        d = json.loads(body or b"{}")
        self.calls.append((path, d))
        ok = {"success": True, "errorCode": 0, "errorMessage": None}
        if path == "/api/Auth/loginKey":
            return 200, json.dumps({**ok, "token": "jwt"}).encode()
        if path == "/api/Account/search":
            return 200, json.dumps({**ok, "accounts": [self.account]}).encode()
        if path == "/api/Contract/search":
            return 200, json.dumps({**ok, "contracts": [self.contract]}).encode()
        if path == "/api/History/retrieveBars":
            s, e = pd.Timestamp(d["startTime"]), pd.Timestamp(d["endTime"])
            bars = [b for b in self.all_bars[:self.visible] if s <= pd.Timestamp(b["t"]) < e]
            return 200, json.dumps({**ok, "bars": bars[-d["limit"]:]}).encode()
        if path == "/api/Order/place":
            oid = self._id()
            if d["type"] == 2:
                side = 1 if d["side"] == 0 else -1
                avg = self.price
                self.positions.append({"id": oid, "accountId": d["accountId"], "contractId": d["contractId"],
                                       "type": 1 if side > 0 else 2, "size": d["size"], "averagePrice": avg})
                prot = 1 - d["side"]
                if "stopLossBracket" in d and self.brackets != "none":
                    sign = -1 if self.brackets == "wrong" else 1
                    sp = round(avg - sign * side * d["stopLossBracket"]["ticks"] * 0.1, 1)
                    self.orders.append({"id": self._id(), "contractId": d["contractId"], "type": 4, "side": prot,
                                        "size": d["size"], "stopPrice": sp})
                if "takeProfitBracket" in d and self.brackets != "none":
                    lp = round(avg + side * d["takeProfitBracket"]["ticks"] * 0.1, 1)
                    self.orders.append({"id": self._id(), "contractId": d["contractId"], "type": 1, "side": prot,
                                        "size": d["size"], "limitPrice": lp})
            elif d["type"] == 4:
                if self.fail_stop:
                    return 200, json.dumps({"success": False, "errorCode": 2, "errorMessage": "rechazada"}).encode()
                self.orders.append({"id": oid, "contractId": d["contractId"], "type": 4, "side": d["side"],
                                    "size": d["size"], "stopPrice": d["stopPrice"]})
            else:
                self.orders.append({"id": oid, "contractId": d["contractId"], "type": d["type"], "side": d["side"],
                                    "size": d["size"], "limitPrice": d.get("limitPrice")})
            return 200, json.dumps({**ok, "orderId": oid}).encode()
        if path == "/api/Order/cancel":
            self.orders = [o for o in self.orders if o["id"] != d["orderId"]]
            return 200, json.dumps(ok).encode()
        if path == "/api/Order/modify":
            for o in self.orders:
                if o["id"] == d["orderId"] and "stopPrice" in d:
                    o["stopPrice"] = d["stopPrice"]
            return 200, json.dumps(ok).encode()
        if path == "/api/Order/searchOpen":
            return 200, json.dumps({**ok, "orders": self.orders}).encode()
        if path == "/api/Position/searchOpen":
            return 200, json.dumps({**ok, "positions": self.positions}).encode()
        if path == "/api/Position/closeContract":
            self.positions = [p for p in self.positions if p["contractId"] != d["contractId"]]
            return 200, json.dumps(ok).encode()
        return 404, b"{}"

    def placed(self, order_type=None):
        return [d for p, d in self.calls if p == "/api/Order/place" and (order_type is None or d["type"] == order_type)]


@pytest.fixture(scope="module")
def market():
    df = generate_m1("2026-09-21", "2026-09-25", seed=11)
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].round(1)
    return df


def _script(entry_ns, side=1, exit_ns=None):
    def f(ctx):
        if ctx.decision_time == entry_ns and not ctx.positions:
            return [Enter(side, sl_dist=5.0, tp_dist=10.0)]
        if exit_ns is not None and ctx.decision_time == exit_ns and ctx.positions:
            return [Exit()]
        return []
    return f


def _bot(tmp_path, fake, market, execute=True, entry_offset=3, side=1, exit_ns=None, now_offset_min=1.5, **cfg_over):
    cfg = dict(tb.DEFAULTS)
    cfg.update({"account_ids": [7], "execute": execute, "warmup_days": 6, "state_dir": str(tmp_path / "st"),
                "risk_usd_per_trade": 200.0, "commission_per_contract_rt": 1.0})
    cfg.update(cfg_over)
    last_server = market.index[fake.visible - 1]
    entry_dec = to_ns(last_server - pd.Timedelta(minutes=entry_offset))
    client = ProjectXClient(username="u", api_key="k", transport=fake, sleep=lambda s: None)
    last_utc = pd.Timestamp(server_to_utc(pd.DatetimeIndex([last_server]))[0])
    clock = {"now": (last_utc + pd.Timedelta(minutes=now_offset_min)).to_pydatetime().replace(tzinfo=timezone.utc)}
    bot = tb.TopstepBot(cfg, client, now_fn=lambda: clock["now"],
                        strategy_factory=lambda: Scripted(script=_script(entry_dec, side, exit_ns)),
                        log=lambda *_: None, sleep=lambda s: None)
    return bot, clock


def _journal(bot):
    p = bot.dir / "diario.csv"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_config_rejects_credentials_and_unknown_keys(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"api_key": "x"}))
    with pytest.raises(ValueError):
        tb.load_config(p)
    p.write_text(json.dumps({"riesgo": 1}))
    with pytest.raises(ValueError):
        tb.load_config(p)
    p.write_text(json.dumps({"account_ids": [1], "execute": True}))
    assert tb.load_config(p)["execute"] is True


def test_signal_mode_never_places_orders(tmp_path, market):
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market, execute=False)
    bot.startup()
    out = bot.step()
    assert out["target"]["side"] == 1
    assert fake.placed() == []
    j = _journal(bot)
    assert "SIGNAL" in j and "SENALES" in j
    assert bot.state.position_key is not None                  # posición virtual para seguir la salida


def test_execute_refused_unless_allowlisted_and_simulated(tmp_path, market):
    bot, _ = _bot(tmp_path, FakeGateway(market, simulated=False), market)
    with pytest.raises(ValueError, match="simulada"):
        bot.startup()
    bot, _ = _bot(tmp_path / "b", FakeGateway(market), market, account_ids=[])
    with pytest.raises(ValueError, match="account_ids"):
        bot.startup()


def test_execute_enters_with_brackets_sized_by_risk(tmp_path, market):
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    entries = fake.placed(order_type=2)
    assert len(entries) == 1
    e = entries[0]
    assert e["side"] == 0 and e["stopLossBracket"]["ticks"] == 50 and e["takeProfitBracket"]["ticks"] == 100
    assert e["size"] == 3                                          # floor(200 / (50 ticks x 1 USD + 1 USD))
    pos = fake.positions[0]
    stops = [o for o in fake.orders if o["type"] == 4]
    assert len(stops) == 1 and stops[0]["stopPrice"] < pos["averagePrice"]
    assert fake.placed(order_type=4) == []                         # el bracket bastó
    # el siguiente paso no repite la entrada
    bot.last_eval_bar = None
    bot.step()
    assert len(fake.placed(order_type=2)) == 1


def test_missing_bracket_gets_own_stop(tmp_path, market):
    fake = FakeGateway(market, brackets="none")
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    own = fake.placed(order_type=4)
    assert len(own) == 1 and own[0]["side"] == 1 and own[0]["stopPrice"] < fake.positions[0]["averagePrice"]


def test_wrong_side_bracket_is_replaced(tmp_path, market):
    fake = FakeGateway(market, brackets="wrong")
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    stops = [o for o in fake.orders if o["type"] == 4]
    assert len(stops) == 1 and stops[0]["stopPrice"] < fake.positions[0]["averagePrice"]


def test_flattens_and_locks_when_no_stop_possible(tmp_path, market):
    fake = FakeGateway(market, brackets="none", fail_stop=True)
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    assert fake.positions == []
    assert bot.state.hard_lock and "proteger" in bot.state.hard_lock


def test_skips_when_one_contract_exceeds_risk(tmp_path, market):
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market, risk_usd_per_trade=20.0)
    bot.startup()
    bot.step()
    assert fake.placed() == []
    assert "1 contrato arriesgar" in _journal(bot)


def test_old_signal_is_not_chased(tmp_path, market):
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market, now_offset_min=40)
    bot.startup()
    bot.step()
    assert fake.placed() == [] and "no se persigue" in _journal(bot)


def test_daily_loss_closes_position_and_blocks(tmp_path, market):
    fake = FakeGateway(market)
    bot, clock = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    assert fake.positions
    fake.account["balance"] = 50000.0 - 600.0                      # pérdida del día > 500
    bot.step()
    assert fake.positions == [] and bot.state.locked_day == bot.state.day_key
    assert not bot.step()["can_open"]


def test_mll_buffer_is_a_hard_lock(tmp_path, market):
    fake = FakeGateway(market, balance=48300.0)                    # a 300 USD del MLL de 48 000
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    out = bot.step()
    assert not out["can_open"] and bot.state.hard_lock and fake.placed() == []


def test_closes_when_strategy_exits(tmp_path, market):
    fake = FakeGateway(market)
    fake.visible -= 30                                             # el mercado «avanza» después
    last_server = market.index[fake.visible - 1]
    exit_ns = to_ns(last_server + pd.Timedelta(minutes=10))
    bot, clock = _bot(tmp_path, fake, market, exit_ns=exit_ns)
    bot.startup()
    bot.step()
    assert fake.positions
    fake.visible += 30
    clock["now"] = clock["now"] + timedelta(minutes=30)
    bot.step()
    assert fake.positions == [] and "ya no quiere" in _journal(bot)


def test_day_key_rolls_at_17_chicago():
    before = datetime(2026, 9, 29, 21, 59, tzinfo=timezone.utc)    # 16:59 CDT
    after = datetime(2026, 9, 29, 22, 1, tzinfo=timezone.utc)      # 17:01 CDT
    assert tb.topstep_day_key(before) == "2026-09-29" and tb.topstep_day_key(after) == "2026-09-30"


def test_bars_to_frame_uses_server_time():
    f = tb.bars_to_frame([{"t": "2026-01-05T15:00:00+00:00", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 3}])
    assert f.index[0] == pd.Timestamp("2026-01-05 17:00")          # invierno: servidor = UTC + 2
    assert f["spread"].iloc[0] == 1.0


def test_client_retries_relogins_and_raises():
    calls = []

    def transport(method, url, headers, body, timeout):
        calls.append(url)
        if url.endswith("loginKey"):
            return 200, b'{"success": true, "errorCode": 0, "token": "t"}'
        if len([c for c in calls if c.endswith("Account/search")]) == 1:
            return 503, b""
        if len([c for c in calls if c.endswith("Account/search")]) == 2:
            return 401, b""
        return 200, b'{"success": true, "errorCode": 0, "accounts": [{"id": 1}]}'

    c = ProjectXClient(username="u", api_key="SECRETKEY123", transport=transport, sleep=lambda s: None)
    assert c.accounts() == [{"id": 1}]
    assert sum(u.endswith("loginKey") for u in calls) == 2          # nuevo login tras el 401
    bad = ProjectXClient(username="u", api_key="k", sleep=lambda s: None,
                         transport=lambda *a: (200, b'{"success": false, "errorCode": 3, "errorMessage": "no"}'))
    with pytest.raises(ProjectXError):
        bad.login()
    code3 = ProjectXClient(username="u", api_key="k", sleep=lambda s: None,
                           transport=lambda *a: (200, b'{"success": false, "errorCode": 3, "errorMessage": null}'))
    with pytest.raises(ProjectXError, match="usuario de TopstepX"):
        code3.login()
    assert "SECRETKEY123" not in repr(c)


def test_instance_lock(tmp_path):
    lock = tb.InstanceLock(tmp_path / "bot.lock")
    lock.acquire()
    with pytest.raises(SystemExit):
        tb.InstanceLock(tmp_path / "bot.lock").acquire()
    lock.release()


def test_credentials_are_prompted_and_placeholders_ignored():
    asked = []
    user, key = tb.ask_credentials(env={"TOPSTEPX_USERNAME": "tu_usuario_de_TopstepX", "TOPSTEPX_API_KEY": "la_clave_nueva"},
                                   input_fn=lambda p: asked.append(p) or " cjdemo ",
                                   getpass_fn=lambda p: asked.append(p) or '"ABC123="')
    assert (user, key) == ("cjdemo", "ABC123=") and len(asked) == 2
    user, key = tb.ask_credentials(env={"TOPSTEPX_USERNAME": "u1", "TOPSTEPX_API_KEY": "K1"},
                                   input_fn=lambda p: 1 / 0, getpass_fn=lambda p: 1 / 0)
    assert (user, key) == ("u1", "K1")
    with pytest.raises(SystemExit):
        tb.ask_credentials(env={}, input_fn=lambda p: "", getpass_fn=lambda p: "")


def test_key_can_come_from_a_local_file(tmp_path):
    f = tmp_path / "clave_topstepx.txt"
    f.write_text("﻿ABCDEF123=  \n", encoding="utf-8")
    user, key = tb.ask_credentials(env={}, input_fn=lambda p: "trader.x", getpass_fn=lambda p: 1 / 0, key_file=f)
    assert (user, key) == ("trader.x", "ABCDEF123=")


def test_test_login_mode(tmp_path, market, monkeypatch, capsys):
    fake = FakeGateway(market)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"state_dir": str(tmp_path / "st")}))
    monkeypatch.setenv("TOPSTEPX_USERNAME", "trader.x")
    monkeypatch.setenv("TOPSTEPX_API_KEY", "ABC123")
    real = tb.ProjectXClient
    monkeypatch.setattr(tb, "ProjectXClient", lambda **kw: real(transport=fake, sleep=lambda s: None, **kw))
    assert tb.main(["--config", str(cfg), "--test-login"]) == 0
    out = capsys.readouterr().out
    assert "Inicio de sesión correcto" in out and "id 7" in out and "ABC123" not in out
