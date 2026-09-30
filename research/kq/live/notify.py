"""Avisos por Telegram del bot de Topstep (gratis; solo biblioteca estándar).

Configuración, una vez, desde la carpeta ``research``::

    python -m kq.live.notify --setup

1. En Telegram, abre @BotFather, envía /newbot, elige un nombre y copia el token que te da.
2. Pega el token cuando se pida (no se muestra en pantalla).
3. Abre el enlace de tu bot y pulsa «Iniciar»: el programa espera solo hasta 3 minutos.

El token y tu chat id se guardan en ``telegram.txt`` (no se sube a git) y se envía un mensaje de prueba.
También valen las variables de entorno TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.
Un fallo de Telegram nunca detiene el bot: los mensajes se envían en segundo plano.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

from .projectx import _urllib_transport

API = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_FILE = "telegram.txt"


class TelegramError(RuntimeError):
    pass


def call(token: str, method: str, params: dict, transport=None, timeout: float = 10.0) -> object:
    transport = transport or _urllib_transport
    status, raw = transport("POST", API.format(token=token, method=method),
                            {"Content-Type": "application/json"}, json.dumps(params).encode("utf-8"), timeout)
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        data = {}
    if status != 200 or not data.get("ok"):
        raise TelegramError(f"Telegram {method}: HTTP {status} {data.get('description', '')}".strip())
    return data.get("result")


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str | int, transport=None, background: bool = True, log=print):
        self.token, self.chat_id = token, str(chat_id)
        self.transport, self.log = transport, log
        self._last_error_at: float | None = None
        self._q: queue.Queue | None = None
        if background:
            self._q = queue.Queue()
            threading.Thread(target=self._worker, daemon=True).start()

    def __repr__(self):  # nunca mostrar el token
        return f"TelegramNotifier(chat_id={self.chat_id!r})"

    def send(self, text: str) -> None:
        if self._q is not None:
            self._q.put(text)
        else:
            self._send(text)

    def flush(self, timeout: float = 8.0) -> None:
        """Espera a que salgan los mensajes pendientes (p. ej. antes de cerrar el programa)."""
        end = time.monotonic() + timeout
        while self._q is not None and self._q.unfinished_tasks and time.monotonic() < end:
            time.sleep(0.1)

    def _send(self, text: str) -> bool:
        try:
            call(self.token, "sendMessage", {"chat_id": self.chat_id, "text": text[:4000],
                                             "disable_web_page_preview": True}, self.transport)
            return True
        except Exception as e:  # noqa: BLE001 - un aviso fallido no puede parar el bot
            if self._last_error_at is None or time.monotonic() - self._last_error_at > 600:
                self._last_error_at = time.monotonic()
                self.log(f"(Telegram: no se pudo enviar un aviso: {e})")
            return False

    def _worker(self):
        while True:
            text = self._q.get()
            try:
                self._send(text)
            finally:
                self._q.task_done()


def load_notifier(path: str | Path = TELEGRAM_FILE, env=None, **kw) -> TelegramNotifier | None:
    env = os.environ if env is None else env
    token, chat = (env.get("TELEGRAM_BOT_TOKEN") or "").strip(), (env.get("TELEGRAM_CHAT_ID") or "").strip()
    if (not token or not chat) and Path(path).exists():
        lines = [x.strip() for x in Path(path).read_text(encoding="utf-8-sig").splitlines() if x.strip()]
        if len(lines) >= 2:
            token, chat = lines[0], lines[1]
    if not token or not chat:
        return None
    return TelegramNotifier(token, chat, **kw)


def wait_for_chat(token: str, transport=None, seconds: float = 180.0, clock=time.monotonic) -> int | None:
    """Espera (long polling) hasta que alguien escriba al bot y devuelve el id de ese chat."""
    end = clock() + seconds
    while True:
        updates = call(token, "getUpdates", {"timeout": 20}, transport, timeout=30.0) or []
        chats = [u["message"]["chat"]["id"] for u in updates if isinstance(u, dict) and u.get("message", {}).get("chat")]
        if chats:
            return chats[-1]
        if clock() >= end:
            return None


def setup(getpass_fn=None, transport=None, path: str | Path = TELEGRAM_FILE, wait_seconds: float = 180.0,
          clock=time.monotonic) -> int:
    import getpass
    getpass_fn = getpass_fn or getpass.getpass
    print("1) En Telegram abre @BotFather, envía /newbot, elige un nombre y copia el token.")
    token = getpass_fn("Token del bot de Telegram (no se verá; pégalo con clic derecho y pulsa Enter): ").strip().strip('"')
    try:
        me = call(token, "getMe", {}, transport)
    except TelegramError as e:
        print(f"El token no es válido: {e}")
        return 1
    try:
        call(token, "deleteWebhook", {}, transport)       # getUpdates no funciona si hay un webhook puesto
    except TelegramError:
        pass
    print(f"2) En el móvil abre  https://t.me/{me.get('username')}  y pulsa el botón INICIAR (abajo),")
    print("   o escríbele cualquier mensaje. No hace falta tocar nada aquí.")
    print(f"   Esperando tu mensaje (hasta {int(wait_seconds // 60)} minutos)...")
    chat_id = wait_for_chat(token, transport, wait_seconds, clock)
    if chat_id is None:
        print("No llegó ningún mensaje a tu bot. Repite  python -m kq.live.notify --setup  y pulsa INICIAR en "
              f"https://t.me/{me.get('username')}")
        return 1
    Path(path).write_text(f"{token}\n{chat_id}\n", encoding="utf-8")
    TelegramNotifier(token, chat_id, transport, background=False).send(
        "✅ KatheBot conectado a Telegram. Aquí recibirás las entradas, salidas, avisos y el resumen diario.")
    print(f"Listo: guardado en {Path(path).resolve()} y mensaje de prueba enviado. No compartas ese archivo.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Avisos por Telegram del bot de Topstep")
    ap.add_argument("--setup", action="store_true", help="conectar tu Telegram (una vez)")
    ap.add_argument("--test", action="store_true", help="enviar un mensaje de prueba")
    a = ap.parse_args(argv)
    if a.setup:
        return setup()
    if a.test:
        n = load_notifier(background=False)
        if n is None:
            print("Telegram no está configurado: ejecuta  python -m kq.live.notify --setup")
            return 1
        return 0 if n._send("🔔 Prueba de KatheBot: los avisos funcionan.") else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
