# Bot KatheQuant en Topstep (TopstepX, API ProjectX)

Topstep opera **futuros del CME**, no CFD, y no usa MetaTrader. El EA de MQL5 no funciona ahí. Para Topstep hay un bot en Python que usa la misma lógica que el motor de investigación (`research/kq`). En cada vela de 1 minuto vuelve a pasar la estrategia por el historial y copia la posición que la estrategia quiere en ese momento. Así lo que se opera es exactamente lo que se prueba.

- Código: `research/kq/live/topstep_bot.py` y `research/kq/live/projectx.py`, con 30 pruebas contra un servidor simulado.
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

## Panel general

Al arrancar se abre **`panel_general.html`**, en la carpeta `research`. Es una sola página con:
- la cuenta: saldo, resultado total y del día, objetivo y distancia al MLL;
- cada turno: horario, próxima entrada o cierre, posición y última señal (entrada, stop y objetivo, o por qué se descartó);
- una tabla con las señales y operaciones de todos los turnos.

Cada turno enlaza a su panel detallado.

Los avisos de Telegram de cada señal llevan siempre la entrada, el stop (con el riesgo en USD), el objetivo o «sin objetivo fijo» y la hora de cierre prevista, **también cuando la señal se descarta**. En ese caso se añade el motivo.

## Panel

Al arrancar, el bot abre `topstep_state\panel.html` en el navegador. Es una página local: no usa internet ni ningún servicio, y se recarga sola cada 20 segundos. Si la cierras, ábrela otra vez con doble clic.

Qué muestra:
- **Cuenta:** saldo, resultado total, resultado del día de Topstep y distancia al MLL estimado.
- **Posición del bot:** precio medio, stop, resultado aproximado y las órdenes de protección que hay en el servidor.
- **Horario:** próxima entrada y salida de la estrategia.
- **Curva de saldo:** con las líneas del saldo inicial, el colchón y el MLL.
- **Operaciones:** las ejecuciones de la cuenta según la API y su resumen (acierto, bruto, comisiones, neto).
- **Diario del bot:** los últimos eventos.

Todas las horas salen en formato de 12 horas y en `display_tz`, que por defecto es Aruba (UTC-4, igual que Venezuela). Si la página deja de actualizarse más de 2 minutos, avisa en rojo de que el bot parece parado.

La consola también muestra cada evento, más una línea por hora («Funcionando…»).

## Avisos por Telegram (opcional, gratis)

El bot te avisa al móvil de:
- el arranque y la parada del bot;
- cada entrada, con su stop y su objetivo;
- cada salida, con el resultado en USD (comisiones incluidas) y lo que falta para el objetivo del Combine;
- los días en que no opera y por qué;
- los errores y los bloqueos;
- un resumen al cambiar el día de Topstep.

**Configurarlo (una vez), desde la carpeta `research`:**
```powershell
python -m kq.live.notify --setup
```
1. En Telegram, abre **@BotFather**, envía `/newbot`, elige un nombre y copia el token que te da.
2. Pégalo cuando se pida. No se ve al escribir.
3. Abre el enlace de tu bot en el móvil y pulsa **Iniciar**. El programa espera solo, hasta 3 minutos.

Queda guardado en `telegram.txt`, que no se sube a git, y recibes un mensaje de prueba. Después reinicia el bot: al arrancar dirá «Avisos por Telegram: activados».

Si Telegram falla, el bot sigue operando igual.

## Configuración actual (desde el 30-09-2026): dos turnos de oro y el Nasdaq en señales

| Archivo en tu PC | Plantilla | Qué hace | Hora de Aruba |
|---|---|---|---|
| `topstep.json` | `live/topstep.oro_dia_ejecucion.json` | **ORO DIA, ejecuta:** vende 1 MGC; stop de 2×ATR(H1) | de 6:00 a. m. a 1:00 p. m., de lunes a viernes |
| `topstep_oro_noche.json` | `live/topstep.h3a_ejecucion.json` | **ORO NOCHE, ejecuta:** compra 1 MGC (H3a); stop de 2×ATR(H1) | de 8:00 p. m. a 4:00 a. m., de domingo a jueves |
| `topstep_mnq.json` | `live/topstep.mnq_senales.json` | **NASDAQ, solo señales:** compra de micro Nasdaq nocturna | de 7:00 p. m. a 9:00 a. m., de lunes a jueves |

```powershell
python -m kq.live.topstep_bot --config topstep.json --config topstep_oro_noche.json --config topstep_mnq.json
```

- **Varios turnos en la misma cuenta:** el bot solo acepta que ejecuten a la vez turnos SESSION_DRIFT cuyos horarios no coincidan (se cuenta también la hora de salida). Así nunca hay dos posiciones abiertas.
- **Límites compartidos:** los dos turnos de oro caen en el mismo día de Topstep. La pérdida diaria y el colchón del MLL se calculan con el saldo común, así que tras una pérdida completa (−350) el segundo turno no entra: 350 + 350 superaría los 500 del límite diario.
- **Nombres:** `label` da nombre a cada turno en la consola y en Telegram.
- **Resumen diario:** lo manda solo el primer turno en ejecución.
- **Validación:** ninguna de las tres está validada. La enmienda 4 del protocolo fija cómo se evalúan, turno a turno.

## Varios mercados a la vez (Nasdaq en modo señales)

Un solo proceso puede llevar varios mercados con una única sesión de la API. Hay que repetir `--config`:

```powershell
python -m kq.live.topstep_bot --config topstep.json --config topstep_mnq.json
```

Cómo funciona:
- **Cada configuración tiene su propia carpeta** (`state_dir`), con su diario y su panel.
- **Solo una puede ejecutar en cada cuenta.** El bot se niega a arrancar si dos configuraciones ejecutan en la misma cuenta, porque el riesgo combinado no está coordinado.
- **Si un mercado en modo señales no arranca** (por ejemplo, porque no encuentra el contrato), los demás siguen.
- **Los avisos de Telegram** llevan delante el mercado: `[MGC]`, `[MNQ]`.

**`live/topstep.mnq_senales.json` (MNQ, micro Nasdaq): prueba prospectiva, solo señales**
- **Reglas:** compra a las 23:00 UTC y cierra a las 13:00 UTC, con stop de 3 × ATR(H1). En hora de Aruba: entra a las 7:00 p. m. y sale a las 9:00 a. m., de lunes a jueves.
- **Hipótesis:** la «deriva nocturna» de los índices de EE. UU. Está documentada en la literatura: Cooper, Cliff y Gulen (2008); Lou, Polk y Skouras (2019); Boyarchenko, Larsen y Whelan, «The Overnight Drift» (2023).
- **No está probada con nuestros datos.** Por eso no envía órdenes.
- **Cada salida anota su resultado teórico** (el del mismo motor, con costes) y un acumulado. Así la hipótesis se valida con datos nuevos, sin arriesgar la cuenta.
- Solo se pasará a ejecución si ese registro prospectivo lo justifica.

**Bitcoin:** no hay una hipótesis con evidencia que se pueda defender, así que no se generan señales.

## Funcionamiento desatendido (sin tocar el PC)

**Con el PC apagado no se puede.** Topstep prohíbe usar la API desde un VPS, una VPN o un servidor remoto, y si lo detecta cierra la cuenta. Lo más cerca que se puede llegar es que el bot funcione sin que tengas que usar el PC:

```powershell
python -m kq.live.autoinicio --instalar
```

Hazlo una vez, desde la carpeta `research`. Hace esto:
- **Credenciales:** guarda el usuario en `usuario_topstepx.txt` y la API key en `clave_topstepx.txt`. Quedan solo en tu PC y no se suben a git.
- **Arranque manual:** crea `iniciar_bot.cmd`; con doble clic arranca el bot con las configuraciones que existan (`topstep.json`, `topstep_oro_noche.json`, `topstep_mnq.json`).
- **Arranque automático:** lo añade a la carpeta de Inicio de Windows. Al iniciar sesión, el bot arranca solo en modo `--auto`:
  - no pregunta nada;
  - si no hay internet o algo falla, vuelve a intentarlo cada 60 s;
  - avisa por Telegram de cada caída y de cada arranque.
- **Energía:** desactiva la suspensión y la hibernación con el PC enchufado.
- **Candados:** si el PC se apagó de golpe, el candado que quedó se detecta como abandonado y se recupera solo.

Para quitarlo: `python -m kq.live.autoinicio --quitar`.

Recomendaciones:
- En la BIOS, activa «encender al volver la corriente» (*Restore on AC power loss*). Si además quieres que arranque sin ti tras un apagón, activa el inicio de sesión automático de Windows.
- En Windows Update, fija el horario activo para que no reinicie de madrugada.

**Aviso si el PC se apaga (opcional y gratis):** un bot apagado no puede avisar de que está apagado. Para eso hace falta un vigilante externo:
1. Crea una cuenta gratuita en healthchecks.io y un *check* con periodo de 5 minutos.
2. Conecta ahí tu Telegram.
3. Pon su URL en `heartbeat_url` de `topstep.json`.

El bot le envía un latido cada minuto, y si dejan de llegar, healthchecks te avisa. Solo recibe latidos, nunca datos de la cuenta.

**Si quieres operar con el PC apagado,** necesitas una firma que permita VPS, normalmente con MetaTrader 5. El EA `KatheQuant_v5.mq5` ya tiene la misma estrategia (`KQ_STRAT_SESSION_DRIFT`) y podría funcionar en un VPS. En cuentas reales va solo con señales, según las reglas del proyecto.

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
| `label` | — | Nombre del turno en la consola y en Telegram |
| `heartbeat_url` | — | URL del vigilante externo, p. ej. healthchecks.io (opcional) |
| `profit_target_usd` | 3000 | Objetivo de beneficio del Combine. Compruébalo en TopstepX |
| `consistency_pct` | 50 | Regla de consistencia: el mejor día debe ser menos de este % del beneficio total |

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
