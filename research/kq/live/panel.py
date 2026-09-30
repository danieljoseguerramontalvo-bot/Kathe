"""Panel local del bot de Topstep.

El bot reescribe ``<state_dir>/panel.html`` en cada ciclo: un HTML autónomo (sin internet, sin servidor y
sin librerías externas) que se abre con doble clic y se recarga solo. Muestra el estado de la cuenta y de
los límites, la posición con sus órdenes de protección, el horario de la estrategia, la curva de saldo, las
operaciones cerradas (según la API) y los últimos eventos del diario. Todas las horas, en la zona horaria
``display_tz`` (por defecto, Aruba: UTC-4, la misma que Venezuela).
"""
from __future__ import annotations

import csv
import html
import os
from pathlib import Path

import pandas as pd

REFRESH_SECONDS = 20
STALE_SECONDS = 120

DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
EVENT_LABELS = {
    "SIGNAL": ("Señal", "info"),
    "FILL": ("Entrada ejecutada", "good"),
    "EXIT": ("Salida", "info"),
    "SKIP": ("Descartada", "muted"),
    "ERROR": ("Error", "bad"),
    "MODIFY": ("Stop movido", "info"),
    "CANCEL": ("Órdenes canceladas", "muted"),
    "STOP_PROPIO": ("Stop propio puesto", "warn"),
}
ORDER_TYPES = {1: "Límite (objetivo)", 2: "Mercado", 4: "Stop", 5: "Trailing stop"}


# ---------------------------------------------------------------------- horas
def tz_label(tz: str | None) -> str:
    return "UTC" if not tz or tz.upper() == "UTC" else tz.split("/")[-1].replace("_", " ")


def to_local(ts, tz: str | None) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(tz or "UTC")


def fmt_local(ts, tz: str | None, fmt: str = "%d/%m %H:%M") -> str:
    try:
        return to_local(ts, tz).strftime(fmt)
    except (ValueError, TypeError):
        return str(ts)


def fmt_day(ts, tz: str | None) -> str:
    """«miércoles 30/09 20:00» (sin depender del idioma de Windows)."""
    t = to_local(ts, tz)
    return f"{DAY_NAMES[t.weekday()]} {t:%d/%m %H:%M}"


def session_schedule(cfg: dict, now_utc, upcoming_only: bool = False) -> dict | None:
    """Ventana actual o siguiente de SESSION_DRIFT (entrada h_in UTC, salida h_out UTC, lunes a viernes UTC,
    sin cruzar el fin de semana); con ``upcoming_only``, solo ventanas que aún no han empezado.
    None para otras estrategias."""
    if cfg.get("strategy") != "SESSION_DRIFT":
        return None
    p = cfg.get("params") or {}
    h_in, h_out = int(p.get("h_in", 0)), int(p.get("h_out", 8))
    dur = (h_out - h_in) % 24
    allowed = set(p["weekdays"]) if p.get("weekdays") is not None else None
    now = to_local(now_utc, "UTC")
    day0 = now.normalize()
    tz = cfg.get("display_tz")
    for k in range(-1, 9):
        start = day0 + pd.Timedelta(days=k, hours=h_in)
        end = start + pd.Timedelta(hours=dur)
        if start.weekday() >= 5 or end.weekday() >= 5 or (allowed is not None and start.weekday() not in allowed):
            continue
        if end > now and not (upcoming_only and start <= now):
            local_days = set()                     # días locales de entrada, a partir de los días UTC permitidos
            for d in range(7):
                s = day0 + pd.Timedelta(days=d, hours=h_in)
                if s.weekday() < 5 and (s + pd.Timedelta(hours=dur)).weekday() < 5 and (allowed is None or s.weekday() in allowed):
                    local_days.add(to_local(s, tz).weekday())
            return {"start": start, "end": end, "active": start <= now,
                    "entry_local": to_local(start, tz).strftime("%H:%M"), "exit_local": to_local(end, tz).strftime("%H:%M"),
                    "days_local": sorted(local_days)}
    return None


def schedule_text(sch: dict | None, tz: str | None) -> str:
    if not sch:
        return "según la estrategia"
    rot = _rotate(sch["days_local"])
    contiguous = len(rot) > 2 and all((b - a) % 7 == 1 for a, b in zip(rot, rot[1:]))
    dias = f"de {DAY_NAMES[rot[0]]} a {DAY_NAMES[rot[-1]]}" if contiguous else ", ".join(DAY_NAMES[i] for i in rot)
    return f"entra a las {sch['entry_local']} y sale a las {sch['exit_local']} (hora {tz_label(tz)}), {dias}"


def _rotate(idx: list[int]) -> list[int]:
    """Ordena días de la semana empezando tras el mayor hueco (p. ej. dom, lun, ..., jue)."""
    s = sorted(set(idx))
    if len(s) < 2:
        return s
    gaps = [((s[(i + 1) % len(s)] - s[i]) % 7, i) for i in range(len(s))]
    _, i = max(gaps)
    return s[i + 1:] + s[:i + 1]


# ---------------------------------------------------------------------- archivos
def read_journal(path: Path, last: int = 60) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    return rows[-last:][::-1]


def append_balance(path: Path, time_utc, balance: float, min_minutes: int = 30) -> bool:
    """Añade un punto a la curva de saldo si cambió o si pasó ``min_minutes`` desde el último."""
    last = None
    if path.exists():
        with open(path, "rb") as f:
            try:
                f.seek(-200, os.SEEK_END)
            except OSError:
                f.seek(0)
            tail = f.read().decode("utf-8", "replace").strip().splitlines()
        if tail and not tail[-1].startswith("time_utc"):
            t, b = tail[-1].split(";")[:2]
            last = (pd.Timestamp(t), float(b))
    now = pd.Timestamp(time_utc).tz_localize(None) if pd.Timestamp(time_utc).tzinfo else pd.Timestamp(time_utc)
    if last is not None and abs(last[1] - balance) < 0.005 and now - last[0] < pd.Timedelta(minutes=min_minutes):
        return False
    new = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        if new:
            f.write("time_utc;balance\n")
        f.write(f"{now:%Y-%m-%d %H:%M:%S};{balance:.2f}\n")
    return True


def read_balance(path: Path, max_points: int = 2000) -> list[tuple[pd.Timestamp, float]]:
    if not path.exists():
        return []
    df = pd.read_csv(path, sep=";")
    if df.empty:
        return []
    if len(df) > max_points:
        df = df.iloc[:: int(len(df) / max_points) + 1]
    return [(pd.Timestamp(t), float(b)) for t, b in zip(df["time_utc"], df["balance"])]


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------- operaciones
def trade_stats(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("profitAndLoss") is not None and not t.get("voided")]
    pnl = [float(t["profitAndLoss"]) for t in closed]
    fees = sum(float(t.get("fees") or 0) for t in trades if not t.get("voided"))
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    return {"n": len(closed), "wins": len(wins), "losses": len(losses), "gross": sum(pnl), "fees": fees,
            "net": sum(pnl) - fees, "best": max(pnl) if pnl else 0.0, "worst": min(pnl) if pnl else 0.0,
            "win_rate": (len(wins) / len(closed) * 100.0) if closed else None,
            "avg_win": (sum(wins) / len(wins)) if wins else None, "avg_loss": (sum(losses) / len(losses)) if losses else None}


# ---------------------------------------------------------------------- HTML
def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _usd(x, sign: bool = False) -> str:
    if x is None:
        return "–"
    s = f"{abs(float(x)):,.2f}".replace(",", " ")
    if float(x) < 0:
        return f"−{s}"
    return f"+{s}" if sign and float(x) > 0 else s


def _n0(x) -> str:
    return f"{float(x):,.0f}".replace(",", " ")


def _cls(x) -> str:
    return "" if x is None or abs(float(x)) < 0.005 else ("pos" if float(x) > 0 else "neg")


def _side(side) -> str:
    try:
        s = int(float(side))
    except (TypeError, ValueError):
        return _e(side)
    return "Compra" if s > 0 else ("Venta" if s < 0 else "–")


def balance_svg(points: list[tuple[pd.Timestamp, float]], lines: list[tuple[str, float, str]], tz: str | None) -> str:
    if len(points) < 2:
        return '<p class="muted">La curva aparecerá cuando el bot haya guardado varios saldos.</p>'
    w, h, pl, pr, pt, pb = 1000, 280, 64, 12, 12, 28
    xs = [p[0].value for p in points]
    ys = [p[1] for p in points] + [v for _, v, _ in lines]
    x0, x1 = min(xs), max(xs) if max(xs) > min(xs) else min(xs) + 1
    y0, y1 = min(ys), max(ys)
    pad = max((y1 - y0) * 0.08, 25.0)
    y0, y1 = y0 - pad, y1 + pad

    def X(v):
        return pl + (v - x0) / (x1 - x0) * (w - pl - pr)

    def Y(v):
        return pt + (y1 - v) / (y1 - y0) * (h - pt - pb)

    path = " ".join(f"{X(t.value):.1f},{Y(b):.1f}" for t, b in points)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Curva de saldo">']
    for k in range(5):
        v = y0 + (y1 - y0) * k / 4
        out.append(f'<line x1="{pl}" x2="{w - pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                   f'<text x="{pl - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="axis">{_n0(v)}</text>')
    for label, v, cls in lines:
        out.append(f'<line x1="{pl}" x2="{w - pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="{cls}"/>'
                   f'<text x="{w - pr - 4}" y="{Y(v) - 5:.1f}" text-anchor="end" class="axis {cls}-t">{_e(label)} {_n0(v)}</text>')
    out.append(f'<polyline points="{path}" class="curve"/>')
    for t in (points[0][0], points[-1][0]):
        anchor = "start" if t == points[0][0] else "end"
        out.append(f'<text x="{X(t.value):.1f}" y="{h - 8}" text-anchor="{anchor}" class="axis">{_e(fmt_local(t, tz))}</text>')
    out.append("</svg>")
    return "".join(out)


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#667085;--line:#e4e7ec;--good:#067647;--bad:#b42318;
--warn:#b54708;--info:#175cd3;--accent:#c48a00;--chip:#f2f4f7}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--ink:#e6e8ec;--muted:#98a2b3;--line:#2a2f3a;
--good:#47cd89;--bad:#f97066;--warn:#fdb022;--info:#84adff;--accent:#f5c451;--chip:#222733}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;justify-content:space-between;margin-bottom:12px}
h1{font-size:20px;margin:0}h2{font-size:15px;margin:0 0 10px}
.sub{color:var(--muted);font-size:13px}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;background:var(--chip)}
.badge.exec{background:var(--good);color:#fff}.badge.sig{background:var(--info);color:#fff}
.banner{padding:10px 12px;border-radius:8px;margin-bottom:12px;font-weight:600}
.banner.bad{background:var(--bad);color:#fff}.banner.warn{background:var(--warn);color:#fff}
.grid-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.kpi .l{color:var(--muted);font-size:12px}.kpi .v{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}
.kpi .s{color:var(--muted);font-size:12px}
.pos{color:var(--good)}.neg{color:var(--bad)}.muted{color:var(--muted)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
@media (max-width:760px){.two{grid-template-columns:1fr}}
.section{margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px}
.tbl{overflow-x:auto}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:0}dt{color:var(--muted)}dd{margin:0}
.tag{font-size:12px;font-weight:600}.tag.good{color:var(--good)}.tag.bad{color:var(--bad)}
.tag.warn{color:var(--warn)}.tag.info{color:var(--info)}.tag.muted{color:var(--muted)}
svg{width:100%;height:auto;display:block}
svg .grid{stroke:var(--line);stroke-width:1}svg .axis{fill:var(--muted);font-size:12px}
svg .curve{fill:none;stroke:var(--accent);stroke-width:2}
svg .l-init{stroke:var(--muted);stroke-dasharray:4 4}svg .l-mll{stroke:var(--bad);stroke-dasharray:6 4}
svg .l-buf{stroke:var(--warn);stroke-dasharray:2 4}
svg .l-mll-t{fill:var(--bad)}svg .l-buf-t{fill:var(--warn)}svg .l-init-t{fill:var(--muted)}
footer{color:var(--muted);font-size:12px;margin-top:8px}
"""


def render_panel(d: dict) -> str:
    tz = d.get("tz")
    lab = tz_label(tz)
    gen = pd.Timestamp(d["generated_utc"])
    gen_ms = int(to_local(gen, "UTC").value // 1_000_000)
    r = d.get("risk") or {}
    execute = d.get("mode") == "EJECUCION"
    banners = []
    if r.get("hard_lock"):
        banners.append(("bad", f"Bot bloqueado: {r['hard_lock']}. No abrirá más operaciones hasta que lo revises."))
    elif r.get("locked_today"):
        banners.append(("warn", f"Sin operaciones el resto del día de Topstep: {r.get('why')}"))
    for err in d.get("alerts") or []:
        banners.append(("warn", err))

    acct = d.get("account") or {}
    sch = d.get("schedule")
    pos = d.get("position")
    st = d.get("stats") or trade_stats([])

    def kpi(label, value, sub="", cls=""):
        return (f'<div class="card kpi"><div class="l">{_e(label)}</div><div class="v {cls}">{value}</div>'
                f'<div class="s">{sub}</div></div>')

    if pos:
        pos_v = f'{_side(pos.get("side"))} {pos.get("size", "")}'
        pos_s = f'a {_e(pos.get("avg"))} · stop {_e(pos.get("stop"))}'
        if pos.get("unrealized") is not None:
            pos_s += f' · <span class="{_cls(pos["unrealized"])}">{_usd(pos["unrealized"], True)} USD aprox.</span>'
    else:
        pos_v, pos_s = "Sin posición", ""
    if sch:
        t_main = to_local(sch["end"] if sch["active"] else sch["start"], tz)
        nxt_label = "Cierre previsto" if sch["active"] else "Próxima entrada"
        nxt_v = f"{DAY_NAMES[t_main.weekday()][:3]} {t_main:%H:%M}"
        nxt_s = f"{t_main:%d/%m}" + ("" if sch["active"] else f" · salida {_e(fmt_day(sch['end'], tz))}")
    else:
        nxt_label, nxt_v, nxt_s = "Próxima entrada", "–", "según la estrategia"

    cards = "".join([
        kpi("Saldo", _usd(r.get("balance")), f'inicial {_usd(r.get("initial"))}'),
        kpi("Resultado total", _usd(r.get("pnl_total"), True), "desde el saldo inicial", _cls(r.get("pnl_total"))),
        kpi("Resultado del día", _usd(r.get("pnl_day"), True), f'día Topstep {_e(r.get("day_key"))} · límite −{_usd(r.get("dll"))}',
            _cls(r.get("pnl_day"))),
        kpi("Distancia al MLL", _usd(r.get("room")), f'MLL estimado {_usd(r.get("floor"))} · colchón {_usd(r.get("buffer"))}',
            "neg" if r.get("room") is not None and r.get("buffer") is not None and r["room"] < 2 * r["buffer"] else ""),
        kpi("Posición del bot", _e(pos_v), pos_s),
        kpi(nxt_label, nxt_v, nxt_s),
    ])

    orders_html = ""
    if pos and pos.get("orders"):
        rows = "".join(f'<tr><td>{_e(ORDER_TYPES.get(int(o.get("type", 0)), o.get("type")))}</td>'
                       f'<td>{"Venta" if int(o.get("side", 0)) == 1 else "Compra"}</td><td>{_e(o.get("size"))}</td>'
                       f'<td>{_e(o.get("stopPrice") if o.get("stopPrice") is not None else o.get("limitPrice"))}</td></tr>'
                       for o in pos["orders"])
        orders_html = ('<h2 style="margin-top:12px">Órdenes en el servidor de Topstep</h2><div class="tbl"><table>'
                       f'<tr><th>Tipo</th><th>Lado</th><th>Contratos</th><th>Precio</th></tr>{rows}</table></div>')
    elif pos and execute:
        orders_html = '<p class="neg" style="margin-top:12px">No se ven órdenes de protección en el servidor.</p>'

    params = ", ".join(f"{k}={v}" for k, v in (d.get("params") or {}).items())
    info = (f'<div class="card"><h2>Configuración</h2><dl>'
            f'<dt>Cuenta</dt><dd>{_e(acct.get("id"))} · {_e(acct.get("name"))} · simulada={_e(acct.get("simulated"))}</dd>'
            f'<dt>Contrato</dt><dd>{_e(d.get("contract"))} · tick {_e(d.get("tick_size"))} = {_e(d.get("tick_value"))} USD</dd>'
            f'<dt>Estrategia</dt><dd>{_e(d.get("strategy"))} <span class="muted">({_e(params)})</span></dd>'
            f'<dt>Horario</dt><dd>{_e(schedule_text(sch, tz))}</dd>'
            f'<dt>Tamaño</dt><dd>máximo {_e(r.get("max_contracts"))} contrato(s); riesgo máximo {_usd(r.get("risk_per_trade"))} USD '
            f'por operación (si 1 contrato arriesga más, no entra)</dd>'
            f'<dt>Límites del bot</dt><dd>pérdida diaria {_usd(r.get("dll"))} · colchón sobre el MLL {_usd(r.get("buffer"))}</dd>'
            f'<dt>¿Puede abrir?</dt><dd>{ {True: "Sí", False: "No"}.get(r.get("can_open"), "pendiente del primer ciclo") }'
            f'{" — " + _e(r.get("why")) if r.get("why") else ""}</dd>'
            f'<dt>Última vela</dt><dd>{_e(d.get("last_bar_local"))} · precio {_e(d.get("last_price"))}</dd>'
            f'</dl>{orders_html}</div>')

    wr = f'{st["win_rate"]:.0f} %' if st.get("win_rate") is not None else "–"
    stats = (f'<div class="card"><h2>Resultados (API de Topstep, últimos {d.get("trades_days", 60)} días)</h2><dl>'
             f'<dt>Operaciones cerradas</dt><dd>{st["n"]} · ganadas {st["wins"]} · perdidas {st["losses"]} · acierto {wr}</dd>'
             f'<dt>Resultado bruto</dt><dd class="{_cls(st["gross"])}">{_usd(st["gross"], True)} USD</dd>'
             f'<dt>Comisiones</dt><dd>{_usd(-st["fees"]) if st["fees"] else "0.00"} USD</dd>'
             f'<dt>Resultado neto</dt><dd class="{_cls(st["net"])}">{_usd(st["net"], True)} USD</dd>'
             f'<dt>Media ganadora / perdedora</dt><dd>{_usd(st["avg_win"], True)} / {_usd(st["avg_loss"], True)}</dd>'
             f'<dt>Mejor / peor</dt><dd>{_usd(st["best"], True)} / {_usd(st["worst"], True)}</dd>'
             f'</dl><p class="muted" style="margin:8px 0 0">Incluye cualquier operación de la cuenta, también manuales. '
             f'Pocas operaciones no dicen si la estrategia funciona.</p></div>')

    init = r.get("initial")
    lines = []
    if init is not None:
        lines.append(("inicial", float(init), "l-init"))
    if r.get("floor") is not None:
        lines.append(("MLL", float(r["floor"]), "l-mll"))
        if r.get("buffer"):
            lines.append(("colchón", float(r["floor"]) + float(r["buffer"]), "l-buf"))
    chart = f'<div class="card section"><h2>Saldo</h2>{balance_svg(d.get("balance_hist") or [], lines, tz)}</div>'

    trades = [t for t in (d.get("trades") or []) if not t.get("voided")][-40:][::-1]
    if trades:
        trs = "".join(
            f'<tr><td>{_e(fmt_local(t.get("creationTimestamp"), tz, "%d/%m %H:%M:%S"))}</td>'
            f'<td>{"Compra" if int(t.get("side", 0)) == 0 else "Venta"}</td><td>{_e(t.get("size"))}</td>'
            f'<td>{_e(t.get("price"))}</td>'
            f'<td class="{_cls(t.get("profitAndLoss"))}">{_usd(t.get("profitAndLoss"), True) if t.get("profitAndLoss") is not None else "apertura"}</td>'
            f'<td>{_usd(-(t.get("fees") or 0)) if t.get("fees") else ""}</td><td class="muted">{_e(t.get("contractId"))}</td></tr>'
            for t in trades)
        trades_html = ('<div class="card section"><h2>Ejecuciones en la cuenta</h2><div class="tbl"><table>'
                       '<tr><th>Hora</th><th>Lado</th><th>Contratos</th><th>Precio</th><th>Resultado</th><th>Comisión</th>'
                       f'<th>Contrato</th></tr>{trs}</table></div></div>')
    else:
        trades_html = ('<div class="card section"><h2>Ejecuciones en la cuenta</h2>'
                       '<p class="muted">Todavía no hay ejecuciones en la cuenta.</p></div>')

    jr = []
    for row in d.get("journal") or []:
        label, cls = EVENT_LABELS.get(row.get("event", ""), (row.get("event", ""), "info"))
        jr.append(f'<tr><td>{_e(fmt_local(row.get("time_utc"), tz, "%d/%m %H:%M:%S"))}</td>'
                  f'<td><span class="tag {cls}">{_e(label)}</span></td><td>{_side(row.get("side")) if row.get("side") else ""}</td>'
                  f'<td>{_e(row.get("contracts"))}</td><td>{_e(row.get("price"))}</td><td>{_e(row.get("stop"))}</td>'
                  f'<td>{_e(row.get("tp"))}</td><td>{_e(row.get("detail"))}</td></tr>')
    journal_html = ('<div class="card section"><h2>Diario del bot</h2><div class="tbl"><table>'
                    '<tr><th>Hora</th><th>Evento</th><th>Lado</th><th>Contr.</th><th>Precio</th><th>Stop</th><th>Objetivo</th>'
                    f'<th>Detalle</th></tr>{"".join(jr) or "<tr><td colspan=8 class=muted>Sin eventos todavía.</td></tr>"}'
                    '</table></div></div>')

    mode_badge = ('<span class="badge exec">EJECUCIÓN</span>' if execute else '<span class="badge sig">SOLO SEÑALES</span>')
    banner_html = "".join(f'<div class="banner {c}">{_e(t)}</div>' for c, t in banners)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{REFRESH_SECONDS}">
<title>Panel KatheBot</title><style>{CSS}</style></head>
<body><main>
<div id="stale" class="banner bad" hidden></div>
{banner_html}
<header><div><h1>KatheBot · Topstep {mode_badge}</h1>
<div class="sub">Actualizado {_e(fmt_local(gen, tz, "%d/%m/%Y %H:%M:%S"))} (hora {_e(lab)}) · se recarga cada {REFRESH_SECONDS} s</div></div>
<div class="sub">Cuenta {_e(acct.get("id"))} · {_e(d.get("contract"))}</div></header>
<section class="grid-cards">{cards}</section>
<section class="two">{info}{stats}</section>
{chart}
{trades_html}
{journal_html}
<footer>Panel local generado por el bot en tu PC; no se envía a ningún sitio. Si esta página deja de actualizarse,
el bot está parado: las posiciones abiertas conservan su stop en el servidor de Topstep.</footer>
</main>
<script>
(function(){{var gen={gen_ms};function chk(){{var m=Math.round((Date.now()-gen)/60000);var b=document.getElementById('stale');
if(Date.now()-gen>{STALE_SECONDS * 1000}){{b.hidden=false;b.textContent='El panel no se actualiza desde hace '+m+
' min: ¿el bot está parado o el PC se suspendió?';}}}}chk();setInterval(chk,5000);}})();
</script>
</body></html>
"""
