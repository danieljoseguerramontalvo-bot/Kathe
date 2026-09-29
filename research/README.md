# Motor de investigación y backtesting XAUUSD (`research/`)

Motor en Python, reproducible y sin datos futuros, para evaluar estrategias de XAUUSD (CFD de oro)
con los datos M1 exportados de MetaTrader 5 (HF Markets). Todo lo que hay aquí se construyó y validó
con **datos sintéticos**: en esta sesión no hubo acceso a datos reales. **Ningún resultado sobre datos
sintéticos dice nada sobre el oro real**; sirven solo para comprobar que el motor funciona.

- Paquete: `research/kq/` · Tests: `research/tests/` (110 tests, `pytest`) · Registro: `research/registry/experiments.jsonl`
- Python 3.11, `numpy`, `pandas` (probado con 3.0), `scipy`, `tzdata`; `pytest` para los tests.

```bash
cd research
python3.11 -m pip install -e ".[test]"      # o: pip install numpy pandas scipy tzdata pytest
python3.11 -m pytest -q                      # 110 passed
```

---

## 1. Arquitectura

| Módulo | Qué hace |
|---|---|
| `kq/timeutil.py` | `server_to_utc()` / `utc_to_server()`: hora del servidor = hora de Nueva York + 7 h (UTC+2 en invierno de EE. UU., UTC+3 en verano). La pausa diaria de las 17:00 NY es siempre las 00:00 del servidor. |
| `kq/data.py` | `load_mt5_csv()`, `load_spec()`/`SymbolSpec`, `resample_bars()`, `MarketData` (M1 + velas M5/M15/H1/H4/D1 en caché). |
| `kq/costs.py` | `CostModel`: spread, deslizamiento, comisión, swap; `rollover_events()`, `floor_to_step()`. |
| `kq/indicators.py` | EMA (iMA), ATR (ATR.mq5), RSI (RSI.mq5), ADX (ADX.mq5), Efficiency Ratio, percentil móvil, canales Donchian. |
| `kq/strategies/` | `REF_T0`, `REF_RSI2`, `TREND_DONCHIAN`, `SESSION_BREAKOUT`, `SESSION_DRIFT`, `RANDOM_ENTRY`, `RegimeGate`, `SCRIPTED` (tests) y `make_strategy()`. |
| `kq/engine.py` | Simulador por eventos sobre M1: `BacktestConfig`, `run_backtest()`, `BacktestResult`. |
| `kq/metrics.py` | `compute_metrics()` y métricas sueltas (PF, t, drawdown, coste de equilibrio, estrés de costes…). |
| `kq/benchmark.py` | Comprar y mantener, `BUY_HOLD_VOLSCALED`, largo con la misma exposición, regresión alfa/beta. |
| `kq/validation.py` | Particiones, walk-forward, sensibilidad, bootstrap estacionario, Monte Carlo, PSR/DSR, Holm, test del mono, control de ancla aleatoria. |
| `kq/registry.py` | Registro de experimentos JSONL solo-añadir con cadena de hashes. |
| `kq/run.py` | CLI `python -m kq.run`. |
| `kq/synth.py` | Datos M1 sintéticos parecidos al oro (`python -m kq.synth`). |

Flujo: `MarketData` (M1 bid + spread) → la estrategia calcula indicadores sobre su marco temporal →
el motor recorre los *momentos de decisión* (cierres de vela), pregunta a la estrategia y ejecuta en
M1 → `BacktestResult` → `compute_metrics()` → `metrics.json` + registro.

## 2. Supuestos del motor (leer antes de interpretar resultados)

**Tiempo y velas**
- Todas las horas internas son hora del **servidor** (ingenua, int64 ns). Las velas superiores se
  construyen a partir de M1 y se etiquetan por su **hora de apertura** en hora del servidor: H4 empieza a
  las 00, 04, 08…; D1 a las 00:00 del servidor.
- Una vela que abre en `t` con duración `L` se considera **cerrada en `t + L`**. La señal de esa vela se
  ejecuta en la **apertura de la primera vela M1 con hora ≥ t + L** (si hay un hueco o fin de semana, la
  primera M1 que exista). La estrategia solo ve velas cerradas. Esto lo comprueban los tests
  (`tests/test_no_lookahead.py`): se alteran todos los datos posteriores a una fecha y todas las
  operaciones cerradas antes de esa fecha deben quedar idénticas, para todas las estrategias.

**Precios y ejecución**
- Los precios de MT5 son **BID**. Ask = Bid + spread × point, con el spread (en puntos) de esa misma vela M1.
- Compra al ask (apertura bid + spread), venta al bid. Los largos salen al bid y los cortos al ask.
- SL/TP de un largo: se activan cuando el **bid** (mínimo/máximo de la vela) cruza el nivel. De un corto:
  cuando el **ask** (bid + spread) lo cruza.
- SL y TP tocados en la misma vela M1 → se asume **SL** (pesimista), salvo que la apertura ya esté más allá
  de uno de los dos (entonces ese se ejecuta primero, porque la apertura es el primer precio).
- Hueco a través del stop en la apertura M1 → se ejecuta **a esa apertura** (peor que el stop). Hueco a
  través del TP → se ejecuta **al nivel del TP** (nunca mejor; conservador).
- `slippage_points` se suma en contra en **cada** ejecución (entrada, salida, SL y TP).
- Comisión por lote ida y vuelta (divisa de la cuenta), cargada completa al entrar.
- Swap por lote y noche (`points` como `SYMBOL_SWAP_MODE_POINTS`, o `money`), cobrado si la posición está
  abierta en la medianoche del servidor (entrada < 00:00 ≤ salida). Solo cuentan los días que terminan de
  lunes a viernes; el día `swap_3days` (numeración MT5: 3 = miércoles) cuenta triple. El swap se acumula en
  el flotante en ese momento y se realiza al cerrar.
- **Reglas de entrada comunes a todas las estrategias** (iguales que el EA, ver §12):
  1. **Ventana de rollover**: ninguna entrada nueva se ejecuta en una vela M1 cuyo minuto del día del servidor
     esté en `[rollover_from_min, rollover_to_min)` (por defecto 1425 → 75, es decir 23:45 → 01:15; puede cruzar
     la medianoche; `from == to` la desactiva).
  2. **Tope de spread**: ninguna entrada nueva se ejecuta en una vela M1 con spread > `max_spread_points`
     (60 puntos por defecto; 0 lo desactiva; una estrategia puede fijar el suyo con su parámetro
     `max_spread_points`).
  3. **Espera con plazo**: la entrada pendiente espera a la primera M1 que cumpla 1 y 2, pero solo hasta el
     **plazo** = mín(fin de la vela del marco de la estrategia en la que la señal se vuelve ejecutable,
     apertura de esa vela + `entry_deadline_min` = 90 min). Si no la hay, se descarta con motivo `rollover`,
     `spread` o `entry_deadline`. El retraso queda en `entry_delay_min` de cada operación.

  Consecuencia: las señales de las 00:00 del servidor (cierre de cada vela D1 y de la H4 de las 20:00) se
  ejecutan hacia las 01:15, no en la apertura de las ~01:00. Las salidas no se ven afectadas por estas reglas.

**Tamaño de la posición**
- Riesgo fijo sobre el **balance realizado** (como `ACCOUNT_BALANCE` en el EA):
  `lotes = floor_to_step(balance × riesgo% / pérdida_por_lote)`, con
  `pérdida_por_lote = |precio de entrada cotizado − SL| × contract_size × unidades_por_USD + comisión`.
- Si los lotes < `volume_min` → la operación **se omite** y se registra (`min_lot_exceeds_risk`); **nunca se
  redondea hacia arriba**. Por encima de `volume_max` se recorta y se registra.
- Lotes fijos: `BacktestConfig(risk_pct=None, fixed_lots=0.01)` o `--fixed-lots 0.01`.
- El SL y el TP se calculan desde el precio **cotizado** de entrada (ask en compras, bid en ventas), como el EA.
- Stop inválido (del lado equivocado del precio o a menos de `stops_level`) → se descarta (`invalid_stop`).
- Una posición a la vez por estrategia (`max_positions = 1`), salvo que la estrategia diga otra cosa.
- **R** = distancia inicial del stop en precio desde el precio **ejecutado**: `r_price = |entrada − SL inicial|`.
  `r_net = beneficio neto / (lotes × contract_size × unidades_por_USD × r_price)` → invariante al tamaño.
  Un stop completo sin costes vale exactamente −1R.
- Cuentas USC (céntimos): `account_units_per_usd = 100` (o `--units-per-usd 100`; por defecto se deduce de
  `account_currency` del spec). Todo el dinero (balance, comisión) va en la divisa de la cuenta.

**Stops dinámicos**
- Solo se actualizan en los **cierres de vela** del marco de la estrategia, solo pueden **estrecharse**
  (un largo solo sube, un corto solo baja) y se aplican desde la siguiente vela M1. Un nivel que al cierre de
  la vela no sería un SL válido (p. ej. por encima del bid en un largo) se rechaza, como haría MT5
  (`n_stop_moves_rejected`).

**Curva de capital**
- Marcada a mercado en **cada cierre M1** (largos al bid de cierre, cortos al ask de cierre, swap acumulado
  incluido). El drawdown máximo se mide sobre esa curva. `max_dd_intrabar_pct` usa además el peor precio
  dentro de cada vela (mínimo bid / máximo ask) frente al máximo previo de la curva de cierre.
- El Sharpe usa los rendimientos **diarios** (capital en el último cierre M1 de cada día del servidor con
  datos), anualizado con √252.

## 3. Cómo cargar la exportación de MT5

El script de exportación del usuario escribe:

- `KQ_<SÍMBOLO>_M1.csv` con cabecera `time,open,high,low,close,tick_volume,spread,real_volume`; `time` en hora
  del servidor con formato `YYYY.MM.DD HH:MM` (también se aceptan `YYYY-MM-DD HH:MM[:SS]`, el formato
  "Exportar barras" de MT5 con `<DATE>`/`<TIME>` separados por tabuladores, separador `;` y UTF-16);
  `spread` en puntos (entero) de esa vela M1.
- `KQ_<SÍMBOLO>_spec.json` (opcional) con claves como `symbol, digits, point, tick_size, tick_value,
  contract_size, volume_min, volume_max, volume_step, stops_level, swap_long, swap_short, swap_3days,
  account_currency, gmt_offset_seconds` (y opcionalmente `swap_mode`: 1 = puntos, 4 = dinero). Las claves
  desconocidas se guardan en `spec.extra`. Si el script de auditoría escribe `commission_per_lot_side_observed`
  (en NEGATIVO, con el signo de `DEAL_COMMISSION` de MT5), la CLI usa su **valor absoluto** × 2 como comisión
  por lote ida y vuelta cuando no se pasa `--commission`. Sin archivo se usan los valores de XAUUSD en HF Markets (2 dígitos,
  point 0.01, 100 oz por lote, lote mínimo 0.01).

```python
from kq import MarketData
md = MarketData.from_csv("KQ_XAUUSD_M1.csv", "KQ_XAUUSD_spec.json")
md.source["quality"]     # filas leídas, duplicados, OHLC incoherentes, huecos, spread mediano y p99
md.bars("H4")            # velas H4 (columnas open/high/low/close, spread, m1_start, close_time_ns, open_utc_ns...)
```

El cargador ordena por hora, elimina marcas de tiempo duplicadas (se queda la última), descarta precios
vacíos o ≤ 0 y repara velas con OHLC incoherente (lo cuenta en el informe). **Exporta al menos 6–12 meses
antes del inicio de la prueba**: los indicadores se calculan desde la primera vela del archivo (EMA200 en H4
necesita 600 velas de calentamiento, unos 5 meses) y solo después se limita el periodo de trading.

### 3.1 Alternativa: historial de Dukascopy (escenario B del protocolo)

Sirve para el escenario B del protocolo: historial largo, desde 2008. Solo funciona si la política de red del entorno permite `datafeed.dukascopy.com`.

```bash
python -m kq.dukascopy --symbol XAUUSD --start 2007-01-01 --end 2026-09-25 \
    --out data/KQ_XAUUSD_DUKA_M1.csv --cache data/raw/dukascopy
```

**Qué hace**
- Descarga los archivos diarios `BID/ASK_candles_min_1.bi5`, en UTC. El mes de la URL empieza en 0.
- Los guarda en caché: si se interrumpe, se puede reanudar. Un 404 cuenta como día vacío.
- Escribe un CSV con el mismo formato que la exportación de MT5:
  - precios BID;
  - hora del servidor NY+7;
  - `spread` = ASK open − BID open, en puntos de 0.01.
- Los minutos sin cotizaciones (volumen 0) se descartan, igual que MT5 no crea velas sin ticks.
- Un minuto sin ASK recibe la mediana del spread de ese día. El resumen cuenta cuántos hubo.
- El divisor de precio se detecta y se valida por rango. Queda anotado en el resumen.

**Límites**
- Precios y spreads son de Dukascopy, no de HF Markets, y su spread suele ser menor. Hay que añadir la diferencia observada con `KQ_AuditoriaEntorno`, con `--extra-spread-usd` o `--spread-audit` de `kq.protocol`. Como mínimo, hay que exigir las pruebas de estrés de +0.10, +0.20 y +0.40 USD del protocolo.
- El spread es el de la apertura del minuto; MT5 guarda un único valor por vela.

## 4. Ejecutar estrategias (CLI)

```bash
cd research
python -m kq.run --data KQ_XAUUSD_M1.csv --spec KQ_XAUUSD_spec.json \
    --strategy REF_T0 --params '{}' --start 2022-01-01 --end 2024-12-31 --out runs/t0_dev \
    --hypothesis-id H0_T0 --split dev
```

- `--start`/`--end`: fechas en hora del servidor; **`--end` es inclusivo** (se prueba el día completo).
- Escribe en `--out`: `trades.csv`, `equity.csv` (capital en el último cierre M1 de cada hora; `--equity-freq`
  M1/M5/…/D1), `metrics.json`, `skipped.csv` (señales descartadas y motivo), `daily_returns.csv`; y añade una
  línea al registro (`--registry` para otro archivo, `--no-registry` para no registrar).
- Otras opciones: `--initial-equity`, `--risk-pct` (1.0), `--fixed-lots`, `--units-per-usd`, `--commission`
  (por lote ida y vuelta; si se omite, 2 × |`commission_per_lot_side_observed`| del spec, o 0),
  `--slippage-points` (3, la base del protocolo), `--no-swap` (por defecto se cobra swap; `--swap-long/--swap-short`), `--spread-mult`, `--spread-floor`,
  `--rollover-from/--rollover-to` (1425/75), `--max-spread-points` (60; 0 = sin tope), `--entry-deadline-min` (90),
  `--n-trials` (para el Deflated Sharpe; por defecto, las configuraciones distintas del registro, esta incluida; con N = 1 el valor es el PSR frente a 0 y así se indica), `--no-benchmarks`.
- `metrics.json` incluye además bootstrap del Sharpe y de la media diaria, Deflated Sharpe, Monte Carlo de las
  operaciones y los benchmarks.

Ejemplos por estrategia (`--params` es JSON; los parámetros omitidos toman su valor por defecto y **todos**
quedan registrados):

```bash
# Referencia en vivo: T0 H4 (EMA 40/200 cruce + retroceso, ADX >= 20, SL 1.5 ATR, TP 3 ATR)
python -m kq.run ... --strategy REF_T0 --params '{}'
# RSI(2) de Connors en M15 con los filtros del informe +236 (F7)
python -m kq.run ... --strategy REF_RSI2 --params '{"timeframe": "M15", "adx_filter": true, "htf_filter": true, "trail_atr": 2.0}'
# Momentum de series temporales (Donchian N=55 en H4)
python -m kq.run ... --strategy TREND_DONCHIAN --params '{"timeframe": "H4", "n": 55, "k_sl": 2.0, "k_trail": 3.0}'
# Ruptura de sesión (rango 00-07 UTC, entradas 07-12 UTC, filtro de compresión 0.4, TP 2 anchos)
python -m kq.run ... --strategy SESSION_BREAKOUT --params '{"c_max": 0.4, "tp_mult": 2.0, "buffer_frac": 0.1}'
# Estacionalidad horaria: configuración confirmatoria por defecto = largo 00:00 -> 08:00 UTC, SL 3 ATR14(H1)
python -m kq.run ... --strategy SESSION_DRIFT --params '{}'
# Test del mono sobre T0 (p_entry se calibra solo si se omite)
python -m kq.run ... --strategy RANDOM_ENTRY --params '{"target": "REF_T0", "seed": 1}'
# Cualquier estrategia filtrada por régimen (tendencia por ER(D1,20) >= 0.3, solo volatilidad media/alta)
python -m kq.run ... --strategy TREND_DONCHIAN --params '{"n": 20, "regime_gate": {"allow_regime": "trend", "er_threshold": 0.3, "allow_vol": [1, 2]}}'
# Benchmarks
python -m kq.run ... --strategy BUY_HOLD_VOLSCALED --params '{"target_pct": 1.0}'
python -m kq.run ... --strategy BUY_HOLD
```

### Parámetros de cada estrategia

| Estrategia | Marco | Parámetros (valor por defecto) |
|---|---|---|
| `REF_T0` | H4 | `fast` 40, `slow` 200, `entry_mode` `cross_pullback` (o `cross_only`), `adx_period` 14, `adx_min` 20 (0 = sin filtro), `atr_period` 14, `sl_atr` 1.5, `tp_atr` 3.0, `close_on_opposite` true, `direction` both, `warmup_bars` None (= 3×slow) |
| `REF_RSI2` | M15 o H4 | `ema_period` 200, `rsi_period` 2, `buy_level` 10, `sell_level` 90, `exit_long` 70, `exit_short` 30, `atr_period` 14, `sl_atr` 1.5, `tp_atr` 6, `adx_filter` false (`adx_min` 20), `htf_filter` false (`htf_timeframe` H1, `htf_period` 200), `trail_atr` 0 (p. ej. 2), `session_start_hour`/`session_end_hour`/`close_hour` None (hora del servidor) |
| `TREND_DONCHIAN` | H4 o D1 | `n` 20 (o 55), `atr_period` 14, `k_sl` 2, `k_trail` 3 (0 = sin chandelier), `close_on_opposite` true |
| `SESSION_BREAKOUT` | M5 | `range_start_utc` 00:00, `range_end_utc` 07:00, `entry_start_utc` 07:00, `entry_end_utc` 12:00, `flat_utc` 20:00, `buffer_frac` 0.1, `c_max` 0.4 (None = sin filtro, variante incondicional), `tp_mult` 2 (1, 2 o None), `atr_period` 14 (D1), `min_range_coverage` 0.5 (≥ 50 % de las M1 esperadas de la ventana: 210 de 420), `anchor_mode` fixed/random, `anchor_seed`, `anchor_step_min` 15 |
| `SESSION_DRIFT` | rejilla horaria (ATR H1) | `h_in` 0, `h_out` 8, `side` +1, `sl_atr` 3, `atr_period` 14, `tp_atr` None, `weekdays` None, `max_exec_delay_min` 59, `skip_weekend_cross` true |
| `RANDOM_ENTRY` | el del objetivo | `target`, `target_params`, `p_entry` (se calibra), `seed`, `use_target_exits` true, `respect_entry_window` true |
| `regime_gate` (envoltorio) | — | `er_period` 20, `er_threshold` 0.3, `atr_period` 14, `pct_window` 250, `allow_regime` trend/range/any, `allow_vol` [0,1,2] |

Todas las estrategias aceptan además `max_spread_points` (None = el tope del motor, 60 puntos).

Detalles de las reglas:

- **REF_T0** (igual que `GetSignal` del EA v4): largo en la vela cerrada *i* si la EMA40 cruza por encima de la
  EMA200 entre *i−1* e *i*, o si EMA40[i] > EMA200[i] y close[i−1] ≤ EMA40[i−1] y close[i] > EMA40[i]; corto
  simétrico; los cruces tienen prioridad. El ADX(14) de MT5 solo bloquea la **entrada nueva**: la señal
  contraria **cierra** la posición aunque ADX < 20. Señales ignoradas durante el calentamiento (`Bars() < 3×200`,
  contando la vela en formación como el EA). SL/TP = 1.5/3 × ATR14 de la vela de la señal.
- **REF_RSI2**: salidas por RSI al cierre de vela (ejecución en la siguiente M1); filtro H1 con la **última
  vela H1 cerrada** (cierre frente a su EMA200, como el EA); trailing ATR solo en cierres de vela.
- **TREND_DONCHIAN**: chandelier idéntico al del EA: `stop = max(stop, máximo HIGH de las velas del marco
  cerradas desde la vela de entrada (incluida una vez cerrada) − k_trail × ATR14 de la última vela cerrada)`,
  espejo para cortos, solo en cierres y solo estrechando.
- **SESSION_BREAKOUT**: rango con máximos/mínimos M1 en la ventana UTC (el día sin al menos el 50 % de las M1
  esperadas no opera); como mucho **un intento por día** (el día se marca como usado cuando se EMITE la entrada,
  aunque luego el motor la descarte); SL en el lado opuesto del rango (el SL de un corto se compara con el ask);
  cierre forzoso a las 20:00 UTC.
- **SESSION_DRIFT**: entra en la primera M1 válida de la hora UTC `h_in` (plazo: el final de esa vela H1; si no hay
  mercado en 59 min, no entra) y sale en la hora `h_out`; no entra si la salida prevista cae en fin de semana.
- **RANDOM_ENTRY**: dirección aleatoria en momentos aleatorios con las mismas salidas del objetivo (su SL/TP,
  su gestión y, opcionalmente, sus salidas por señal contraria) y la misma frecuencia de entrada.

### Uso desde Python

```python
from kq import MarketData, BacktestConfig, CostModel, run_backtest, make_strategy, compute_metrics
md = MarketData.from_csv("KQ_XAUUSD_M1.csv", "KQ_XAUUSD_spec.json")
cfg = BacktestConfig(start="2022-01-01", end="2025-01-01", initial_equity=10_000, risk_pct=1.0,
                     account_units_per_usd=1, costs=CostModel(commission_per_lot_rt=0, slippage_points=5,
                                                              apply_swap=True))
res = run_backtest(md, make_strategy("REF_T0", {}), cfg)      # end es EXCLUSIVO en BacktestConfig
m = compute_metrics(res, md=md)                              # md -> incluye benchmarks
res.trades, res.skipped, res.equity_frame("H1"), res.daily_returns()
```

## 5. Benchmarks

`compute_metrics(res, md=md)` añade `benchmarks` a cada ejecución:
- `buy_hold`: mantener oro (cierres bid, sin costes).
- `buy_hold_volscaled` (**BUY_HOLD_VOLSCALED**): siempre largo, rebalanceo diario en la primera M1 fuera de la
  ventana de rollover y con spread ≤ tope, tamaño tal que 1 ATR14(D1) = `target_pct` % (1 %) del capital; paga el mismo modelo de
  costes (compra al ask + deslizamiento, venta al bid − deslizamiento, media comisión por lado, swap largo).
  **Las estrategias de tendencia deben compararse con él.**
- `exposure_matched_long`: largo solo mientras la estrategia tiene posición (sea cual sea su lado).
- `strategy_vs_buy_hold_volscaled`: regresión MCO de los rendimientos diarios de la estrategia sobre el
  benchmark (correlación, beta, alfa anual y su t) para ver si la ganancia es solo beta.
- Además cada informe separa el P&L de largos y cortos (`long_net_profit`, `short_net_profit`, `by_side`).

## 6. Métricas (`metrics.json`)

Número de operaciones; % de acierto; ganancia/pérdida media en dinero y en R; profit factor; esperanza en dinero
y en R; desviación de R; t y p (unilateral) de la media de R; Sharpe y Sortino diarios anualizados; CAGR;
drawdown máximo (M1 cierre e intrabarra), su duración, tiempo de recuperación y el drawdown más largo; rachas
máximas de pérdidas/ganancias; resultados por año, por lado y por hora UTC de entrada; exposición (% de cierres
M1 con posición); concentración (parte del beneficio neto de las 5 mejores operaciones y de los 5 mejores días);
estrés de costes (+10, +20, +40 puntos por operación, recalculado a posteriori con los mismos lotes: exacto en R);
**coste extra de equilibrio** (`break_even_extra_points_money` y `_r`: puntos por operación con los que la
esperanza neta vale 0; negativo = ya pierde); señales descartadas por tipo y motivo; avisos del motor.

## 7. Validación (API de Python, `kq.validation`)

```python
from kq.validation import *
from kq.strategies import scan_session_windows

# Particiones cronológicas
chronological_split("2022-01-01", "2026-07-01", cuts=["2025-01-01", "2025-09-01"],
                    names=["dev", "validation", "holdout"])

# Walk-forward (rolling o anclado). Por defecto, como el protocolo: esperanza en R ('expectancy_r'; también
# 't_stat_r', 'sharpe', 'profit_factor', 'net_profit' o una función) con min_trades = 30. Una ventana sin
# configuración elegible cuenta como tiempo sin posición (rendimientos diarios 0).
ws = walk_forward_windows("2022-01-01", "2026-07-01", train_months=24, test_months=6, anchored=False)
wf = walk_forward(md, "TREND_DONCHIAN", {"n": [20, 55], "k_trail": [2, 3]}, cfg, ws)
wf["windows"], wf["oos_trades"], wf["oos_metrics"]          # operaciones OOS concatenadas

# Sensibilidad en el vecindario de parámetros
param_neighbourhood(md, "REF_T0", {"adx_min": 20, "sl_atr": 1.5}, {"adx_min": [15, 20, 25], "sl_atr": [1, 1.5, 2]}, cfg)

# Bootstrap estacionario (Politis-Romano) de los rendimientos diarios
bootstrap_ci(res.daily_returns(), stat="sharpe", n_boot=2000, mean_block=10)

# Monte Carlo de la secuencia de operaciones (drawdown y rachas)
monte_carlo_trades(res.trades.r_net, n_sims=5000, risk_fraction=0.01, method="shuffle")

# Deflated Sharpe Ratio con el número de pruebas realizadas, y Holm-Bonferroni
deflated_sharpe_ratio(res.daily_returns(), n_trials=25)
holm_bonferroni([0.01, 0.04, 0.03])

# Test del mono: la estrategia frente a N entradas aleatorias con las mismas salidas y frecuencia
monkey_test(md, "REF_T0", {}, cfg, n_runs=100)

# SESSION_BREAKOUT: control de ancla aleatoria (ventana del rango aleatoria de la misma longitud, dentro de las
# 24 h previas a la ventana de entrada, sin datos futuros) y variante incondicional (sin filtro de compresión)
breakout_anchor_control(md, {"tp_mult": 2}, cfg, n_seeds=200)                    # compara con random_p95
breakout_anchor_control(md, {"tp_mult": 2}, cfg, n_seeds=200, unconditional=True)

# SESSION_DRIFT: barrido EXPLORATORIO de ventanas (solo en el rango dado); devuelve la mejor y cuántas se probaron
scan_session_windows(md, "2022-01-01", "2024-01-01", cfg.costs)   # -> table (p, p_holm), best, n_tried
```

Buenas prácticas que el motor facilita pero no impone: fijar la hipótesis, los parámetros y los criterios antes de
mirar los datos de validación; registrar **todas** las ejecuciones (también las malas) y pasar el número de
pruebas a `--n-trials`/`deflated_sharpe_ratio`; confirmar cualquier ventana del barrido en datos no usados.

### 7.1 El protocolo v5 completo en un comando (`kq.protocol`)

Aplica `MQL5/docs/PROTOCOLO_V5.md` (enmiendas 1 y 2) sin decisiones manuales: walk-forward de H3a, H2, H1 y H4, barrido H3b, controles, estudios adicionales, criterios a–k, selección y congelado.

```bash
# DEV + VAL (la reserva final no se carga)
python -m kq.protocol devval --scenario A --data KQ_XAUUSD_M1.csv --spec KQ_XAUUSD_spec.json --out runs/protoA
# Reserva final: una sola ejecución por candidata congelada
python -m kq.protocol holdout --scenario A --data KQ_XAUUSD_M1.csv --spec KQ_XAUUSD_spec.json \
    --frozen runs/protoA/frozen_candidates.json --out runs/protoA_hold
```

**Salida de `devval`**
- `REPORTE.md` (informe en español) y `report.json`;
- `frozen_candidates.json`;
- `oos_trades_<familia>.csv`;
- una línea por familia en el registro.

**Opciones:**
- Costes **en USD por onza**, convertidos con el `point` del símbolo, así que valen igual con 2 o 3 decimales:
  - `--slippage-usd` (0.03);
  - `--max-spread-usd` (0.60);
  - `--extra-spread-usd`, para datos de Dukascopy;
  - `--spread-audit KQ_<SÍMBOLO>_spread_por_hora.csv`, que añade el spread de ticks que las velas M1 no recogen.
- `--commission`, `--units-per-usd` (por defecto, según la divisa del spec), `--n-monkey` y `--n-anchor` (1 000), `--workers`.

**Comprobaciones al cargar** (si no se cumplen, se detiene):
- el valor por lote que supone el motor coincide con el del bróker;
- la hora del servidor es NY+7 según la auditoría;
- el registro no ha sido alterado.

**Etapa `holdout`:** anota cada ejecución en el registro encadenado (`record_type = holdout_lock`) antes de calcularla, y rechaza una segunda ejecución de la misma candidata. Hay que hacer *commit* del registro **y de su cabecera** (`registry/experiments.jsonl` y `registry/experiments.jsonl.head`) después de cada ejecución con datos reales, porque git es el ancla externa que impide borrar anotaciones. La etapa `holdout` se niega a arrancar si hay cambios sin commit o si `--registry` no es el registro canónico del repositorio.

**Tiempos:** con datos sintéticos del escenario A, unos 40 s con 20 simulaciones de control y unos 5–10 min con 1 000, en 4 núcleos.

**Validación con datos sintéticos:**
- con un paseo aleatorio no aprueba nada;
- con una deriva plantada detecta ventajas desde ≈ +0.09 R por operación (enmienda 2, punto 16).

## 8. Registro de experimentos

`research/registry/experiments.jsonl`: una línea JSON por ejecución con hora UTC, commit de git (y si el árbol
tenía cambios), id del experimento, id de la hipótesis, estrategia con **todos** sus parámetros, ruta + SHA-256
del CSV y del spec + rango de datos, partición, costes, configuración, especificación del símbolo y métricas.
Se abre con `O_APPEND` bajo bloqueo exclusivo (nunca se reescribe una línea) y cada línea guarda el SHA-256 de la
anterior: `kq.registry.verify_registry()` detecta cualquier edición o borrado. Las ejecuciones con datos
sintéticos de esta sesión **no** se escribieron en el registro real.

## 9. Datos sintéticos

```bash
python -m kq.synth --start 2022-01-03 --end 2026-07-01 --seed 1 --out-dir /tmp/synth   # 1 612 889 velas M1
```
GBM con innovaciones t(5), estacionalidad intradía de la volatilidad por hora UTC, regímenes de volatilidad,
regímenes de tendencia opcionales (`--trend-regime`), huecos en cada apertura diaria y de fin de semana, horario de
HF Markets (lunes–viernes 01:00–23:59 del servidor, viernes hasta 23:54), spreads que se abren mucho tras la
apertura diaria y antes de la pausa, y algunos minutos ausentes. Escribe el CSV y el spec en el formato del usuario.

## 10. Rendimiento medido (datos sintéticos, 1 612 889 velas M1, 2022-01-03 → 2026-06-30)

Máquina de esta sesión, Python 3.11, pandas 3.0, un solo hilo. Costes: comisión 7, deslizamiento 5 puntos, swap;
reglas de entrada por defecto (rollover 23:45–01:15, tope de spread 60, plazo 90 min).

| Paso | Tiempo |
|---|---|
| Leer CSV (91 MB) + SHA-256 + conversión a UTC | 5.3 s |
| Remuestrear M5/M15/H1/H4/D1 | 0.2 s |
| `REF_T0` H4 (7 031 decisiones) | 0.3 s |
| `REF_RSI2` M15 (107 823 decisiones; con ADX + H1 + trailing: 1.6 s) | 2.1 s |
| `REF_RSI2` H4 | 0.2 s |
| `TREND_DONCHIAN` H4 / D1 | 0.3 s / 0.1 s |
| `SESSION_BREAKOUT` M5 (71 492 decisiones) | 1.0 s |
| `SESSION_DRIFT` (rejilla horaria, 39 359 decisiones) | 0.5 s |
| `RANDOM_ENTRY` (objetivo T0) / T0 con `regime_gate` | 0.2 s / 0.1 s |
| `compute_metrics` (sin / con benchmarks) | 0.1 s / 0.25 s |
| `BUY_HOLD_VOLSCALED` | 0.1 s |
| CLI completa (carga + backtest + métricas + benchmarks + bootstrap + MC + archivos + registro) | ≈ 8–10 s |
| Walk-forward Donchian 4 combinaciones × 6 ventanas | 3.9 s |
| Test del mono: por ejecución aleatoria | ≈ 0.3 s |
| Control de ancla aleatoria: por semilla | ≈ 1 s |
| Barrido de ventanas horarias (2 años, 576 ventanas) | 0.2 s |
| Suite de tests (110) | ≈ 15 s |

## 11. Diferencias conocidas con el probador de estrategias de MT5

1. **Resolución M1, no ticks.** Dentro de una vela M1 no se conoce el orden de los precios: SL+TP en la misma vela
   → SL; TP con hueco → al nivel del TP. En "cada tick basado en ticks reales" MT5 puede dar resultados mejores.
2. **Spread por vela.** Se usa un único spread por vela M1 (el campo `spread` de MT5, que no refleja el máximo de
   la vela); el ask OHLC se aproxima como bid OHLC + ese spread. Los spreads reales en noticias pueden ser mayores:
   usar `--spread-floor`, `--spread-mult` y el estrés de costes.
3. **Momento de ejecución.** Se ejecuta en la apertura de la primera M1 ≥ cierre de la vela; el EA lo hace en el
   primer tick de la vela nueva (normalmente el mismo precio, salvo que el primer tick llegue tarde en ese minuto).
4. **Trailing del EA en REF_RSI2.** El EA mueve el trailing tick a tick con un paso mínimo de max(1 pip, 0.1 ATR);
   aquí solo en cierres de vela, sin paso mínimo. El chandelier de TREND_DONCHIAN sí sigue la definición del EA.
5. **Protecciones del EA no modeladas:** pérdida diaria máxima (los presets de investigación del EA la desactivan),
   bloqueo por drawdown, máximo de operaciones por día,
   comprobación de margen, lotes máximos, espera tras cerrar, filtro horario por defecto del EA (08–20) y cierre
   intradía (REF_RSI2 tiene `session_*_hour`/`close_hour` opcionales). Tampoco margen, stop-out ni `freeze_level`.
6. **Reglas de entrada:** el motor evalúa la ventana de rollover y el tope de spread con el spread de cada vela M1
   (el EA, con el spread de cada tick); la espera se resuelve a la resolución de 1 minuto.
7. **Historial de calentamiento.** Las EMAs/ADX dependen de dónde empieza el historial (semilla); MT5 usa el
   historial que tenga el terminal. Con el mismo historial los valores coinciden (fórmulas de iMA, ATR.mq5, RSI.mq5
   y ADX.mq5, este con sus búferes iniciados a 0). Exportar suficiente historial previo.
8. **Velas H4/D1 construidas desde M1.** Coinciden con las de MT5 si el M1 exportado está completo.
9. **Swap:** se usan los valores del spec para todo el periodo (como el probador, que usa los actuales); no se
   modelan festivos ni cambios de swap. Comisión cargada entera al entrar.
10. **Divisa:** se supone divisa de beneficio USD (XAUUSD) y cuenta USD o USC.
11. **El SL de un corto de SESSION_BREAKOUT** (máximo del rango, un nivel bid) se compara con el ask, así que el
    stop efectivo del corto es más estrecho que el del largo por el spread.

## 12. Paridad con el EA (reglas canónicas acordadas tras la revisión independiente)

El EA se está cambiando para seguir exactamente estas reglas; el motor ya las aplica:

1. **Rollover**: una entrada cuya ejecución cae en `[23:45, 01:15)` del servidor **no se descarta**: se **retrasa**
   a la primera M1 fuera de la ventana, siempre que siga dentro del plazo (regla 3); solo se descarta si no existe
   esa vela antes del plazo (motivo `rollover`). El primer tick del día del oro llega hacia las 01:00, dentro de la
   ventana: sin el retraso, las señales D1 (y las H4/H1 que cierran a las 00:00) no operarían nunca. El EA espera y
   entra hacia las 01:15.
2. **Tope de spread**: todas las estrategias, `max_spread_points = 60` por defecto (0 lo desactiva). Si el spread de
   la vela de ejecución supera el tope, se espera a la primera M1 posterior (antes del plazo) con spread ≤ tope; si
   no la hay, se descarta con motivo `spread`.
3. **Plazo de entrada**: una entrada pendiente vale hasta mín(fin de la vela del marco de la señal en la que se vuelve
   ejecutable, apertura de esa vela + 90 minutos). Para SESSION_DRIFT (hipótesis H3) el plazo es el final de esa
   vela H1; para M5/M15 es el final de la vela.
4. **SESSION_BREAKOUT (H2)**: el rango exige al menos el 50 % de las M1 esperadas de la ventana (210 de 420 para
   00–07 UTC); el día se marca como usado cuando se **emite** la entrada.
5. **Sin bloqueo por pérdida diaria** en las pruebas de investigación; una posición a la vez.
6. **Comisión observada**: el script de auditoría de MT5 escribe `commission_per_lot_side_observed` en negativo
   (signo de `DEAL_COMMISSION`); se usa su valor absoluto (× 2 para ida y vuelta).
7. **Cierres por señal contraria y salidas por RSI**: el EA los reintenta hasta que se ejecutan; en el motor se
   ejecutan en la apertura de la siguiente M1, como antes.
8. **Resto de reglas ya alineadas**: señales solo con velas cerradas; la señal contraria de REF_T0 cierra aunque
   ADX < 20 (el ADX solo bloquea la entrada nueva); calentamiento `Bars() < 3 × 200`; chandelier de TREND_DONCHIAN
   con el máximo HIGH / mínimo LOW de las velas cerradas desde la de entrada (incluida) y el ATR14 de la última
   vela cerrada, solo en cierres y solo estrechando; SL/TP desde el precio cotizado; tamaño por riesgo sobre el
   balance sin redondear nunca hacia arriba.
