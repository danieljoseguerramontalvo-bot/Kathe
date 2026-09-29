# Protocolo de evaluación – Robot XAUUSD (v3 → v4)

Documento de trabajo para encontrar, **con evidencia**, una configuración defendible o
concluir que no la hay. Los criterios de aceptación se fijan aquí **antes** de ver los
resultados y no se cambian después.

## 0. Qué se ha hecho y qué no

| Hecho | No se ha podido hacer (y por qué) |
|---|---|
| Recuperar del historial de git las 5 versiones del código y archivar copias exactas de la v1 (original) y de la v3 (la que generó el informe) | **Compilar** y **ejecutar backtests**: este entorno no tiene MetaEditor ni MetaTrader, y el proxy bloquea mql5.com |
| Determinar qué estrategia y qué parámetros generaron el informe de +236 USD (a partir de las capturas del Diario y de los parámetros) | **Reproducir** el informe: hay que hacerlo en el MetaTrader del usuario (fase 0) |
| Análisis estadístico del informe de referencia | Descargar datos del oro para un backtest independiente: todas las fuentes de datos de mercado están bloqueadas |
| Implementar la v4 con los requisitos de robustez y riesgo | Verificar que la v4 compila: la última versión compilada por el usuario es la v3 |
| Diseñar el protocolo, las 13 variantes y sus archivos `.set` | |

Las comprobaciones estáticas de la v4 (paréntesis y llaves equilibrados, funciones definidas
antes de usarse, solo API estándar de MQL5, mismos parámetros que la v3) están hechas.

**Actualización 2026-09-29:** la v4 **compila sin errores** en el MetaTrader del usuario y
**reproduce exactamente** el informe de referencia: fase 1 superada (resultados en el apartado 5).

## 1. Recuperación del proyecto

### 1.1 Versiones

| Versión | Commit | Qué es | Copia |
|---|---|---|---|
| v1 | `b6b5938` | Original pedida: compra en el cruce EMA 40/200, SL 20 / TP 40 pips, 0.5 lotes | `Experts/archive/EMA_Cross_DayTrade_v1_original.mq5` |
| v2 | `72dbada` | Compras y ventas, retrocesos, pip del oro | historial de git |
| v2.1 | `6aaf471` | Stops por ATR y filtro ADX opcionales | historial de git |
| **v3** | `eb1a1bc` | Añade filtro H1, trailing ATR y **modo Reversión RSI(2)**. **Generó el informe de +236 USD** | `Experts/archive/EMA_Cross_DayTrade_v3_referencia.mq5` (SHA-256 `53a67416…bbb7`) |
| v4 | este commit | Versión robusta de este documento | `Experts/EMA_Cross_DayTrade.mq5` |

### 1.2 Dos estrategias distintas en el mismo archivo

El nombre «EMA 40/200» viene de la **estrategia A (tendencia)**. El informe de +236 USD lo
generó la **estrategia B (reversión RSI)**, que **no usa la EMA 40**. Se eligen con el
parámetro *Tipo de entrada* y se evalúan por separado.

| | Estrategia A – Tendencia | Estrategia B – Reversión RSI(2) |
|---|---|---|
| Modo (`InpEntryMode`) | 0 = solo cruce, 1 = cruce + retrocesos | 2 |
| Compra | EMA 40 cruza sobre EMA 200, o retroceso: con EMA 40 > EMA 200, cierre[2] ≤ EMA40[2] y cierre[1] > EMA40[1] | cierre[1] > EMA200[1] **y** RSI(2)[1] < 10 |
| Venta | Simétrico | cierre[1] < EMA200[1] **y** RSI(2)[1] > 90 |
| Salida propia | Señal contraria | RSI(2)[1] > 70 cierra compras; RSI(2)[1] < 30 cierra ventas (se evalúa al abrir cada vela) |

**Evidencia de que el informe es de la estrategia B.** En el Diario de la prueba aparecen
líneas como «Señal de VENTA: RSI(2) = 98.3 sobrecomprado con el precio bajo la EMA 200»,
«Trailing: SL de la posición #1012 movido a …» y «Posición #1010 cerrada: salida por RSI
(21.6 < 30.0)». En la venta #1012 (entrada 4275.89, SL 4291.57, TP 4213.15), la distancia al
SL es 15.68 y al TP 62.74. Su cociente es 4.0 = 6.0 / 1.5, lo que confirma SL = ATR × 1.5 y
TP = ATR × 6, con un ATR ≈ 10.45.

### 1.3 Configuración exacta del informe de referencia

| Elemento | Valor | Fuente |
|---|---|---|
| Bróker / servidor | HF Markets (SV) Ltd., HFMarketsGlobal-Live20 | Barra de título de MT5 |
| Tipo de cuenta | **Hedging** | Barra de título («Hedge») |
| Símbolo | XAUUSD (2 decimales; 1 pip = 0.10 para el EA) | Probador y Diario |
| Temporalidad | M15 (señales); H1 para el filtro | Probador |
| Fechas | 2025.09.01 – 2026.09.25 | Archivo `robot trade.XAUUSD.M15.20250901_20260925.400.ini` del Diario |
| Modelado | Cada tick basado en ticks reales. Calidad del historial 30 %: ticks reales solo desde 2026.05.29; antes, generados. Barras desde 2022.01.03 | Informe y Diario |
| Depósito | 1 000 USD | Informe |
| Apalancamiento | **1:100 (deducido)**: 0.5 lotes a 4 328 exigían 2 164 USD de margen = 0.5 × 100 × 4 328 / 100 | Diario de una prueba anterior |
| Retrasos, comisión | **Desconocidos** (pendiente de confirmar) | — |
| Lote | 0.01 fijo (`InpRiskPercent` = 0) | Parámetros |
| Stops | ATR(14) M15 × 1.5 (SL) y × 6 (TP) | Parámetros y Diario |
| Trailing | ATR(14) × 2 | Parámetros y Diario |
| RSI | Periodo 2; entradas 10 / 90; salidas 70 / 30 | Parámetros |
| EMA de tendencia (M15) | EMA 200 sobre el cierre | Parámetros |
| Filtro H1 | Activado, EMA 200 de H1 | Parámetros |
| ADX | **«ADX 20» = umbral mínimo 20; periodo 14** | Parámetros |
| Resto | Spread máx. 8 pips, deslizamiento 30 puntos, 1 posición, 10 operaciones/día, pérdida diaria 5 %, horario 08:00–20:00, cierre intradía 22:00, lunes a viernes | Parámetros. Del horario en adelante no se veía en la captura: **supuesto = valores por defecto** |

Archivo: `Presets/00_referencia_v3.set`.

### 1.4 Reglas exactas de la v3 en modo Reversión

1. **Evaluación**: en el primer tick de cada vela M15 nueva, con la vela 1 (la última cerrada).
2. **Filtros de entrada**, en este orden:
   - día (lunes a viernes);
   - horario [08:00, 20:00) del servidor;
   - antes del cierre intradía;
   - filtro H1;
   - pérdida diaria;
   - ADX;
   - permisos de trading;
   - una sola posición;
   - máximo diario.
3. **Filtro H1**: se compara el cierre de la última vela H1 cerrada con la EMA 200 de H1 en esa misma vela. Compras solo si el cierre está por encima; ventas solo si está por debajo.
4. **ADX**: línea principal del ADX(14) en M15 (vela cerrada) ≥ 20. No mira +DI / −DI, así que **no es direccional**: se aplica igual a compras y ventas.
5. **Ejecución**:
   - orden a mercado dentro de la misma vela, hasta 3 intentos;
   - si el spread supera 8 pips, espera dentro de la vela;
   - si la vela termina, la señal caduca.
6. **Salidas**:
   - SL o TP;
   - salida por RSI al abrir la vela siguiente;
   - señal contraria (la cierra aunque luego no se pueda abrir la nueva);
   - cierre intradía a las 22:00 o cualquier posición de un día anterior;
   - límite de pérdida diaria.
7. **Trailing**:
   - activo desde la entrada y revisado en cada tick;
   - SL candidato = Bid − 2 × ATR en compras (Ask + 2 × ATR en ventas);
   - solo se mueve si mejora el SL actual en al menos max(1 pip, 0.1 × ATR);
   - como el SL inicial es 1.5 × ATR, empieza a moverse cuando el precio ha avanzado unos 0.5 ATR a favor;
   - **nunca amplía el riesgo**.
8. **Reentrada**:
   - no hay tiempo de espera;
   - si el RSI sigue en extremo, puede volver a entrar en la vela siguiente a un stop;
   - como máximo una entrada por vela.

## 2. El resultado de referencia, analizado

| Métrica | Valor |
|---|---|
| Operaciones | 506 (280 ganadoras, 55.3 %) |
| Beneficio neto | +236.02 USD (bruto +2 844.88 / −2 608.86) |
| Factor de beneficio | 1.09 |
| Esperanza por operación | +0.47 USD |
| Ganancia media / pérdida media | +10.16 / −11.54 |
| Mayor ganancia / mayor pérdida | +103.54 / −61.13 |
| **Drawdown de balance** | 364.13 USD (24.59 %) |
| **Drawdown de equidad** | 384.23 USD (25.66 %). Es la cifra del «25.7 %» |
| Factor de recuperación | 0.61 |
| Compras / ventas | 286 (59.8 % acierto) / 220 (49.6 %) |

**Estadística** (cálculo propio con los datos del informe):

| | Valor |
|---|---|
| Desviación típica por operación | ≥ 10.8 USD (cota baja; con colas, 13–15) |
| t de la esperanza | 0.70 – 0.97 |
| p unilateral | 0.17 – 0.24 |
| IC 95 % de la esperanza por operación | de −0.47 a +1.41 USD en el mejor caso. **Incluye el cero** |
| Operaciones necesarias para confirmar una ventaja así (95 %) | ≈ 1 450 – 2 800 |
| Peso de la mayor operación | 44 % del beneficio neto (sin ella: +132) |
| Coste extra que anula la ventaja | 0.47 USD de precio por operación (≈ 4.7 pips) con 0.01 lotes |

**Cifras exactas** (líneas `[RESULTADO]` de la v4 en la fase 1, que coinciden con el informe):

| | Valor |
|---|---|
| Media / desviación típica por operación | +0.47 / 14.16 USD (n = 506) |
| t de la esperanza | **0.74** |
| IC 95 % de la esperanza por operación | de **−0.76** a **+1.70** USD |
| Operaciones necesarias para confirmar esa ventaja | ≈ 2 450 (95 % unilateral) – 3 500 (bilateral); ≈ 5 700 para t = 2.5 |
| Media con estrés de +2 pips | +0.27 USD |
| Por año | 2025 (sep–dic): **−0.53** en 161 op. · 2026: +236.55 en 345 op. |
| Mayor ganancia | 103.54 = 43.9 % del beneficio neto |

**Conclusión**: el +236 USD **no se distingue estadísticamente de cero**. Es compatible con
una estrategia sin ventaja que tuvo un buen año, y además depende mucho de una sola
operación. Por eso no se optimiza sobre él: primero se reproduce y después se contrasta
con datos que no se han usado.

La pérdida máxima de −61 USD, con un SL típico de unos 15 USD, indica un ATR muy alto en
esa entrada (≈ 40) o un salto de precio que atravesó el stop. Hay que revisarla en el
historial de operaciones de la fase 0.

## 3. Cambios de la v4

| Requisito | Implementación |
|---|---|
| Señales con velas cerradas | Todas las lecturas usan la vela 1 (EMAs, RSI, ADX, ATR) |
| Filtro H1 sin datos futuros | Se lee la última vela H1 **cerrada** por su hora de apertura (EMA y cierre de la misma vela). Exige 400 velas H1 calculadas. Si faltan datos, **espera** dentro de la vela en lugar de descartar |
| Sin entradas duplicadas | Guardia `g_lastEntryBarTime`: como máximo una entrada por vela, aunque haya reintentos o recargas |
| Solo posiciones propias | Filtro por símbolo + número mágico en todas las funciones |
| Netting / hedging | Detecta el modo. En netting fuerza una sola posición. **En netting no deben operar otros EA ni operaciones manuales en el mismo símbolo**, porque se fusionarían en una posición |
| Volumen, tick, distancias | Lote redondeado **hacia abajo** al paso; mínimo y máximo; precios al tamaño de tick; stops level al abrir y freeze level al modificar |
| SL desde la apertura | Toda orden lleva SL. Si una posición del EA aparece sin SL, se le pone. Si no se puede, **se cierra** |
| El trailing nunca amplía el riesgo | El trailing y el breakeven solo acercan el SL a favor |
| Lote por riesgo | `OrderCalcProfit` calcula la pérdida de 1 lote de la entrada al SL (incluye el spread, porque la compra entra al Ask) + comisión configurable. Si el lote mínimo supera el riesgo, **se omite la operación** |
| USD / USC | Detecta la divisa de la cuenta (o se fuerza con un parámetro). El riesgo en USD se multiplica por 100 en cuentas USC. `OrderCalcProfit` ya devuelve en la divisa de la cuenta |
| Exposición | Máximo de lotes abiertos, margen máximo por operación (% del margen libre), una posición, máximo diario |
| Pérdida diaria | Cerrado + flotante del EA ≤ X % del balance al inicio del día. Al superarlo: cierra y no opera hasta el día siguiente (hora del servidor) |
| Drawdown | Equidad de la **cuenta** frente a su máximo, guardado en variables globales del terminal (sobreviven a reinicios). Al superarlo: cierra, **bloquea** y exige reiniciar a mano con `InpResetDrawdownLock = true`. Un retiro de dinero puede activarlo: en ese caso, reiniciar |
| Registro | Etiquetas `[SEÑAL]`, `[ENTRADA]`, `[SALIDA]`, `[DESCARTE]`, `[ESPERA]`, `[RIESGO]`, `[TRAILING]`, `[ERROR]`, `[RESULTADO]` |
| Informe del probador | `OnTester` imprime operaciones, acierto, PF, esperanza, recuperación, drawdown de equidad y de balance, **t de la esperanza**, **media con estrés de costes (+2 pips)**, resultado **por año** y peso de la mayor ganancia. Devuelve el factor de recuperación (0 si hay menos de 30 operaciones) como criterio personalizado |
| Sin martingala ni grid | No existe ningún aumento de lote tras pérdidas ni órdenes escalonadas |
| Reentrada | Nuevo `InpCooldownBars` (0 = como la v3) |

**Diferencias con la v3 que pueden cambiar resultados con los mismos parámetros**: los puntos 2
y 3 de la tabla y la protección de posiciones sin SL. Por eso existe la fase 1.

## 4. Protocolo

### 4.1 Fases y periodos (cronológicos)

| Fase | Periodo | Qué se ejecuta | Para qué |
|---|---|---|---|
| ~~0. Reproducción~~ | 2025.09.01 – 2026.09.25 | **v3** + `00_referencia_v3.set`, depósito 1 000, 1:100 | **No ejecutada**: el usuario sobrescribió la v3 con la v4 en su terminal. Innecesaria: la fase 1 dio el informe original exacto, así que los datos no han cambiado |
| **1. Compatibilidad** ✔ | igual | **v4** + `00_referencia_v3.set` | Tolerancia: operaciones ±1 %, beneficio ±5 %. **Resultado: 0 % de diferencia** |
| **2. Desarrollo** | **2022.01.01 – 2024.12.31** | v4, 13 variantes (4.3) | Única fase en la que se compara y se elige |
| **3. Validación** | **2025.01.01 – 2025.08.31** | Solo 1-2 finalistas, **una vez**, sin tocar nada | Contraste fuera de muestra |
| 4. Periodo ya visto | 2025.09.01 – 2026.09.25 | Las mismas finalistas | Solo informativo: está **contaminado** porque se usó para elegir la estrategia B |
| **5. Prueba final** | Tiempo real en **demo**, ≥ 8 semanas y ≥ 60 operaciones | Configuración congelada | Único periodo realmente no visto |

**Limitación reconocida:** no queda ningún tramo histórico posterior sin usar. El periodo
2025.09 – 2026.09 ya influyó en las decisiones: el resultado de −304 USD llevó a la v3, y el de
+236 USD a la estrategia B. Por eso el desarrollo y la validación usan datos **anteriores**, y
la prueba final es prospectiva (en demo). Las EMAs 200 de M15 y de H1 necesitan unas
3 semanas de calentamiento, así que enero de 2022 casi no opera.

### 4.2 Condiciones idénticas para todas las variantes

- **Probador**: XAUUSD, M15, «Cada tick basado en ticks reales», **depósito 10 000 USD**, apalancamiento **1:100**, retrasos «Sin retrasos», visualización desactivada.
- **Parámetros comunes** (ya incluidos en los `.set`):
  - riesgo **1 %** del balance por operación (lote por `OrderCalcProfit`);
  - 1 posición y máximo 10 operaciones/día;
  - pérdida diaria 5 %;
  - margen ≤ 50 % del libre;
  - spread ≤ 8 pips;
  - horario 08–20 y cierre 22:00;
  - drawdown máximo **desactivado** (0) para no truncar las curvas;
  - reiniciar el bloqueo por drawdown = true, para que un bloqueo de una prueba anterior no afecte a la siguiente. No cambia ningún resultado.

¿Por qué 10 000 y no 1 000? Con 1 000 USD y un SL de unos 15 USD por 0.01 lotes, el 1 % (10 USD)
no llega al lote mínimo: muchas operaciones se omitirían, y más en las variantes con el SL más
ancho. La comparación quedaría sesgada. En una cuenta de 1 000 USD, 0.01 lotes equivalen a
arriesgar ≈ 1.5 % por operación.

### 4.3 Variantes (máximo 13, fijadas de antemano)

**Diseño factorial de la estrategia B.** Responde si el trailing, el filtro H1 y el ADX
aportan algo frente a la misma estrategia sin ellos:

| Archivo | Trailing ATR 2 | Filtro H1 | ADX ≥ 20 |
|---|---|---|---|
| `F0_rsi_base` | – | – | – |
| `F1_rsi_trailing` | ✔ | – | – |
| `F2_rsi_h1` | – | ✔ | – |
| `F3_rsi_trailing_h1` | ✔ | ✔ | – |
| `F4_rsi_adx` | – | – | ✔ |
| `F5_rsi_trailing_adx` | ✔ | – | ✔ |
| `F6_rsi_h1_adx` | – | ✔ | ✔ |
| `F7_rsi_completo` (= referencia) | ✔ | ✔ | ✔ |

Efecto de un componente = PF medio de las 4 variantes que lo tienen − PF medio de las 4 que
no lo tienen (y lo mismo con la esperanza y el drawdown).

**Sensibilidad** alrededor de la referencia, para ver si hay un pico aislado:

| Archivo | Cambio respecto a F7 |
|---|---|
| `S1_rsi_completo_sl25` | SL = ATR × 2.5 |
| `S2_rsi_completo_5_95` | RSI 5 / 95 |
| `S3_rsi_completo_15_85` | RSI 15 / 85 |

**Estrategia A (tendencia)**, evaluada aparte:

| Archivo | Configuración |
|---|---|
| `T0_tendencia_retrocesos` | Cruce + retrocesos, SL ATR × 1.5, TP ATR × 3, H1, ADX 20, sin trailing |
| `T1_tendencia_trailing` | T0 con trailing ATR × 2 y TP ATR × 6 |

No se usa el optimizador en esta ronda. Con 13 variantes ya hay riesgo de elegir la mejor por
azar; el criterio t ≥ 2.5 lo compensa.

### 4.4 Métricas y criterios de aceptación

La variante elegida debe cumplir **todo** esto en **desarrollo**:

| # | Criterio | Umbral |
|---|---|---|
| a | Operaciones | ≥ 300 |
| b | Factor de beneficio | ≥ 1.15 |
| c | t de la esperanza (`[RESULTADO] Por operación`) | ≥ 2.5 |
| d | Esperanza con estrés de +2 pips por operación | > 0 |
| e | Drawdown relativo de equidad | ≤ 20 % |
| f | Factor de recuperación (3 años) | ≥ 2.0 |
| g | Años con resultado positivo | ≥ 2 de 3 |
| h | Mayor ganancia / beneficio neto | ≤ 20 % |
| i | Si es F7: S1, S2 y S3 con PF ≥ 1.0 | sin «acantilados» |

Y en **validación**: PF ≥ 1.05, esperanza > 0, drawdown de equidad ≤ 20 % y ≥ 60 operaciones.

**Reglas de decisión:**

1. Un componente (trailing, H1, ADX) solo se mantiene si su efecto mejora el PF en ≥ 0.05 y lo hace en al menos 2 de los 3 años. Si no, se quita: lo más simple gana.
2. Entre las variantes que cumplen a-h, se elige la **más simple** cuyo PF esté a menos de 0.05 del mejor, no la que más dinero gana.
3. Si **ninguna** cumple, la conclusión es que **no hay configuración defendible** y no se opera en real. Cualquier idea nueva necesitaría datos nuevos (la demo).
4. En demo se detiene la prueba si el drawdown supera el 15 % o si el comportamiento no coincide con el del probador (señales, salidas, errores).

### 4.5 Presupuesto de cálculo

| Pruebas | Tiempo aproximado |
|---|---|
| 13 × desarrollo (3 años) | 5-10 min cada una |
| 2 × reproducción y compatibilidad | ≈ 2 min cada una |
| ≤ 2 × validación | ≈ 1 min cada una |
| Opcional: 2 × finalistas con modelado «1 minuto OHLC» | Para ver cuánto dependen los resultados del modelado de ticks |
| **Total** | **1.5 – 2.5 horas** |

Tope: **19 ejecuciones**. No se añaden variantes después de ver resultados.

### 4.6 Limitaciones

- **Calidad de datos**: los ticks de 2022 a mayo de 2026 son generados. El trailing y los stops ajustados son sensibles al modelado.
- **Probador ≠ real**: faltan deslizamiento real, ensanchamiento del spread en noticias, recotizaciones y la comisión, que es desconocida.
- **Régimen de mercado**: el oro subió con fuerza de 2022 a 2026. Que las compras acierten más puede no repetirse.
- **Potencia estadística**: con una ventaja como la del informe hacen falta más de 1 400 operaciones para confirmarla.

## 5. Plantilla de resultados

Copiar los datos del informe (pestaña Backtest) y de las líneas `[RESULTADO]` del Diario:

| Variante | Periodo | Oper. | Acierto | PF | Esperanza | t | Esperanza estrés | DD equidad % | Recuperación | Años + | Mayor ganancia % | ¿Cumple? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 00 (v3) | Informe original | 506 | 55.3 % | 1.09 | 0.47 | – | – | 25.66 | 0.61 | – | 44 | referencia |
| 00 (v4) | Compatibilidad | 506 | 55.3 % | 1.09 | 0.47 | 0.74 | 0.27 | 25.66 | 0.61 | 1 de 2 | 43.9 | ✔ idéntico |
| F7 con lote fijo 0.01 (*) | Desarrollo | 1 483 | 49.0 % | 0.79 | −0.33 | **−3.62** | −0.53 | 5.48 | −0.88 | **0 de 3** | – | ✘ falla b, c, d, f y g |
| **F7** (`.set`, riesgo 1 %) | Desarrollo | 1 482 | 48.9 % | 0.76 | −5.37 | **−4.15** | −8.80 | **82.02** | −0.96 | **0 de 3** | – | ✘ falla b, c, d, e, f y g |
| **F0** (†) | Desarrollo | 1 905 | 49.1 % | 0.72 | −4.84 | **−5.13** | −7.32 | **92.62** | −0.97 | **0 de 3** | – | ✘ falla b, c, d, e, f y g |
| **T0** (‡) | Desarrollo | 989 | 31.4 % | 0.75 | −7.83 | **−3.90** | −10.74 | **79.20** | −0.97 | **0 de 3** | – | ✘ falla b, c, d, e, f y g |
| **T1** | Desarrollo | 1 024 | 31.8 % | 0.67 | −7.87 | **−4.43** | −10.66 | **81.74** | −0.98 | **0 de 3** | – | ✘ falla b, c, d, e, f y g |
| F1 … F6, S1 … S3 | Desarrollo | no ejecutadas: ver la conclusión de la ronda 1 | | | | | | | | | | |

(‡) Identificada por el modo «Tendencia: cruces + retrocesos», TP = 2 × SL (ATR 3 / 1.5) y la
ausencia de trailing. Por año: 2022 −3 982.63 (321 op.), 2023 −2 653.62 (358 op.), 2024
−1 111.68 (310 op.). Balance final 2 252.07. Gana 72.96 de media y pierde 44.89: una relación
de 1.63, por debajo del 2 teórico por el spread y las salidas anticipadas. Con un 31.4 % de acierto no llega al punto
de equilibrio.

(†) El usuario no indicó el archivo. Se identifica como F0 porque es el primero de la lista, no
tiene líneas de trailing y hace más operaciones que F7 (sin filtros). La relación SL/TP es la
del modo ATR 1.5/6. Por año: 2022 −5 149.69 (605 op.), 2023 −3 201.08 (686 op.), 2024 −876.53
(614 op.). Balance final 772.70.

**Lectura de F0 frente a F7:** la entrada RSI(2) sola pierde (t = −5.13). Los tres componentes
juntos apenas la mejoran: PF 0.72 → 0.76. F1-F6 son combinaciones intermedias entre esos dos
extremos, así que es muy improbable que alguna llegue a PF ≥ 1.15 y t ≥ +2.5. Se da
prioridad a T0 y T1 (estrategia A, independiente). F1-F6 quedan como opcionales para completar
el análisis factorial.

**F7 con su archivo** (riesgo 1 % sobre 10 000):
- Por año: 2022 −2 887.67 (459 op.), 2023 −3 938.81 (535 op.), 2024 −1 137.68 (488 op.).
- Balance final 2 035.84: **pierde el 80 % de la cuenta**.
- El drawdown de 82 % se ve porque el drawdown máximo está desactivado (0) en las pruebas. Con el valor por defecto de la v4 (20 %), el EA se habría bloqueado al perder un 20 % desde el máximo.
- La configuración de referencia queda **descartada**. S1-S3 solo sirven para el criterio i, que se aplica si se elige F7, así que ya no deciden nada.

(*) Se ejecutó sin cargar `F7_rsi_completo.set`: son los parámetros de la referencia (trailing,
H1, ADX 20, RSI 10/90) con lote fijo 0.01 en vez del 1 % de riesgo. Las señales y las salidas
son las mismas que en F7. Solo cambia el tamaño de las operaciones, y con él el límite de
pérdida diaria. Por año: 2022 −92.87 (459 op.), 2023 −230.05 (536 op.), 2024 −160.43 (488 op.).
Beneficio neto −483.35 sobre 10 000. Calidad del historial 0 %: todos los ticks son generados
a partir de barras de 1 minuto. Con t = −3.62, la configuración de referencia **pierde de forma
estadísticamente significativa** en datos no vistos: en cada operación pierde algo más que el spread. Hay que
repetir F7 con su archivo para que las 13 variantes tengan condiciones idénticas.

Otros datos de la fase 1: beneficio neto +236.02, balance final 1 236.02, drawdown de balance
364.13 (24.59 %). Las operaciones y los precios del Diario coinciden con los de la v3. Por ejemplo, la venta
#1012: entrada 4275.89, SL 4291.57, TP 4213.15, riesgo al SL 15.68 USD, salida por RSI a 4263.57.

**Prueba adicional (no planificada):** la misma configuración con el drawdown máximo al 20 %,
que es el valor por defecto de la v4:
- Hasta julio de 2026 las operaciones son idénticas: 2025 da −0.53 en 161 operaciones, como en la fase 1.
- En julio de 2026 la equidad cayó un 20.01 % desde su máximo (≈ 1 497) y el EA se bloqueó, como estaba previsto.
- Total: 409 operaciones, +197.69, drawdown de equidad 299.57 (20.01 %). Las 97 operaciones restantes no se abrieron.
- Sin la protección, esa caída llegó al 25.66 %.

## 6. Conclusión de la ronda 1 (M15)

**Ninguna variante cumple los criterios.** Las cuatro ejecutadas pierden en 2022, 2023 y 2024:

| Variante | Estrategia | Balance final (de 10 000) | t | Pérdida por operación (≈ pips) |
|---|---|---|---|---|
| F7 | RSI(2) con trailing, H1 y ADX (la del +236) | 2 035.84 | −4.15 | 3.1 |
| F0 | RSI(2) sin nada | 772.70 | −5.13 | 3.9 |
| T0 | Tendencia EMA 40/200, TP 3 ATR | 2 252.07 | −3.90 | 5.4 |
| T1 | Tendencia EMA 40/200, trailing y TP 6 ATR | 1 942.94 | −4.43 | 5.6 |

- La pérdida en pips sale de la prueba de estrés: 2 pips más de coste por operación bajan la media en una cantidad conocida.
- Un SL típico en M15 a final de 2024 es 1.5 × ATR ≈ 3.2–3.6 de precio (32–36 pips). Perder 3–6 pips por operación es un 10–17 % del riesgo. Es del tamaño de uno o dos spreads.
- **Las entradas no muestran ninguna ventaja medible, y el coste de cada operación decide el resultado.**

F1–F6 y S1–S3 no se ejecutaron. Los dos extremos del diseño factorial, F0 (ningún componente) y
F7 (los tres), dan PF 0.72 y 0.76, y ninguno se acerca a 1.15. S1–S3 solo servían para el
criterio i, que se aplica si se elige F7. Ejecutarlas añadiría comparaciones sin posibilidad de
cambiar la decisión.

Por la regla 3, **ninguna configuración de la ronda 1 es defendible**: no se opera en real ni en demo.

## 7. Ronda 2 (fijada antes de ejecutarla): las mismas reglas en H4

**Hipótesis.** Las pérdidas en M15 se deben sobre todo a que el coste es grande frente a un
stop pequeño. En H4 el ATR es unas 4 veces mayor, así que el mismo spread pesa unas 4 veces
menos por unidad de riesgo. Se repiten las reglas sin cambiarlas: solo cambia la temporalidad.

| Archivo | Reglas |
|---|---|
| `R2_H4_F0_rsi` | F0 en H4 |
| `R2_H4_T0_tendencia` | T0 en H4, sin filtro H1 porque es un marco menor |
| `R2_H4_T1_tendencia_trailing` | T1 en H4, sin filtro H1 |

**Condiciones.** Las del apartado 4.2, con estas diferencias:
- `InpTimeframe` = H4: el archivo lo fija, así que el gráfico del probador puede quedarse en M15;
- sin horario;
- sin cierre intradía: las posiciones duran días, y el probador aplica swaps (los actuales) y huecos de fin de semana.

Periodo: 2022.01.01–2024.12.31. El calentamiento son 600 velas H4, así que las señales empiezan
hacia mayo de 2022.

**Criterios en desarrollo** (menos operaciones que en M15, así que se exige más ventaja por operación):

| # | Criterio | Umbral |
|---|---|---|
| a | Operaciones | ≥ 60 |
| b | Factor de beneficio | ≥ 1.3 |
| c | t de la esperanza | ≥ 2.0 |
| d | Esperanza con estrés de +2 pips | > 0 |
| e | Drawdown de equidad | ≤ 25 % |
| f | Factor de recuperación | ≥ 2.0 |
| g | Años positivos | ≥ 2 de 3 (2022 incompleto cuenta) |
| h | Mayor ganancia / beneficio neto | ≤ 25 % |

**Contexto.** El oro subió de ≈ 1 830 a ≈ 2 620 entre finales de 2021 y finales de 2024 (≈ +43 %).
Una estrategia de tendencia puede ganar solo por ir comprada. Se anota el acierto de las compras
y de las ventas (pestaña Backtest) para verlo.

**Validación:** 2025.01.01–2025.08.31, solo las que cumplan a–h, una vez. Debe dar PF ≥ 1.1 y
beneficio neto > 0. Después, demo durante 3 meses como mínimo.

**Regla de cierre:** si ninguna cumple a–h, el proyecto termina con esta conclusión. Con estos
indicadores (EMA 40/200, RSI(2), ATR, ADX) no hay un robot defendible para el oro ni en M15 ni en H4,
y no se opera con dinero real. No habrá ronda 3 con estos mismos datos.

Presupuesto: 3 pruebas de desarrollo y ≤ 2 de validación.

| Variante | Oper. | Acierto | PF | Esperanza | t | Estrés | DD equidad % | Recuperación | Años + | Mayor ganancia % | ¿Cumple? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2_H4_F0_rsi | 230 | 57.4 % | 0.96 | −1.36 | −0.25 | −2.69 | 10.46 | −0.28 | 1 de 3 | – | ✘ falla b, c, d, f y g |
| R2_H4_T0_tendencia | 100 | 40.0 % | 1.21 | 13.70 | 0.89 | 12.15 | 13.32 | 0.81 | 1 de 3 | 16.5 | ✘ falla b, c, f y g |
| R2_H4_T1_tendencia_trailing | 107 | 36.4 % | 0.81 | −8.47 | −1.09 | −11.02 | 17.57 | −0.48 | 1 de 3 | – | ✘ falla b, c, d, f y g |

**R2_H4_T0_tendencia:**
- Resultado: beneficio neto +1 370.05 (balance final 11 370.05). Drawdown de balance 1 654.16 (13.13 %).
- Compras: 55 (47.3 % de acierto). Ventas: 45 (31.1 %).
- Por año: 2022 **+1 964.32** (30 op.), 2023 −181.02 (35 op.), 2024 **−413.25** (35 op.). Todo el beneficio viene de 2022.
- En 2024 pierde aunque el oro subió con fuerza ese año.
- Pasar a H4 elimina la sangría de costes: de −77 % en M15 a +13.7 %. Aun así, t = 0.89 **no se distingue de cero**.

**R2_H4_T1_tendencia_trailing:**
- Resultado: beneficio neto −906.82 (balance final 9 093.18).
- Compras: 60 (43.3 % de acierto). Ventas: 47 (27.7 %).
- Por año: 2022 +228.77 (31 op.), 2023 −476.27 (39 op.), 2024 −782.24 (36 op.).
- `[RESULTADO] Por operación` cuenta 106 operaciones: la última la cerró el probador al terminar la prueba.
- Con trailing y TP lejano sale peor que T0 en H4: PF 0.81 frente a 1.21.
- Las dos variantes de tendencia solo ganan en 2022 y pierden en 2023 y 2024, cuando el oro subió con más fuerza. Las ventas aciertan poco (28–31 %).

**R2_H4_F0_rsi:**
- Resultado: beneficio neto −311.73 (balance final 9 688.27).
- Compras: 143 (55.2 % de acierto). Ventas: 87 (60.9 %).
- Por año: 2022 +245.73 (79 op.), 2023 −101.24 (83 op.), 2024 −456.22 (68 op.).
- Acierta el 57 % y aun así pierde: gana 61.15 de media y pierde 85.55.

### 7.1 Conclusión de la ronda 2 y del protocolo

**Ninguna variante cumple a–h.** En H4 los costes dejan de hundir los resultados, que pasan de
−77 % / −92 % a entre −9 % y +14 %. Pero ninguna tiene una ventaja que se distinga del azar:
- t entre −1.09 y +0.89;
- las tres ganan solo en 2022 y pierden en 2023 y en 2024.

La mejor, R2_H4_T0 (+13.7 %, PF 1.21), tampoco está cerca: le falta más de una unidad de t y
tiene dos de tres años negativos.

Referencia: comprar y mantener oro en el mismo periodo daba ≈ +43 % (≈ 1 830 → ≈ 2 620).
Ninguna variante se acerca.

Por la regla de cierre fijada de antemano, **el proyecto termina aquí**:
- con EMA 40/200, RSI(2), ATR y ADX no hay un robot defendible para XAUUSD, ni en M15 ni en H4;
- no se opera con dinero real;
- no se hace una ronda 3 con estos datos.

Para una idea nueva ya no quedan datos históricos limpios: 2022–2024 y 2025.09–2026.09 ya se han
usado, y solo queda 2025.01–2025.08, que son unas 8 semanas de H4. Habría que evaluarla en demo,
hacia delante.

El defecto de «market closed» no cambia esta conclusión, así que no se repitieron las pruebas.
Aunque recuperase las señales perdidas de la primera vela del día (≈ 1 de cada 6), no podría
hacer positivos 2023 y 2024 ni llevar la t de 0.89 a 2.0. Se corrige igualmente en la v4.01 (apartado 7.2).

**Defecto de ejecución encontrado.**
- En la primera vela H4 del día, el primer tick llega a la 01:00:00, antes de que abra la sesión de trading.
- Los 3 intentos fallan en el mismo segundo con el código 10018 («market closed») y la señal se descarta. Ejemplo: 2024.12.19 01:00, venta por cruce bajista.
- Afecta por igual a las 3 variantes de la ronda 2. En M15 no ocurría porque el horario 08–20 lo evitaba.
- Se corrige después de la ronda 2: esperar dentro de la vela mientras la sesión esté cerrada, sin gastar intentos.
- Si alguna variante queda cerca de los criterios, se repiten las 3 con el código corregido.

### 7.2 Corrección v4.01

- `IsTradeSessionOpen` consulta las sesiones de trading del símbolo (`SymbolInfoSessionTrade`). Mientras la sesión esté cerrada, `MarketConditions` devuelve «esperar dentro de la vela».
- Si aun así el servidor responde 10018 (`TRADE_RETCODE_MARKET_CLOSED`), no cuenta como intento: se reintenta dentro de la misma vela al cabo de 60 segundos.
- Ningún resultado de este documento usa la v4.01. Todos se obtuvieron con la v4.00.

### 7.3 Prueba exploratoria fuera del protocolo: T0 en H1

**Por qué.** El usuario quiere operaciones casi diarias. T0 en H4 hace unas 3–4 al mes; en H1
serían unas 3–4 por semana.

**Cómo.** Es `R2_H4_T0_tendencia.set` con «Marco temporal de las señales» = H1. Mismo periodo
(2022–2024), 10 000 USD, riesgo 1 %.

**Qué puede decidir.** Esta prueba usa unos datos ya vistos muchas veces. Por eso **solo puede descartar**:
- si pierde o no cumple los criterios de la ronda 1 (a–h), H1 queda descartado y se sigue con H4;
- si los cumple, tampoco demuestra nada por sí sola: habría que probarla hacia delante, en demo o en la cuenta Cent, antes de sustituir a H4.

Criterios fijados antes de ejecutarla: los del apartado 4.4 (a–h).

## 8. Datos pendientes del usuario

1. Apalancamiento, retrasos y divisa del depósito usados en la prueba de +236 USD (se deduce 1:100).
2. Tipo de cuenta real en HF Markets (Premium, Zero, Pro, cent…), divisa (USD o USC), comisión por lote y balance aproximado.
3. Si acepta la demo de ≥ 8 semanas como prueba final.
