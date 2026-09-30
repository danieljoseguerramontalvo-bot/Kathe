# Bot KatheQuant en Topstep (TopstepX, API ProjectX)

Topstep opera **futuros del CME**, no CFD, y no usa MetaTrader. El EA de MQL5 no funciona ahí. Para Topstep hay un bot en Python que usa la misma lógica que el motor de investigación (`research/kq`). En cada vela de 1 minuto vuelve a pasar la estrategia por el historial y copia la posición que la estrategia quiere en ese momento. Así lo que se opera es exactamente lo que se prueba.

- Código: `research/kq/live/topstep_bot.py` y `research/kq/live/projectx.py`, con 25 pruebas contra un servidor simulado.
- Configuración de ejemplo (solo señales): `research/live/topstep.ejemplo.json`.
- Configuración de ejecución H3a: `research/live/topstep.h3a_ejecucion.json`.

## Qué necesitas

1. **Una cuenta de Topstep:** Trading Combine, o práctica si la tienes.
   - Los bots **no** están permitidos en la Live Funded Account. El bot, además, solo ejecuta en cuentas que la API marque como simuladas.
2. **Acceso a la API:**
   - En TopstepX: **Settings → API → ProjectX Linking**.
   - Suscríbete a «ProjectX API Access». Según Topstep cuesta 29 USD al mes, y con el código `topstep` hay un 50 % de descuento. Comprueba el precio al contratar.
   - Después pulsa **Add API Key**.
3. **Un PC con Windows y Python 3.11 o superior** (python.org; marca «Add to PATH»).
   - **Topstep prohíbe usar la API desde un VPS, una VPN o un servidor remoto.** El bot tiene que correr en tu PC, y tienes que vigilarlo.
4. En TopstepX, activa **Auto OCO Brackets** (Settings → Risk Settings) para que el stop y el objetivo se cancelen entre sí.
   - Si aun así el stop no aparece en el lado correcto, el bot pone uno propio y, si no puede, cierra la posición.

## Instalación (una vez)

1. **Descarga el código.** Con tu sesión de GitHub abierta en el navegador, abre:
   `https://github.com/danieljoseguerramontalvo-bot/Kathe/archive/refs/heads/claude/mql5-ema-crossover-advisor-awun6l.zip`
2. **Descomprímelo** en `C:\KatheBot`. Quedará una carpeta `C:\KatheBot\Kathe-claude-mql5-ema-crossover-advisor-awun6l`.
3. **Abre PowerShell y ejecuta, línea a línea:**
   ```powershell
   cd C:\KatheBot\Kathe-claude-mql5-ema-crossover-advisor-awun6l\research
   pip install -e .
   copy live\topstep.ejemplo.json topstep.json
   ```
   - No lo ejecutes desde `C:\WINDOWS\System32`: el bot tiene que arrancar desde la carpeta `research`.
   - Si PowerShell se queda en `>>` (una comilla sin cerrar), pulsa **Ctrl+C**.

## Credenciales: nunca en archivos ni en pantalla

- **El bot te pide el usuario y la API key al arrancar.** La clave no se ve mientras la escribes: pégala con **clic derecho** y pulsa **Enter**.
- No hace falta escribirla en ningún comando.
- **No hagas capturas de pantalla donde se vea la clave.** Si ocurre, revócala en TopstepX → Settings → API (papelera) y crea otra.
- El bot **rechaza** una configuración que contenga claves.

## Paso 1: solo señales (1–2 semanas)

Desde la carpeta `research`:

```powershell
python -m kq.live.topstep_bot --config topstep.json --once
```

- Al arrancar, el bot lista tus cuentas: id, nombre, si es simulada y si puede operar. Anota el id de tu Combine.
- Con `"execute": false` **no envía órdenes**. Anota cada señal, con su stop, su objetivo y el tamaño, en `topstep_state\diario.csv`.
- Para dejarlo funcionando, quita `--once`. Para pararlo, pulsa **Ctrl+C**.
- Revisa que las señales tienen sentido y mándame el diario.

## Paso 2: ejecución en el Combine

En `topstep.json`:

```json
"account_ids": [123456],
"execute": true
```

Vuelve a arrancarlo.

**Configuración de ejecución H3a.** `live\topstep.h3a_ejecucion.json` trae la estrategia SESSION_DRIFT: compra a las 00:00 UTC, cierra a las 08:00 UTC, stop de 3 × ATR(H1), 1 MGC como máximo y un riesgo máximo de 350 USD.
- Si tu descarga no trae ese archivo, abre `notepad topstep.json`, borra todo y pega su contenido.
- Pon el id de tu cuenta en `account_ids`.
- Guarda como UTF-8 (el bot también acepta UTF-8 con BOM).
- H3a **no está validada**. Es la mejor hipótesis del análisis previo, no una ventaja demostrada.

- El bot se niega a ejecutar si la cuenta no está en `account_ids`, si la API no la marca como simulada o si la cuenta no puede operar.
- **Para pararlo:** Ctrl+C. Las posiciones abiertas se quedan con su stop en el servidor de Topstep.

## Panel

Al arrancar, el bot abre `topstep_state\panel.html` en el navegador. Es una página local: no usa internet ni ningún servicio, y se recarga sola cada 20 segundos. Si la cierras, ábrela otra vez con doble clic.

Qué muestra:
- **Cuenta:** saldo, resultado total, resultado del día de Topstep y distancia al MLL estimado.
- **Posición del bot:** precio medio, stop, resultado aproximado y las órdenes de protección que hay en el servidor.
- **Horario:** próxima entrada y salida de la estrategia.
- **Curva de saldo:** con las líneas del saldo inicial, el colchón y el MLL.
- **Operaciones:** las ejecuciones de la cuenta según la API y su resumen (acierto, bruto, comisiones, neto).
- **Diario del bot:** los últimos eventos.

Todas las horas salen en `display_tz`, que por defecto es Aruba (UTC-4, igual que Venezuela). Si la página deja de actualizarse más de 2 minutos, avisa en rojo de que el bot parece parado.

La consola también muestra cada evento, más una línea por hora («Funcionando…»).

## Configuración y riesgo

| Clave | Valor por defecto | Qué hace |
|---|---|---|
| `symbol_search` | `MGC` | Micro oro: 10 oz; un tick de 0.10 vale 1 USD |
| `risk_usd_per_trade` | 200 | Riesgo por operación. Equivale al 10 % del límite de pérdida máxima de 50K, como arriesgar el 1 % en una cuenta que corta al 10 % |
| `max_contracts` | 5 | Tope de contratos |
| `daily_loss_limit_usd` | 500 | Al perder esto en el día de Topstep (que cambia a las 17:00 de Chicago), cierra y no opera más ese día |
| `mll_usd` / `initial_balance` | 2000 / 50000 | Para estimar el Maximum Loss Limit, que sube con el máximo de fin de día hasta el saldo inicial |
| `mll_floor_override` | — | Si lo conoces, el nivel exacto del MLL que muestra TopstepX |
| `mll_buffer_usd` | 500 | Nunca se acerca al MLL a menos de esto. Si ocurre, cierra y se bloquea |
| `entry_max_age_min` | 10 | No persigue señales viejas |
| `strategy` / `params` | `REF_T0` / `{}` | Cualquier estrategia del motor, con sus parámetros |
| `display_tz` | `America/Aruba` | Zona horaria de la consola y del panel |
| `open_panel` | `true` | Abre el panel en el navegador al arrancar |
| `trades_days` | 60 | Días de ejecuciones de la cuenta que muestra el panel |

**Reglas que no se pueden desactivar:**
- Contratos = riesgo ÷ pérdida al stop de 1 contrato, redondeado hacia abajo. **Si 1 contrato arriesga más de lo permitido, no entra.**
- Una sola posición.
- Sin martingala ni grid.
- Toda posición lleva stop.

**Ojo con la estrategia actual (T0 en H4).** Su stop es 1.5 × ATR de H4, a menudo 20–35 USD de precio. En MGC eso son 200–350 USD por contrato, más que los 200 de riesgo. Muchas señales se descartarán en una cuenta de 50K, y es intencionado: el bot nunca sube el riesgo para poder entrar. Con 100K o 150K (MLL de 3 000 y 4 500 USD) cabe más.

**T0 no es una estrategia validada.** En 2022–2024 no se distinguió del azar. Úsala para comprobar la mecánica. Cuando el protocolo encuentre un candidato, se cambia `strategy` y `params`.

## Datos para la investigación

El bot puede descargar velas de 1 minuto del contrato activo en el formato que usa el motor:

```powershell
python -m kq.live.topstep_bot --config topstep.json --export-bars 365 --out KQ_MGC_M1.csv
```

Si me subes `KQ_MGC_M1.csv` y `KQ_MGC_spec.json`, puedo ejecutar el protocolo con datos de futuros de oro.

- Solo cubre el historial del contrato actual; los contratos vencidos no se incluyen.
- Los futuros no traen spread por vela: se asume 1 tick, más el deslizamiento configurado.

## Lo que no se ha probado

- **Comprobado:** el inicio de sesión y el listado de cuentas funcionan contra TopstepX desde el PC del usuario.
  - El usuario de la API es el «Username» del correo de Topstep; en esta cuenta es el email.
- **Sin comprobar todavía:** el envío de órdenes, los brackets y el cierre contra el servidor real.
  - Los nombres de los campos y los códigos salen de la documentación pública de ProjectX y de dos SDK de código abierto.
  - Si los brackets se rechazan, el bot reintenta la entrada sin ellos y pone su propio stop. Si no puede, cierra la posición.
  - Revisa en TopstepX la primera operación: debe tener su stop en el lado correcto.
