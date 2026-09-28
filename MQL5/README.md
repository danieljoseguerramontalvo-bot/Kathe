# Robot tendencial EMA 40/200 – Day Trade (MetaTrader 5)

Asesor experto (EA) en MQL5: `Experts/EMA_Cross_DayTrade.mq5`. Está pensado para el
**oro (XAUUSD)**, pero funciona en cualquier símbolo.

## Estrategia

La tendencia la marcan dos medias exponenciales: **EMA 40** (rápida) y **EMA 200** (lenta).

| Señal | Compra | Venta |
|---|---|---|
| **Cruce** (cambio de tendencia) | La EMA 40 cruza hacia arriba la EMA 200 | La EMA 40 cruza hacia abajo la EMA 200 |
| **Retroceso** (solo en el modo «Cruce + retrocesos») | Con la EMA 40 por encima de la EMA 200, el precio cierra por debajo de la EMA 40 y en la vela siguiente vuelve a cerrar por encima | Con la EMA 40 por debajo de la EMA 200, el precio cierra por encima de la EMA 40 y en la vela siguiente vuelve a cerrar por debajo |

- Todas las señales se confirman con **velas cerradas**.
- Cada señal se ejecuta solo dentro de su vela. Si no se puede operar en ese
  momento (fuera de horario, posición abierta...), se descarta y no entra tarde.
- Con «Cerrar la posición contraria» activado, una señal de venta cierra las
  compras abiertas y una de compra cierra las ventas.
- El modo «Solo cruces» es la estrategia original: opera poco (los cruces 40/200
  pueden tardar días). «Cruce + retrocesos» entra muchas más veces a favor de la tendencia.

## Instalación

1. En MetaEditor: **Archivo → Nuevo → Asesor experto (plantilla)**, ponle un nombre y pulsa Finalizar.
   Si ya tienes el robot creado, simplemente ábrelo.
2. **Ctrl+A** y **Supr** para borrar el contenido, pega el código de `EMA_Cross_DayTrade.mq5`.
3. Compila con **F7** (debe decir `0 errors`).
4. En MT5, arrastra el robot al gráfico de **XAUUSD** y activa **Algo Trading**.

## Parámetros

| Grupo | Parámetro | Por defecto | Descripción |
|---|---|---|---|
| Estrategia | Marco temporal | Actual | Temporalidad de las EMAs (M15 recomendado; M5 da más operaciones) |
| | Periodo EMA rápida / lenta | 40 / 200 | |
| | Tipo de entrada | Cruce + retrocesos | «Solo cruces» = estrategia original, pocas operaciones |
| | Dirección | Compras y ventas | También «Solo compras» o «Solo ventas» |
| | Cerrar la posición contraria | Sí | Una señal opuesta cierra la posición abierta |
| Operación | Tamaño del lote | 0.5 | Se usa si el riesgo % es 0 |
| | Riesgo por operación (%) | 0 | Si es mayor que 0, el lote se calcula para perder ese % del balance si toca el SL |
| | Stop Loss / Take Profit | 20 / 40 pips | En el oro: 2.00 / 4.00 USD de movimiento |
| | Valor de 1 pip | 0 (auto) | Automático: oro 0.1, plata 0.01, divisas 0.0001 (0.01 en pares con JPY) |
| | Spread máximo | 8 pips | Con el spread más alto, espera dentro de la vela (0 = sin límite) |
| | Deslizamiento máximo | 30 puntos | |
| | Solo una posición a la vez | Sí | |
| | Máximo de operaciones por día | 10 | 0 = sin límite |
| Protección | Pérdida máxima diaria (%) | 5 | Al llegar, cierra todo y no opera más ese día (0 = sin límite) |
| | Breakeven (pips) | 0 | Con ganancia de X pips mueve el SL a la entrada (0 = desactivado) |
| | Pips asegurados | 2 | Ganancia que deja asegurada el breakeven |
| Horario | Inicio / Fin | 08:00 / 20:00 | Hora del **servidor** del bróker |
| Días | Lunes … Domingo | L–V sí, S–D no | |
| Day trade | Cerrar todo al final del día | Sí, 22:00 | No quedan posiciones abiertas de un día para otro |
| Visualización | Panel informativo | Sí | Tendencia, horario, posiciones, resultado del día, última señal |

### Hora del servidor

Los horarios son en hora del servidor (la de «Observación del Mercado»), que puede ir
varias horas por delante o por detrás de la hora de tu PC. El panel muestra las dos
horas (servidor y PC) para que sea fácil convertir.

## Cómo probarlo (Probador de estrategias)

1. **Ver → Probador de estrategias** (Ctrl+R) y elige el robot.
2. Símbolo **XAUUSD**, **M15**, periodo de 1 año o más, modelo **«Cada tick basado en ticks reales»**.
3. **Desmarca «Visualización»**. Con la visualización activada el probador va vela a vela
   y puede parecer que no opera; sin ella, el informe completo sale en pocos minutos.
4. Revisa la pestaña **Backtest**: *Operaciones rentables (%)*, *Factor de beneficio*
   (tiene que ser mayor que 1), *Reducción máxima* y número de operaciones.
5. Antes de pasar a real, déjalo varias semanas en una **cuenta demo**.

## Sobre el porcentaje de acierto

**Este EA no garantiza ningún porcentaje de acierto**, tampoco un 92 %.

- Con SL 20 / TP 40 (relación 1:2) basta con acertar algo más del **33 %** para no
  perder, sin contar spread ni comisiones.
- En el oro, 20 pips son solo 2 USD y las velas de M15 se mueven varios dólares:
  el ruido y el spread cerrarán muchas operaciones en el SL. Prueba en el probador
  valores como 50/100 pips antes de decidir.
- Más operaciones no significa más ganancia: cada operación paga spread.
- Los EA que anuncian acertar el 90 % o más casi siempre usan un stop loss mucho
  mayor que el take profit, o martingala. Ganan poco muchas veces y, cuando
  pierden, pierden mucho.

## Aviso de riesgo

El trading con apalancamiento conlleva un riesgo alto de pérdida. En el oro,
**0.5 lotes = 50 onzas: cada dólar que se mueve el precio son 50 USD**, así que con
SL de 2 USD cada operación perdedora cuesta unos 100 USD. Los resultados pasados,
incluidos los del backtest, no garantizan resultados futuros. Usa este EA bajo tu
propia responsabilidad y pruébalo primero en demo.
