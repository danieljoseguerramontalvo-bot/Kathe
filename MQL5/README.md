# Robot tendencial EMA 40/200 v3 – Day Trade (MetaTrader 5)

Asesor experto (EA) en MQL5: `Experts/EMA_Cross_DayTrade.mq5`. Está pensado para el
**oro (XAUUSD)**, pero funciona en cualquier símbolo.

## Qué aprendimos del primer backtest

XAUUSD M15, septiembre 2025 – septiembre 2026, SL 20 / TP 40 pips (2 / 4 USD), sin filtros:

| Dato | Resultado |
|---|---|
| Operaciones | 676 |
| Acierto | 27.2 % (compras 32.1 %, ventas 21.8 %) |
| Ganancia media / pérdida media | +4.00 / −2.11 USD |
| Factor de beneficio | 0.71 (pierde) |
| Esperanza por operación | −0.45 USD |

El Diario mostró operaciones cerradas en el stop a los **16 segundos**, **52 segundos** y
**3 minutos** de abrirse. Un stop de 2 USD está dentro del ruido normal del oro, y el
spread (≈ 0.48 USD) ya consume casi una cuarta parte del stop al entrar.

## Fundamentos de cada mejora

| Mejora | Fuente | Qué hace en el robot |
|---|---|---|
| **Stops por volatilidad (ATR)** | Curtis Faith, *Way of the Turtle*; Van K. Tharp, *Trade Your Way to Financial Freedom* | SL = ATR × 1.5, TP = ATR × 3. El stop se adapta a lo que se mueve el oro en cada momento |
| **Filtro del marco mayor** | Alexander Elder, *Trading for a Living* («triple pantalla») | En M15 solo compra si H1 está por encima de su EMA 200 y solo vende si está por debajo |
| **Filtro de fuerza de tendencia (ADX)** | J. Welles Wilder, *New Concepts in Technical Trading Systems* | No entra si el ADX es menor que 20: el mercado va de lado |
| **Trailing stop por ATR** | Chuck LeBeau («chandelier exit»); Michael Covel, *Trend Following* | El SL sigue al precio para dejar correr las ganancias |
| **Reversión RSI(2)** | Larry Connors y Cesar Alvarez, *Short Term Trading Strategies That Work* | Estrategia distinta: compra caídas extremas a favor de la tendencia. Suele acertar más, pero gana poco en cada acierto |
| **Pausa de noticias** | Práctica habitual en el oro | No abre operaciones en la franja de los datos de EE. UU. |
| **Validar sin sobreoptimizar** | Robert Pardo, *The Evaluation and Optimization of Trading Strategies* | Optimizar con prueba *forward* para no ajustar los parámetros al pasado |

### La fórmula que manda (Van Tharp)

```
Esperanza = (% acierto × ganancia media) − (% fallo × pérdida media)
```

Primer backtest: 0.272 × 4.00 − 0.728 × 2.11 = **−0.45 USD por operación**. Un sistema puede
ganar dinero acertando el 35 % si sus ganancias son el doble que sus pérdidas, y perderlo
acertando el 90 % si cada pérdida borra diez ganancias. El objetivo es una esperanza
positiva (factor de beneficio > 1), no un porcentaje de acierto alto.

## Estrategia

| Modo | Compra | Venta |
|---|---|---|
| **Solo cruce** | La EMA 40 cruza hacia arriba la EMA 200 | La EMA 40 cruza hacia abajo la EMA 200 |
| **Cruce + retrocesos** (predeterminado) | Además: con la EMA 40 sobre la EMA 200, el precio cierra bajo la EMA 40 y vuelve a cerrar por encima | Lo contrario |
| **Reversión RSI(2)** | Precio sobre la EMA 200 y RSI(2) < 10. Sale cuando el RSI > 70 | Precio bajo la EMA 200 y RSI(2) > 90. Sale cuando el RSI < 30 |

Todas las señales se confirman con **velas cerradas** y pasan por los filtros: horario,
pausa, marco mayor, ADX, spread, límites diarios y cierre intradía.

## Instalación

1. En MetaEditor, abre tu robot (o crea uno nuevo: **Archivo → Nuevo → Asesor experto**).
2. **Ctrl+A** y **Supr** para vaciarlo, pega el código **una sola vez** y compila con **F7** (`0 errors`).
3. En MT5, arrastra el robot al gráfico de **XAUUSD M15** y activa **Algo Trading**.

## Parámetros principales

| Grupo | Parámetro | Por defecto |
|---|---|---|
| Estrategia | Tipo de entrada | Cruce + retrocesos |
| | Dirección | Compras y ventas |
| Operación | Tamaño del lote | **0.01** |
| | Tipo de SL/TP | **Según la volatilidad (ATR)**: SL = ATR × 1.5, TP = ATR × 3 |
| | Stop Loss / Take Profit en pips | 20 / 40 (solo en modo «Pips fijos») |
| | Spread máximo | 8 pips |
| | Máximo de operaciones por día | 10 |
| Marco mayor | Filtro activado / marco / EMA | Sí / H1 / 200 |
| Reversión RSI | Periodo / compra / venta / salidas | 2 / 10 / 90 / 70 y 30 |
| ADX | ADX mínimo | **20** |
| Protección | Pérdida máxima diaria | 5 % |
| | Breakeven | desactivado |
| | Trailing ATR | desactivado (0) |
| Horario (servidor) | Inicio / Fin / Cierre intradía | 08:00 / 20:00 / 22:00 |
| | Pausa de noticias | desactivada (15:15 – 16:00) |

## Plan de pruebas (Probador de estrategias)

Configuración común: **XAUUSD, M15, 2025.09.01 – 2026.09.25, «Cada tick basado en ticks
reales», depósito 1000, Visualización sin marcar.** Lánzalo desde MetaTrader
(Ver → Probador de estrategias → **Empezar**), no desde MetaEditor.

El probador recuerda los valores de pruebas anteriores. En la pestaña *Parámetros de
entrada*, restablece los valores por defecto (clic derecho) o comprueba a mano que coinciden
con la tabla de arriba. Luego cambia solo lo que indica cada prueba:

| Prueba | Cambios |
|---|---|
| 1 | Nada (v3 por defecto: retrocesos + ATR + filtro H1 + ADX 20) |
| 2 | Trailing ATR = **2.0** y TP = ATR × **6** (dejar correr las ganancias) |
| 3 | Tipo de entrada = **Reversión RSI(2)**, SL = ATR × **2.5** |
| 4 | La mejor de las anteriores + Pausa de noticias = **true** |

Compara el **factor de beneficio** (tiene que ser mayor que 1), la **reducción máxima**, el
número de operaciones y el % de acierto.

### Optimización (cuando una prueba sea prometedora)

1. En *Configuración*: Optimización = **Algoritmo genético rápido**, criterio **Factor de
   beneficio máximo**, **Forward = 1/3**.
2. En *Parámetros de entrada*, marca solo 2 o 3 parámetros. Por ejemplo, multiplicador del
   SL de 1.0 a 3.0 (paso 0.5), del TP de 2 a 6 (paso 1) y ADX mínimo de 15 a 30 (paso 5).
3. Da por buenos solo los resultados que también ganan en el periodo *forward*. Si solo
   ganan en el periodo optimizado, están sobreajustados al pasado.

## Sobre el porcentaje de acierto

**Este EA no garantiza ningún porcentaje de acierto.** Los sistemas de tendencia suelen
acertar entre el 35 y el 50 % y ganan porque sus ganancias son mayores que sus pérdidas.
Los de reversión (como el RSI(2)) suelen acertar más, pero sus pérdidas son mayores que sus
ganancias. En ambos casos, lo que decide es la esperanza. Los EA que anuncian acertar el
90 % o más suelen usar martingala o stops enormes.

## Aviso de riesgo

El trading con apalancamiento conlleva un riesgo alto de pérdida. En el oro, 0.01 lotes
equivalen a 1 USD por cada dólar que se mueve el precio, y 0.5 lotes a 50 USD. Los resultados
pasados, incluidos los del backtest, no garantizan resultados futuros. Prueba siempre en
demo antes de usar dinero real.
