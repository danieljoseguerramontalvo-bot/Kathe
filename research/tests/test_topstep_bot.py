"""Bot de TopstepX contra un servidor ProjectX simulado (sin red ni cuentas reales)."""
import json
import os
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
        self.reject_brackets = False
        utc = pd.DatetimeIndex(server_to_utc(df_server.index))
        self.all_bars = [{"t": _iso(t), "o": round(o, 1), "h": round(h, 1), "l": round(l, 1), "c": round(c, 1), "v": 10}
                         for t, o, h, l, c in zip(utc, df_server["open"], df_server["high"], df_server["low"], df_server["close"])]
        # «ahora» a media sesión (a las 23:59 del servidor el motor no entra: franja de rollover)
        self.visible = int(df_server.index.searchsorted(pd.Timestamp("2026-09-24 14:00"))) + 1
        self.account = {"id": 7, "name": "50KTC-V2-7", "balance": balance, "canTrade": True, "isVisible": True,
                        "simulated": simulated}
        self.contract = {"id": "CON.F.US.MGC.Z26", "name": "MGCZ6", "tickSize": 0.1, "tickValue": 1.0,
                         "activeContract": True}
        self.positions, self.orders, self.calls, self.trades = [], [], [], []
        self.fail_trades = False
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
            if getattr(self, "fail_after_place", False) and d["type"] == 2:
                self.fail_after_place = False                       # ejecuta la orden pero la respuesta se pierde
                self.__call__(method, url, headers, body, timeout)
                self.calls.pop()
                return 502, b"Bad Gateway"
            if self.reject_brackets and "stopLossBracket" in d:
                return 200, json.dumps({"success": False, "errorCode": 2, "errorMessage": "brackets"}).encode()
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
        if path == "/api/Trade/search":
            if self.fail_trades:
                return 500, b"{}"
            return 200, json.dumps({**ok, "trades": self.trades}).encode()
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
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"account_ids": [2]}).encode("utf-8"))   # guardado con BOM
    assert tb.load_config(p)["account_ids"] == [2]


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


def test_rejected_brackets_retry_without_them_and_protect(tmp_path, market):
    fake = FakeGateway(market)
    fake.reject_brackets = True
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    assert fake.positions, "la entrada se reintenta sin brackets"
    stops = [o for o in fake.orders if o["type"] == 4]
    tps = [o for o in fake.orders if o["type"] == 1]
    assert len(stops) == 1 and stops[0]["stopPrice"] < fake.positions[0]["averagePrice"]
    assert len(tps) == 1 and tps[0]["limitPrice"] > fake.positions[0]["averagePrice"]


def test_console_shows_heartbeat_and_journal_events(tmp_path, market):
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market)
    lines = []
    bot.log_fn = lines.append
    bot.startup()
    bot.step()
    text = "\n".join(lines)
    assert "Funcionando. Saldo" in text and "posición del bot: ninguna" in text
    assert "FILL side=1 contracts=3" in text                       # los eventos del diario también salen en pantalla
    n = len(lines)
    bot.last_eval_bar = None
    bot.step()                                                     # misma hora: sin nueva línea de latido
    assert not any("Funcionando" in l for l in lines[n:])


def test_panel_shows_account_position_orders_and_local_times(tmp_path, market):
    fake = FakeGateway(market)
    fake.trades = [
        {"id": 1, "contractId": "CON.F.US.MGC.Z26", "creationTimestamp": "2026-09-23T00:01:05Z", "price": 1690.0,
         "profitAndLoss": None, "fees": 0.74, "side": 0, "size": 1, "voided": False},
        {"id": 2, "contractId": "CON.F.US.MGC.Z26", "creationTimestamp": "2026-09-23T08:00:40Z", "price": 1695.0,
         "profitAndLoss": 50.0, "fees": 0.74, "side": 1, "size": 1, "voided": False},
    ]
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    path = bot.write_panel()
    text = path.read_text(encoding="utf-8")
    assert "EJECUCIÓN" in text and "Compra 3" in text
    assert "Órdenes en el servidor de Topstep" in text and "Stop" in text
    assert "hora Aruba" in text and "Entrada ejecutada" in text
    assert "22/09 8:01:05 p. m." in text                           # 00:01 UTC = 8:01 p. m. del día anterior en Aruba
    assert "Objetivo del Combine" in text
    assert "+50.00" in text and "Operaciones cerradas</dt><dd>1 " in text
    assert (bot.dir / "saldo.csv").exists()


def test_panel_never_breaks_the_bot(tmp_path, market):
    fake = FakeGateway(market)
    fake.fail_trades = True
    bot, _ = _bot(tmp_path, fake, market, execute=False)
    bot.startup()
    bot.journal("ERROR", detail="<script>alert(1)</script>")
    bot.step()
    path = bot.write_panel()
    text = path.read_text(encoding="utf-8")
    assert "SOLO SEÑALES" in text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text


def test_session_schedule_in_aruba_time():
    from kq.live import panel
    cfg = {"strategy": "SESSION_DRIFT", "params": {"h_in": 0, "h_out": 8}, "display_tz": "America/Aruba"}
    now = pd.Timestamp("2026-09-30 03:29", tz="UTC")                   # miércoles, dentro de la ventana de hoy
    cur = panel.session_schedule(cfg, now)
    nxt = panel.session_schedule(cfg, now, upcoming_only=True)
    assert cur["active"] and cur["start"] == pd.Timestamp("2026-09-30 00:00", tz="UTC")
    assert not nxt["active"] and nxt["start"] == pd.Timestamp("2026-10-01 00:00", tz="UTC")
    assert panel.schedule_text(nxt, cfg["display_tz"]) == \
        "entra a las 8:00 p. m. y sale a las 4:00 a. m. (hora Aruba), de domingo a jueves"
    fri = panel.session_schedule(cfg, pd.Timestamp("2026-10-02 09:00", tz="UTC"))
    assert fri["start"] == pd.Timestamp("2026-10-05 00:00", tz="UTC")   # sin entradas en fin de semana UTC
    assert panel.session_schedule({"strategy": "REF_T0", "params": {}}, now) is None


def test_trade_stats_and_balance_log(tmp_path):
    from kq.live import panel
    st = panel.trade_stats([{"profitAndLoss": None, "fees": 1.0}, {"profitAndLoss": 80.0, "fees": 1.0},
                            {"profitAndLoss": -40.0, "fees": 1.0}, {"profitAndLoss": -500.0, "voided": True}])
    assert st["n"] == 2 and st["wins"] == 1 and st["losses"] == 1 and st["net"] == 37.0 and st["win_rate"] == 50.0
    p = tmp_path / "saldo.csv"
    t0 = pd.Timestamp("2026-09-30 00:00", tz="UTC")
    assert panel.append_balance(p, t0, 50000.0)
    assert not panel.append_balance(p, t0 + pd.Timedelta(minutes=5), 50000.0)     # sin cambios: no repite
    assert panel.append_balance(p, t0 + pd.Timedelta(minutes=6), 50012.5)
    assert panel.append_balance(p, t0 + pd.Timedelta(minutes=40), 50012.5)
    assert [b for _, b in panel.read_balance(p)] == [50000.0, 50012.5, 50012.5]


class FakeTelegram:
    """api.telegram.org mínimo: getMe, getUpdates y sendMessage."""

    def __init__(self, chat_id=555, has_update=True):
        self.sent, self.chat_id, self.has_update = [], chat_id, has_update

    def __call__(self, method, url, headers, body, timeout):
        d = json.loads(body or b"{}")
        m = url.rsplit("/", 1)[1]
        if "/botBAD/" in url:
            return 401, json.dumps({"ok": False, "description": "Unauthorized"}).encode()
        if m == "getMe":
            return 200, json.dumps({"ok": True, "result": {"username": "kathe_test_bot"}}).encode()
        if m == "getUpdates":
            res = [{"update_id": 1, "message": {"chat": {"id": self.chat_id}, "text": "/start"}}] if self.has_update else []
            return 200, json.dumps({"ok": True, "result": res}).encode()
        if m == "deleteWebhook":
            return 200, json.dumps({"ok": True, "result": True}).encode()
        if m == "sendMessage":
            self.sent.append(d["text"])
            return 200, json.dumps({"ok": True, "result": {}}).encode()
        return 404, b"{}"


def test_telegram_setup_saves_chat_and_sends_test(tmp_path):
    from kq.live import notify
    tg = FakeTelegram()
    path = tmp_path / "telegram.txt"
    assert notify.setup(getpass_fn=lambda *_: "TOKEN123", transport=tg, path=path) == 0
    assert path.read_text(encoding="utf-8").split() == ["TOKEN123", "555"]
    assert tg.sent and "conectado" in tg.sent[0]
    n = notify.load_notifier(path, env={}, transport=tg, background=False)
    assert n is not None and "TOKEN" not in repr(n)
    assert notify.setup(getpass_fn=lambda *_: "BAD", transport=tg, path=tmp_path / "x.txt") == 1
    ticks = iter(range(0, 1000, 60))                                   # nadie escribe al bot: se rinde a los 3 min
    quiet = FakeTelegram(has_update=False)
    assert notify.setup(getpass_fn=lambda *_: "T2", transport=quiet, path=tmp_path / "y.txt",
                        clock=lambda: next(ticks)) == 1
    assert not (tmp_path / "y.txt").exists()
    assert notify.load_notifier(tmp_path / "no.txt", env={}) is None


def test_telegram_messages_for_entry_exit_and_day_summary(tmp_path, market):
    from kq.live import notify
    tg = FakeTelegram()
    fake = FakeGateway(market)
    bot, clock = _bot(tmp_path, fake, market)
    bot.notifier = notify.TelegramNotifier("T", 555, transport=tg, background=False)
    bot.startup()
    assert tg.sent[0].startswith("[MGC] 🤖 KatheBot arrancado en EJECUCIÓN")
    bot.step()
    entry = [m for m in tg.sent if m.startswith("[MGC] 🟢 ENTRADA COMPRA 3")]
    assert entry and ("p. m." in entry[0] or "a. m." in entry[0])
    # el stop salta en el servidor: el bot lo detecta y, cuando el saldo ya lo refleja, avisa del resultado
    fake.positions.clear()
    fake.orders.clear()
    fake.account["balance"] = 49848.0
    fake.visible += 1
    clock["now"] += timedelta(minutes=1)
    bot.step()
    assert not any(m.startswith("[MGC] 🔴 SALIDA") for m in tg.sent)          # todavía no: espera a que el saldo cuadre
    clock["now"] += timedelta(minutes=1)
    fake.visible += 1
    bot.step()
    out = [m for m in tg.sent if m.startswith("[MGC] 🔴 SALIDA")]
    assert out and "-152.00 USD" in out[0] and "faltan 3,152" in out[0]
    # cambio de día de Topstep (17:00 de Chicago): resumen del día anterior
    clock["now"] += timedelta(hours=24)
    bot.step()
    assert any(m.startswith("[CUENTA] 📊 Resumen del día") for m in tg.sent)


def test_telegram_failure_never_breaks_the_bot(tmp_path, market):
    from kq.live import notify

    def down(*a, **k):
        raise OSError("sin red")

    logs = []
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market)
    bot.notifier = notify.TelegramNotifier("T", 1, transport=down, background=False, log=logs.append)
    bot.startup()
    bot.step()
    assert len(fake.placed(order_type=2)) == 1
    assert any("Telegram" in l for l in logs)


def test_signals_mode_reports_theoretical_result(tmp_path, market):
    fake = FakeGateway(market)
    fake.visible -= 30
    exit_ns = to_ns(market.index[fake.visible - 1] + pd.Timedelta(minutes=10))
    bot, clock = _bot(tmp_path, fake, market, execute=False, exit_ns=exit_ns)
    bot.startup()
    bot.step()
    assert bot.state.position_key and fake.placed() == []
    fake.visible += 30
    clock["now"] = clock["now"] + timedelta(minutes=30)
    bot.step()
    j = _journal(bot)
    assert "resultado teórico" in j and "acumulado" in j and "en 1 señales" in j
    assert bot.state.extra["virtual_n"] == 1 and fake.placed() == []


def test_several_markets_share_one_session_and_only_one_executes(tmp_path, market):
    from kq.live import notify
    tg = FakeTelegram()
    fake = FakeGateway(market)
    gold, _ = _bot(tmp_path / "a", fake, market)
    other, _ = _bot(tmp_path / "b", fake, market, execute=False)
    other.client = gold.client                                     # una sola sesión de la API
    n = notify.TelegramNotifier("T", 1, transport=tg, background=False)
    gold.notifier = other.notifier = n
    gold.startup()
    other.startup()
    tb.run_many([gold, other], sleep=lambda s: None, rounds=1, overview=tmp_path / "general.html")
    general = (tmp_path / "general.html").read_text(encoding="utf-8")
    assert "panel general" in general and general.count("Ver el panel completo") == 2
    assert len(fake.placed(order_type=2)) == 1                     # solo ordena el que ejecuta
    assert (gold.dir / "panel.html").exists() and (other.dir / "panel.html").exists()
    assert all(m.startswith("[MGC] ") for m in tg.sent)
    logins = [c for c in fake.calls if c[0] == "/api/Auth/loginKey"]
    assert len(logins) <= 2
    base = dict(tb.DEFAULTS)
    a = {**base, "execute": True, "account_ids": [7], "state_dir": str(tmp_path / "x")}
    b = {**base, "execute": True, "account_ids": [7], "state_dir": str(tmp_path / "y"), "symbol_search": "MNQ"}
    with pytest.raises(ValueError, match="solo una puede ejecutar"):
        tb.check_configs([a, b])
    with pytest.raises(ValueError, match="state_dir"):
        tb.check_configs([a, {**b, "execute": False, "state_dir": str(tmp_path / "x")}])
    tb.check_configs([a, {**b, "execute": False}])


def test_two_non_overlapping_shifts_can_execute_on_one_account(tmp_path, market):
    base = dict(tb.DEFAULTS)
    day = {**base, "strategy": "SESSION_DRIFT", "execute": True, "account_ids": [7], "label": "ORO DÍA",
           "params": {"h_in": 10, "h_out": 17, "side": -1}, "state_dir": str(tmp_path / "d")}
    night = {**day, "label": "ORO NOCHE", "params": {"h_in": 0, "h_out": 8, "side": 1}, "state_dir": str(tmp_path / "n")}
    tb.check_configs([day, night])                                  # 10-17 y 0-8 UTC no coinciden
    late = {**night, "params": {"h_in": 16, "h_out": 20, "side": 1}}
    with pytest.raises(ValueError, match="se solapan"):
        tb.check_configs([day, late])
    back_to_back = {**night, "params": {"h_in": 17, "h_out": 20, "side": 1}}
    with pytest.raises(ValueError, match="se solapan"):               # la hora de salida cuenta
        tb.check_configs([day, back_to_back])
    # un turno no toca la posición del otro y solo lo avisa una vez
    fake = FakeGateway(market)
    a, _ = _bot(tmp_path / "a", fake, market, label="ORO DÍA")
    b, _ = _bot(tmp_path / "b", fake, market, label="ORO NOCHE")
    b.client = a.client
    lines = []
    b.log_fn = lines.append
    a.startup()
    b.startup()
    a.step()
    assert len(fake.positions) == 1
    for _ in range(3):
        b.last_eval_bar = None
        b.step()
    assert len(fake.placed(order_type=2)) == 1 and len(fake.positions) == 1
    assert sum("no abrió este turno" in l for l in lines) == 1
    assert all("[ORO NOCHE]" in l for l in lines)


def test_stale_lock_is_taken_over_but_a_live_one_is_not(tmp_path):
    lock = tmp_path / "bot.lock"
    lock.write_text("999999999")                                    # proceso que ya no existe (apagón)
    tb.InstanceLock(lock).acquire()
    assert lock.read_text() == str(os.getpid())
    with pytest.raises(SystemExit, match="Ya hay otro bot"):
        tb.InstanceLock(lock).acquire()                              # este proceso sigue vivo
    tb.InstanceLock(lock).release()


def test_heartbeat_pings_at_most_once_a_minute():
    from kq.live.notify import Heartbeat
    calls, now = [], {"t": 0.0}
    hb = Heartbeat("https://hc-ping.example/abc", transport=lambda *a: calls.append(a) or (200, b"OK"),
                   clock=lambda: now["t"], background=False)
    assert hb.beat() and not hb.beat()
    now["t"] = 61.0
    assert hb.beat()
    assert len(calls) == 2 and calls[0][0] == "GET" and calls[0][1] == "https://hc-ping.example/abc"


def test_credentials_from_files_and_no_questions_in_auto_mode(tmp_path):
    (tmp_path / "u.txt").write_text("yo@example.com\n", encoding="utf-8")
    (tmp_path / "k.txt").write_text("\ufeffCLAVE44\n", encoding="utf-8")
    ask = lambda *_: pytest.fail("no debe preguntar")
    assert tb.ask_credentials(env={}, input_fn=ask, getpass_fn=ask, key_file=tmp_path / "k.txt",
                              user_file=tmp_path / "u.txt", interactive=False) == ("yo@example.com", "CLAVE44")
    with pytest.raises(SystemExit, match="autoinicio"):
        tb.ask_credentials(env={}, input_fn=ask, getpass_fn=ask, key_file=tmp_path / "k.txt",
                           user_file=tmp_path / "nada.txt", interactive=False)


def test_auto_mode_restarts_after_an_error(tmp_path, monkeypatch):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"state_dir": str(tmp_path / "st")}))
    calls, sleeps = [], []

    def fake_run_bots(cfgs, client, notifier, once=False, open_panels=True):
        calls.append(open_panels)
        if len(calls) == 1:
            raise ProjectXError("sin internet al arrancar")
        return 0

    monkeypatch.setattr(tb, "run_bots", fake_run_bots)
    monkeypatch.setattr(tb, "ask_credentials", lambda interactive=True: ("u", "k"))
    monkeypatch.setattr(tb.time, "sleep", lambda s: sleeps.append(s))
    import kq.live.notify as nt
    monkeypatch.setattr(nt, "load_notifier", lambda *a, **k: None)
    assert tb.main(["--config", str(cfg), "--auto"]) == 0
    assert calls == [True, False] and sleeps == [60]            # reintenta una vez; el panel solo se abre al principio
    with pytest.raises(ProjectXError):                            # sin --auto, el error se propaga
        calls.clear()
        tb.main(["--config", str(cfg)])


def test_autoinicio_installs_launcher_credentials_and_startup_entry(tmp_path):
    from kq.live import autoinicio
    work, startup = tmp_path / "research", tmp_path / "Startup"
    work.mkdir()
    (work / "topstep.json").write_text("{}")
    (work / "topstep_mnq.json").write_text("{}")
    ran = []
    rc = autoinicio.install(work, input_fn=lambda *_: "yo@example.com", getpass_fn=lambda *_: "CLAVE",
                            run=lambda cmd, **k: ran.append(cmd), startup=startup, python=r"C:\Python312\python.exe")
    assert rc == 0
    assert (work / "usuario_topstepx.txt").read_text().strip() == "yo@example.com"
    assert (work / "clave_topstepx.txt").read_text().strip() == "CLAVE"
    cmd = (work / "iniciar_bot.cmd").read_text(encoding="ascii")
    assert '--config "topstep.json" --config "topstep_mnq.json" --auto' in cmd and "topstep_oro_noche" not in cmd
    assert f'cd /d "{work.resolve()}"' in cmd
    assert "iniciar_bot.cmd" in (startup / "KatheBot.cmd").read_text(encoding="ascii")
    assert ["powercfg", "/change", "standby-timeout-ac", "0"] in ran
    autoinicio.remove(startup)
    assert not (startup / "KatheBot.cmd").exists()



def test_skipped_signal_still_reports_entry_stop_and_reason(tmp_path, market):
    from kq.live import notify
    tg = FakeTelegram()
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market, risk_usd_per_trade=20.0)
    bot.notifier = notify.TelegramNotifier("T", 1, transport=tg, background=False)
    bot.startup()
    bot.step()
    assert fake.placed() == []
    msg = [m for m in tg.sent if "NO SE OPERA" in m]
    assert msg and "Entrada ~" in msg[0] and "Stop " in msg[0] and "riesgo 5" in msg[0]
    assert "Motivo: 1 contrato arriesgaría" in msg[0]
    text = bot.write_panel().read_text(encoding="utf-8")
    assert "Última señal" in text and "Compra descartada" in text and "stop " in text


def test_entry_message_has_levels(tmp_path, market):
    from kq.live import notify
    tg = FakeTelegram()
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market)
    bot.notifier = notify.TelegramNotifier("T", 1, transport=tg, background=False)
    bot.startup()
    bot.step()
    entry = [m for m in tg.sent if "ENTRADA COMPRA 3" in m][0]
    assert "Entrada ~" in entry and "Stop " in entry and "riesgo 150 USD" in entry and "Objetivo " in entry
    text = bot.write_panel().read_text(encoding="utf-8")
    assert "Compra ejecutada" in text



def test_signals_mode_sends_the_signal_even_above_the_risk_cap(tmp_path, market):
    from kq.live import notify
    tg = FakeTelegram()
    fake = FakeGateway(market)
    bot, _ = _bot(tmp_path, fake, market, execute=False, risk_usd_per_trade=20.0)
    bot.notifier = notify.TelegramNotifier("T", 1, transport=tg, background=False)
    bot.startup()
    bot.step()
    sig = [m for m in tg.sent if "SEÑAL COMPRA 1" in m]
    assert sig and "Entrada ~" in sig[0] and "Stop " in sig[0]
    assert "solo informativo" in _journal(bot) and bot.state.position_key and fake.placed() == []



def test_uncertain_order_response_is_never_resent(tmp_path, market):
    fake = FakeGateway(market)
    fake.fail_after_place = True                                       # el servidor abrió la posición pero respondió 502
    bot, _ = _bot(tmp_path, fake, market)
    bot.startup()
    bot.step()
    assert len(fake.placed(order_type=2)) == 1                          # una sola orden de entrada, sin reintentos
    assert len(fake.positions) == 1 and fake.positions[0]["size"] == 3
    j = _journal(bot)
    assert "respuesta incierta" in j and "FILL" in j
    assert [o for o in fake.orders if o["type"] == 4]                   # y la posición queda con stop



def test_order_block_strategy_runs_in_the_bot_in_signals_mode(tmp_path, market):
    from kq.live import notify
    tg = FakeTelegram()
    fake = FakeGateway(market)
    cfg = dict(tb.DEFAULTS)
    cfg.update({"account_ids": [], "execute": False, "strategy": "ORDER_BLOCK", "params": {}, "warmup_days": 6,
                "state_dir": str(tmp_path / "ob"), "label": "ORDER BLOCKS"})
    client = ProjectXClient(username="u", api_key="k", transport=fake, sleep=lambda s: None)
    bot = tb.TopstepBot(cfg, client, now_fn=lambda: datetime(2026, 9, 24, 11, 5, tzinfo=timezone.utc),
                        log=lambda *_: None, sleep=lambda s: None,
                        notifier=notify.TelegramNotifier("T", 1, transport=tg, background=False))
    bot.startup()
    bot.step()
    assert fake.placed() == []
    assert tg.sent and tg.sent[0].startswith("[ORDER BLOCKS] 🤖") and "Historial de 6 días" in tg.sent[0]
