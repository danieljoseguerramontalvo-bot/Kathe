"""Cliente mínimo de la API ProjectX Gateway (TopstepX), solo con la biblioteca estándar.

Referencia: https://gateway.docs.projectx.com (base por defecto ``https://api.topstepx.com``).
Autenticación con API key: ``POST /api/Auth/loginKey`` {userName, apiKey} -> token JWT (24 h),
que se envía como ``Authorization: Bearer <token>``; ``/api/Auth/validate`` lo renueva.

Códigos (ProjectX): lado 0 = compra, 1 = venta; tipo 1 = límite, 2 = mercado, 4 = stop,
5 = trailing stop; unidad de velas 1 = segundo, 2 = minuto, 3 = hora, 4 = día.
Límites de la API (según Topstep): 200 peticiones / 60 s en general y 50 / 30 s para velas.

Las credenciales se leen de variables de entorno (``TOPSTEPX_USERNAME``, ``TOPSTEPX_API_KEY``);
nunca se escriben en archivos ni en los diarios.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone

DEFAULT_BASE_URL = "https://api.topstepx.com"

SIDE_BUY, SIDE_SELL = 0, 1
TYPE_LIMIT, TYPE_MARKET, TYPE_STOP, TYPE_TRAILING_STOP = 1, 2, 4, 5
UNIT_SECOND, UNIT_MINUTE, UNIT_HOUR, UNIT_DAY = 1, 2, 3, 4


class ProjectXError(RuntimeError):
    """La API respondió con success = false o con un error HTTP definitivo."""

    def __init__(self, message: str, code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RateLimiter:
    """Ventana deslizante: como mucho ``max_calls`` en ``period`` segundos."""

    def __init__(self, max_calls: int, period: float, clock=time.monotonic, sleep=time.sleep):
        self.max_calls, self.period, self.clock, self.sleep = max_calls, period, clock, sleep
        self.calls: deque = deque()

    def wait(self):
        now = self.clock()
        while self.calls and now - self.calls[0] >= self.period:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            self.sleep(self.period - (now - self.calls[0]) + 0.05)
            now = self.clock()
            while self.calls and now - self.calls[0] >= self.period:
                self.calls.popleft()
        self.calls.append(now)


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class ProjectXClient:
    def __init__(self, username: str | None = None, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 20.0, transport=None, clock=time.monotonic, sleep=time.sleep, retries: int = 4):
        self.username = username if username is not None else os.environ.get("TOPSTEPX_USERNAME")
        self._api_key = api_key if api_key is not None else os.environ.get("TOPSTEPX_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport or _urllib_transport
        self.clock, self.sleep, self.retries = clock, sleep, retries
        self.token: str | None = None
        self.token_time: float | None = None
        self.limits = {"default": RateLimiter(190, 60.0, clock, sleep), "bars": RateLimiter(45, 30.0, clock, sleep)}

    def __repr__(self):  # nunca mostrar la clave
        return f"ProjectXClient(user={self.username!r}, base_url={self.base_url!r}, token={'sí' if self.token else 'no'})"

    # ------------------------------------------------------------------ transporte
    def _post(self, path: str, body: dict, bucket: str = "default", auth: bool = True) -> dict:
        if auth:
            self.ensure_token()
        payload = json.dumps(body).encode("utf-8")
        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            self.limits[bucket].wait()
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if auth and self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            try:
                status, raw = self.transport("POST", self.base_url + path, headers, payload, self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last_err = ProjectXError(f"{path}: error de red {e}", retryable=True)
            else:
                if status == 401 and auth and attempt < self.retries:
                    self.token = None                      # token caducado: nuevo login y reintento
                    self.ensure_token()
                    continue
                if status == 429 or status >= 500:
                    last_err = ProjectXError(f"{path}: HTTP {status}", code=status, retryable=True)
                elif status != 200:
                    raise ProjectXError(f"{path}: HTTP {status} {raw[:200]!r}", code=status)
                else:
                    data = json.loads(raw.decode("utf-8") or "{}")
                    if not data.get("success", False) or int(data.get("errorCode") or 0) != 0:
                        raise ProjectXError(f"{path}: {data.get('errorMessage') or 'error'} "
                                            f"(código {data.get('errorCode')})", code=data.get("errorCode"))
                    return data
            if attempt < self.retries:
                self.sleep(delay)
                delay = min(delay * 2, 16.0)
        raise last_err or ProjectXError(f"{path}: sin respuesta")

    # ------------------------------------------------------------------ sesión
    def login(self) -> None:
        if not self.username or not self._api_key:
            raise ProjectXError("faltan TOPSTEPX_USERNAME / TOPSTEPX_API_KEY en las variables de entorno")
        try:
            data = self._post("/api/Auth/loginKey", {"userName": self.username, "apiKey": self._api_key}, auth=False)
        except ProjectXError as e:
            if e.code == 3:
                raise ProjectXError("inicio de sesión rechazado (código 3): el usuario de TopstepX o la API key no son "
                                    "correctos. Usa el «Username» del correo de Topstep «Trading Combine credentials» "
                                    "(a menudo es tu email; no el nombre de la cuenta ni el usuario del panel de ProjectX) "
                                    "y una clave copiada con el icono de copiar.", code=3) from None
            raise
        self.token, self.token_time = data["token"], self.clock()

    def ensure_token(self) -> None:
        if self.token is None:
            self.login()
            return
        if self.clock() - (self.token_time or 0) > 20 * 3600:      # los tokens duran 24 h
            old = self.token
            self.token_time = self.clock()          # evita que _post vuelva a entrar aquí
            try:
                data = self._post("/api/Auth/validate", {}, auth=True)
                self.token = data.get("newToken") or old
            except ProjectXError:
                self.token = None
                self.login()

    # ------------------------------------------------------------------ cuentas y contratos
    def accounts(self, only_active: bool = True) -> list[dict]:
        return self._post("/api/Account/search", {"onlyActiveAccounts": only_active}).get("accounts", [])

    def contracts(self, search_text: str, live: bool = False) -> list[dict]:
        return self._post("/api/Contract/search", {"searchText": search_text, "live": live}).get("contracts", [])

    # ------------------------------------------------------------------ datos
    def bars(self, contract_id: str, start: datetime, end: datetime, unit: int = UNIT_MINUTE, unit_number: int = 1,
             limit: int = 20000, live: bool = False, include_partial: bool = False) -> list[dict]:
        data = self._post("/api/History/retrieveBars", {
            "contractId": contract_id, "live": live, "startTime": iso_utc(start), "endTime": iso_utc(end),
            "unit": unit, "unitNumber": unit_number, "limit": limit, "includePartialBar": include_partial,
        }, bucket="bars")
        return data.get("bars", [])

    # ------------------------------------------------------------------ órdenes y posiciones
    def place_order(self, account_id: int, contract_id: str, order_type: int, side: int, size: int,
                    limit_price: float | None = None, stop_price: float | None = None, custom_tag: str | None = None,
                    stop_loss_ticks: int | None = None, take_profit_ticks: int | None = None) -> int:
        body = {"accountId": account_id, "contractId": contract_id, "type": order_type, "side": side, "size": int(size)}
        if limit_price is not None:
            body["limitPrice"] = limit_price
        if stop_price is not None:
            body["stopPrice"] = stop_price
        if custom_tag:
            body["customTag"] = custom_tag
        if stop_loss_ticks:
            body["stopLossBracket"] = {"ticks": int(stop_loss_ticks), "type": TYPE_STOP}
        if take_profit_ticks:
            body["takeProfitBracket"] = {"ticks": int(take_profit_ticks), "type": TYPE_LIMIT}
        return int(self._post("/api/Order/place", body)["orderId"])

    def cancel_order(self, account_id: int, order_id: int) -> None:
        self._post("/api/Order/cancel", {"accountId": account_id, "orderId": order_id})

    def modify_order(self, account_id: int, order_id: int, stop_price: float | None = None,
                     limit_price: float | None = None, size: int | None = None) -> None:
        body = {"accountId": account_id, "orderId": order_id}
        if stop_price is not None:
            body["stopPrice"] = stop_price
        if limit_price is not None:
            body["limitPrice"] = limit_price
        if size is not None:
            body["size"] = int(size)
        self._post("/api/Order/modify", body)

    def open_orders(self, account_id: int) -> list[dict]:
        return self._post("/api/Order/searchOpen", {"accountId": account_id}).get("orders", [])

    def open_positions(self, account_id: int) -> list[dict]:
        return self._post("/api/Position/searchOpen", {"accountId": account_id}).get("positions", [])

    def close_position(self, account_id: int, contract_id: str) -> None:
        self._post("/api/Position/closeContract", {"accountId": account_id, "contractId": contract_id})

    def trades(self, account_id: int, start: datetime, end: datetime | None = None) -> list[dict]:
        body = {"accountId": account_id, "startTimestamp": iso_utc(start)}
        if end is not None:
            body["endTimestamp"] = iso_utc(end)
        return self._post("/api/Trade/search", body).get("trades", [])
