# Bot KatheQuant en Topstep (TopstepX, API ProjectX)

Topstep opera **futuros del CME**, no CFD, y no usa MetaTrader. El EA de MQL5 no funciona ahí. Para Topstep hay un bot en Python que usa la misma lógica que el motor de investigación (`research/kq`). En cada vela de 1 minuto vuelve a pasar la estrategia por el historial y copia la posición que la estrategia quiere en ese momento. Así lo que se opera es exactamente lo que se prueba.

- Código: `research/kq/live/topstep_bot.py` y `research/kq/live/projectx.py`, con 16 pruebas contra un servidor simulado.
- Configuración de ejemplo: `research/live/topstep.ejemplo.json`.

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

1. Descarga el repositorio: en GitHub, rama `claude/mql5-ema-crossover-advisor-awun6l` → **Code → Download ZIP**, y descomprímelo.
2. Abre PowerShell en la carpeta `research` y ejecuta:
   ```powershell
   pip install -e .
   copy live\topstep.ejemplo.json topstep.json
   ```

## Credenciales: nunca en archivos

Ponlas en variables de entorno, en cada sesión de PowerShell:

```powershell
$env:TOPSTEPX_USERNAME = "tu_usuario_de_topstep"
$env:TOPSTEPX_API_KEY  = "tu_api_key"
```

- El bot **rechaza** una configuración que contenga claves.
- No las pegues en el chat ni las subas a GitHub.
- Si una clave se expone, revócala en TopstepX → Settings → API.

## Paso 1: solo señales (1–2 semanas)

```powershell
python -m kq.live.topstep_bot --config topstep.json
```

- Al arrancar, el bot lista tus cuentas: id, nombre, si es simulada y si puede operar. Anota el id de tu Combine.
- Con `"execute": false` **no envía órdenes**. Anota cada señal, con su stop, su objetivo y el tamaño, en `topstep_state\diario.csv`.
- Revisa que las señales tienen sentido y mándame el diario.

## Paso 2: ejecución en el Combine

En `topstep.json`:

```json
"account_ids": [123456],
"execute": true
```

Vuelve a arrancarlo.

- El bot se niega a ejecutar si la cuenta no está en `account_ids`, si la API no la marca como simulada o si la cuenta no puede operar.
- **Para pararlo:** Ctrl+C. Las posiciones abiertas se quedan con su stop en el servidor de Topstep.

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

- **El bot no se ha conectado nunca a TopstepX.** Desde este entorno no hay acceso a la API ni a tu cuenta.
- Los nombres de los campos y los códigos salen de la documentación pública de ProjectX y de dos SDK de código abierto.
- **Por eso el primer uso real tiene que ser en modo señales.**
