# EMA Cross 40/200 – Day Trade (MetaTrader 5)

Asesor experto (EA) en MQL5: `Experts/EMA_Cross_DayTrade.mq5`.

## Estrategia

- Cuando la **EMA 40** cruza **hacia arriba** la **EMA 200**, abre una **compra**.
- Por defecto: **0.5 lotes**, **stop loss de 20 pips** y **take profit de 40 pips**.
- El cruce se confirma con **velas cerradas**: compara la última vela cerrada con
  la anterior. Así no se opera un cruce que aparece y desaparece dentro de la vela.
- Cada cruce genera **una sola señal**. Si en ese momento no se puede operar
  (fuera de horario, día desactivado, posición ya abierta...), la señal se descarta
  y el EA no entra más tarde con un precio peor.

## Instalación

1. En MetaTrader 5: **Archivo → Abrir carpeta de datos**.
2. Copia `EMA_Cross_DayTrade.mq5` en `MQL5/Experts/`.
3. Ábrelo en MetaEditor (F4) y compílalo (F7).
4. En MT5, arrastra el EA al gráfico y activa **Algo Trading**.

## Parámetros

| Grupo | Parámetro | Por defecto | Descripción |
|---|---|---|---|
| Estrategia | Marco temporal de las EMAs | Actual | Temporalidad de las EMAs (se recomienda M5 o M15 para day trade) |
| | Periodo EMA rápida / lenta | 40 / 200 | Periodos de las medias |
| | Precio aplicado | Cierre | Precio usado para calcular las EMAs |
| Operación | Tamaño del lote | 0.5 | Se ajusta al paso de lote del símbolo |
| | Stop Loss / Take Profit | 20 / 40 pips | Distancia desde el precio de entrada |
| | Valor de 1 pip | 0 (auto) | Ver la sección «Pips» |
| | Spread máximo | 3 pips | Con el spread más alto, espera dentro de la misma vela (0 = sin límite) |
| | Deslizamiento máximo | 10 puntos | Desviación de precio aceptada al ejecutar |
| | Solo una posición a la vez | Sí | No abre otra compra si ya hay una abierta |
| | Máximo de operaciones por día | 0 | 0 = sin límite |
| | Número mágico | 4020040 | Identifica las operaciones de este EA |
| Horario | Activar filtro de horario | Sí | Hora del **servidor del bróker** (la que muestra la Observación de Mercado) |
| | Inicio / Fin | 08:00 / 20:00 | Si el inicio es igual al fin, opera todo el día; si el inicio es mayor que el fin, el horario cruza la medianoche |
| Días | Lunes … Domingo | L–V sí, S–D no | Días en los que puede abrir operaciones |
| Day trade | Cerrar todo al final del día | Sí | Cierra las posiciones del EA a la hora indicada |
| | Hora de cierre | 22:00 | Después de esa hora ya no abre operaciones ese día |
| Visualización | Panel informativo | Sí | Muestra en el gráfico las EMAs, el horario, el spread y las posiciones abiertas |

### Day trade

Con **«Cerrar todo al final del día»** activado, ninguna posición queda abierta de
un día para otro. A la hora de cierre el EA cierra todas sus posiciones de ese
símbolo. Si alguna viene de un día anterior (por ejemplo, porque el mercado estaba
cerrado a la hora de cierre), la cierra en el primer tick que reciba.

### Pips

En modo automático, 1 pip = 10 puntos en cotizaciones de 5 y 3 decimales
(EURUSD 1.08125, USDJPY 151.235) y 1 punto en las de 4 y 2 decimales.

En **oro, índices y criptomonedas** cada bróker define el pip de forma distinta.
Ahí conviene fijar el valor a mano en **«Valor de 1 pip en precio»**. Por ejemplo,
`0.1` en XAUUSD hace que 20 pips sean 2.00 USD de movimiento.

### Cuentas netting

En cuentas *netting* MT5 solo admite una posición por símbolo. Si desactivas
«Solo una posición a la vez», las compras nuevas se suman a la posición existente
y reemplazan su SL y su TP.

## Cómo probarlo (Probador de estrategias)

1. **Ver → Probador de estrategias** (Ctrl+R) y elige `EMA_Cross_DayTrade`.
2. Símbolo y temporalidad (p. ej. EURUSD M15), modelo **«Cada tick basado en ticks reales»**.
3. Usa un periodo largo (2 años o más) y revisa el informe: *Operaciones rentables (%)*,
   *Factor de beneficio*, *Reducción máxima* y el número de operaciones.
4. Antes de pasar a real, déjalo varias semanas en una **cuenta demo**.

## Sobre el porcentaje de acierto

**Este EA no garantiza un 92 % de acierto.** Ningún sistema puede prometer un
porcentaje fijo, y con estos parámetros ese número es muy poco probable:

- Con SL 20 / TP 40 (relación 1:2) basta con acertar algo más del **33 %** para no
  perder, sin contar spread ni comisiones. Los cruces de medias de este tipo suelen
  quedar muy por debajo del 92 %.
- Los EA que muestran porcentajes de acierto del 90 % o más casi siempre usan un
  stop loss mucho mayor que el take profit, o martingala. Ganan muchas veces poco
  y, cuando pierden, pierden mucho.

Lo que de verdad importa es la **esperanza matemática** (factor de beneficio por
encima de 1 con un drawdown aceptable), medida en tu bróker, tu símbolo y tu
temporalidad con el probador de estrategias.

## Aviso de riesgo

El trading con apalancamiento conlleva un riesgo alto de pérdida. Los resultados
pasados, incluidos los del backtest, no garantizan resultados futuros. Usa este
EA bajo tu propia responsabilidad y pruébalo primero en demo.
