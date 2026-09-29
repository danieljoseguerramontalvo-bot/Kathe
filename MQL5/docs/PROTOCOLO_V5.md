# Protocolo de investigación v5 (prerregistrado)

**Fecha de registro:** 2026-09-29, antes de disponer de ningún dato para esta fase.

Lo que aquí se fija (hipótesis, reglas, cortes de datos, métricas, criterios y presupuesto) **no
se cambia después de ver resultados**. Cualquier cambio posterior se añade al final con fecha y
motivo. Si un experimento lo sigue, se marca como no prerregistrado.

Relación con lo anterior:
- El protocolo v4 (`../PROTOCOLO.md`) quedó cerrado sin ninguna configuración defendible.
- La v5 **no reutiliza** las familias EMA 40/200 ni RSI(2) como candidatas: solo como referencias.

## 1. Datos y contaminación

| Escenario | Fuente | Periodo | Estado |
|---|---|---|---|
| A | Exportación del MT5 del usuario (`Scripts/KQ_ExportarHistorial.mq5`), XAUUSD M1 con spread | 2022-01-03 → hoy (≈ 4.7 años) | Pendiente de que el usuario lo exporte |
| B | Proveedor externo con historial largo (por ejemplo, ticks de Dukascopy desde 2003) | ≈ 2008 → hoy | Bloqueado por la política de red del entorno; necesita que el usuario lo habilite |

Cortes cronológicos:

| Tramo | Escenario A | Escenario B | Uso |
|---|---|---|---|
| Desarrollo (DEV) | 2022-01-03 → 2024-06-30 | 2008-01-01 → 2016-12-31 | Selección de familias y parámetros, solo con walk-forward |
| Validación (VAL) | 2024-07-01 → 2025-06-30 | 2017-01-01 → 2021-12-31 | Continuación del walk-forward. Las candidatas se congelan al terminar |
| Reserva final (HOLD) | 2025-07-01 → fin | 2022-01-01 → fin | **Una sola ejecución** por candidata congelada |
| Prospectiva | Demo, desde el congelado | Ídem | Única prueba realmente no vista |

**Contaminación declarada:**
- 2022–2024 y 2025-09 → 2026-09 ya se usaron en MT5 para las familias EMA/RSI.
- Además, el equipo conoce la trayectoria general del oro: fuerte subida en 2024–2026.
- Por tanto, **ningún tramo histórico posterior a 2022 es limpio**. HOLD es «el menos contaminado» y la validación definitiva es la **prospectiva en demo**.
- En el escenario B, DEV y VAL (2008–2021) sí son limpios para todas las familias nuevas.

## 2. Modelo de costes (común a todo)

- Las velas son de precio BID. Ask = Bid + spread de la vela M1 (dato del bróker).
  - Compras: entran al Ask y salen al Bid.
  - Ventas: entran al Bid y salen al Ask.
  - Los SL y TP se disparan con el lado del precio que corresponde a cada posición.
- **Deslizamiento adicional** adverso en cada ejecución: base de 3 puntos (0.03 USD).
- **Comisión**: la que se observe en la cuenta (script de auditoría). Si no se conoce, se usa 0 en base y se cubre con el estrés.
- **Swap**: el observado. En la cuenta Cent, 0 si se confirma que no tiene swap.
- **Estrés** obligatorio: +10, +20 y +40 puntos por operación completa (0.10 / 0.20 / 0.40 USD), y el coste que anula la ventaja (*break-even cost*).
- Ejecución: la señal usa velas **cerradas** y se ejecuta en la apertura de la siguiente vela M1.
  - Si SL y TP caen dentro de la misma vela M1, se asume el SL.
  - Un hueco que salta el stop se ejecuta en la apertura de la vela.

## 3. Hipótesis (conjunto acotado)

Cada hipótesis tiene su mecanismo, dónde debería funcionar y fallar, sus reglas exactas y lo que la descarta.
Las reglas están implementadas igual en el motor Python (`research/`) y en el EA v5, para poder
contrastar ambos.

### H1. Continuación de tendencia (momentum de serie temporal)

- **Mecanismo:**
  - infrarreacción a la información y difusión lenta (flujos de bancos centrales, ETF, cobertura);
  - comportamiento de rebaño.
  - Está documentado en futuros, oro incluido: Moskowitz, Ooi y Pedersen (2012); Hurst, Ooi y Pedersen (2017).
- **Por qué sobreviviría a los costes:** los movimientos diarios o de 4 horas son de decenas de USD frente a un spread de 0.2–0.5 (< 2 % del riesgo por operación).
- **Funciona** en tendencias macro sostenidas. **Falla** en rangos laterales con rupturas falsas.
- **Reglas (`TREND_DONCHIAN`):**
  - Compra si el cierre supera el máximo de las N velas anteriores; venta, simétrica.
  - SL inicial: 2×ATR14.
  - Trailing tipo *chandelier*: 3×ATR14 desde el extremo alcanzado desde la entrada. Solo se estrecha.
  - La ruptura contraria cierra la posición y la invierte.
- **Rejilla:** N ∈ {20, 55} × TF ∈ {H4, D1} = **4 configuraciones**.
- **Se descarta si:** tras el walk-forward, la esperanza fuera de muestra es ≤ 0 después de costes, o todo el beneficio es de compras sin superar al comprar y mantener con la misma exposición.

### H2. Ruptura tras compresión en el cambio de liquidez de Londres

- **Mecanismo:**
  - la volatilidad se agrupa (clustering);
  - el rango asiático, de baja liquidez, se rompe cuando entra la liquidez de Londres y la información de la mañana europea;
  - la compresión precede a la expansión.
- **Por qué sobreviviría a los costes:** una operación al día como mucho, con riesgo igual al ancho del rango (normalmente 5–15 USD) frente a 0.3 de spread.
- **Funciona** en días de expansión direccional. **Falla** en días de rango (rupturas falsas) y con noticias que invierten el movimiento.
- **Reglas (`SESSION_BREAKOUT`):**
  - Rango: máximo y mínimo entre las 00:00 y las 07:00 UTC.
  - Filtro de compresión: se opera el día solo si ancho / ATR14 diario ≤ c_max.
  - Entrada: entre las 07:00 y las 12:00 UTC, con el cierre de una vela M5 fuera del rango ± 0.1×ancho. Como mucho una operación al día.
  - SL: el otro lado del rango.
  - TP: m×ancho.
  - Cierre forzado a las 20:00 UTC.
- **Rejilla:** c_max ∈ {0.4, sin filtro} × m ∈ {1, 2} = **4 configuraciones**.
- **Se descarta si:** la esperanza fuera de muestra es ≤ 0, o desaparece con +10 puntos de coste, o no es estable entre años.

### H3. Estacionalidad intradía (sesiones)

- **Mecanismo:**
  - flujos recurrentes por sesión (demanda física asiática, fijaciones de la LBMA, apertura de COMEX y datos de EE. UU.);
  - efectos de noche frente a día descritos en futuros.
- **Riesgo principal:** *data snooping*. Hay cientos de ventanas horarias posibles.
- **Procedimiento (`SESSION_DRIFT`):**
  - **Solo en DEV** se evalúan todas las ventanas (hora de entrada, hora de salida y dirección, de 1 a 12 h) después de costes.
  - Se elige la mejor y se registra cuántas ventanas se probaron (del orden de 550).
  - Su significación se ajusta con el *Deflated Sharpe Ratio* usando ese número de pruebas.
  - SL de protección: 3×ATR14 de H1.
- **Rejilla:** **1 configuración** seleccionada (el número de ventanas probadas cuenta para la corrección).
- **Se descarta si:** no supera el *Deflated Sharpe Ratio* ≥ 0.95, o su signo cambia en VAL o HOLD.

### H4. Reversión a la media condicionada al régimen (prioridad baja)

- **Mecanismo:**
  - provisión de liquidez tras movimientos extremos de corto plazo;
  - solo en régimen de rango, porque en tendencia la reversión pierde.
- **Evidencia previa en contra:** RSI(2) en M15 perdió en 2022–2024 (t = −5.1). Se incluye para comprobar si el **régimen** explica ese fracaso, no porque se espere que funcione.
- **Reglas:**
  - RSI(2) 10/90 con filtro EMA200. Salidas: RSI 70/30, SL 1.5×ATR14 y TP 6×ATR14.
  - Solo cuando el *efficiency ratio* diario de 20 días es menor que 0.3 (régimen de rango).
- **Rejilla:** TF ∈ {H1, H4} × filtro de régimen {sí, no} = **4 configuraciones**.
- **Se descarta si:** el filtro de régimen no convierte la esperanza en positiva fuera de muestra.

### Referencias obligatorias (no son candidatas)

| Id | Qué es | Para qué sirve |
|---|---|---|
| B0 | Comprar y mantener, y comprar y mantener con la misma exposición que cada candidata | Separar la ventaja de la simple beta alcista del oro |
| B1 | `REF_T0` (la configuración en real: EMA 40/200 H4, ADX 20, SL 1.5 / TP 3 ATR) | Contrastar el motor Python con el probador de MT5 (resultado conocido: 2022–2024, 100 operaciones, PF 1.21) |
| B2 | `REF_RSI2` (la del +236) | Ídem (conocido: F0-H4 con 230 operaciones y PF 0.96) |
| B3 | Entradas aleatorias con las mismas salidas y el mismo riesgo (1 000 semillas) | Medir cuánto aporta la entrada y cuánto la gestión |

### Estudios adicionales (solo si una familia supera el walk-forward)

- **Régimen:** la misma familia con y sin filtro de régimen, detectado solo con datos pasados:
  - tendencia o rango según el ER diario de 20 días;
  - terciles de volatilidad según el percentil del ATR de 250 días.
  - Cuenta **2 configuraciones** por familia superviviente.
- **Combinación:** si dos o más familias superan el walk-forward y la correlación de su P&L diario es < 0.5, se prueba una combinación con el mismo riesgo para cada una (**1 configuración**). Tiene que mejorar a cada componente por separado.
- **Aprendizaje automático:** excluido en el escenario A por falta de datos.
  - En el escenario B, como mucho un metaetiquetado con regresión logística de ≤ 5 variables, entrenado en walk-forward (**1 configuración**).
  - Solo se acepta si mejora la esperanza fuera de muestra en ≥ 20 % y el *Deflated Sharpe*.

## 4. Diseño de validación

1. **Walk-forward** sobre DEV y VAL:
   - ventanas deslizantes de 18 meses de entrenamiento y 6 meses de prueba (escenario A), o de 4 años y 1 año (B);
   - en cada ventana de entrenamiento se elige la configuración de la familia con mayor esperanza en R, con n ≥ 30 (el desempate lo gana la más simple);
   - las operaciones de todas las ventanas de prueba se concatenan: ese es el resultado fuera de muestra.
2. **Sensibilidad:** la tabla de configuraciones vecinas de la rejilla. Ninguna vecina puede tener esperanza ≤ 0 (sin acantilados).
3. **Costes:** estrés de +10, +20 y +40 puntos y coste de equilibrio.
4. **Desgloses:** por año, por semestre, por sesión y hora de entrada, por dirección y por régimen de volatilidad.
5. **Concentración:** el peso de las 5 mejores operaciones y de los 5 mejores días en el beneficio neto.
6. **Ablación:** quitar cada componente (filtro, trailing, régimen) y medir su aportación.
7. **Incertidumbre:**
   - *bootstrap* por bloques estacionario (Politis-Romano) sobre los rendimientos diarios, para los intervalos de la esperanza y del Sharpe;
   - Monte Carlo del orden de las operaciones, para la distribución del drawdown máximo y de las rachas de pérdidas.
8. **Número de pruebas:**
   - *Deflated Sharpe Ratio* con el número total de configuraciones registradas en todas las familias;
   - Holm-Bonferroni sobre los p-valores de las cuatro hipótesis.
9. **Prueba del mono:** la esperanza fuera de muestra debe superar el percentil 95 de B3.

## 5. Qué significa «el mejor»: criterios de aceptación

Todos con riesgo equivalente: **1 % del capital por operación** y la misma gestión de límites. Una candidata es **defendible** si cumple TODO esto:

| # | Criterio (fuera de muestra: walk-forward DEV y VAL concatenados) | Umbral |
|---|---|---|
| a | Operaciones | ≥ 100 (A) / ≥ 200 (B) |
| b | Esperanza neta en R y su t | > 0 y t ≥ 2.0 |
| c | *Deflated Sharpe Ratio* (con todas las pruebas registradas) | ≥ 0.95 |
| d | Factor de beneficio | ≥ 1.20 |
| e | Esperanza con +20 puntos de coste por operación | > 0 |
| f | Drawdown de equidad (1 % de riesgo) y percentil 95 del Monte Carlo | ≤ 20 % y ≤ 30 % |
| g | Periodos positivos | ≥ 60 % de los semestres. Ningún año aporta > 50 % del beneficio |
| h | Concentración | 5 mejores operaciones ≤ 30 % y 5 mejores días ≤ 35 % del beneficio |
| i | Vecindario de parámetros | Todas las vecinas con esperanza > 0 |
| j | Dirección | Ventas con resultado ≥ 0, o compras que superen a B0 con la misma exposición |
| k | Prueba del mono | > percentil 95 de B3 |

**Reserva final (una sola ejecución, con los parámetros congelados):** PF ≥ 1.10, esperanza > 0,
drawdown ≤ 20 % y ≥ 30 operaciones.

**Elección entre candidatas defendibles**, en este orden:
1. mayor Sharpe fuera de muestra con riesgo equivalente;
2. menor drawdown y menor tiempo de recuperación;
3. más simple (menos parámetros y componentes).

Se presentará la tabla de compensaciones:
- rentabilidad;
- drawdown;
- frecuencia;
- capital mínimo: el que hace que el lote mínimo arriesgue ≤ 1 % con el stop mediano.

**Si ninguna es defendible**, se entregan:
- la investigación;
- las causas del descarte;
- el siguiente experimento con más valor informativo.

## 6. Presupuesto de experimentos

- Candidatas: H1 4 + H2 4 + H3 1 (con ≈ 550 ventanas contadas) + H4 4 = **13 configuraciones**.
- Adicionales: régimen, combinación y aprendizaje automático, como mucho **6**.
- Referencias: B0–B3 (no compiten).
- A la reserva final llegan **como mucho 3 candidatas**, y cada una se ejecuta **una vez**.
- Todo experimento se anota en `research/registry/experiments.jsonl` (solo añadir; nunca borrar). El *Deflated Sharpe* usa el recuento total del registro.

## 7. Fase prospectiva (demo, parámetros congelados)

- **Duración:** ≥ 3 meses y ≥ 30 operaciones. Si es intradía, ≥ 60.
- **Registro del EA v5** en CSV, por operación y por señal:
  - la señal y su vela, y el precio esperado y el ejecutado;
  - el spread al entrar y al salir, el deslizamiento, la comisión y el swap;
  - los motivos de descarte y los errores.
- **Continuar** si se cumplen las tres condiciones:
  - el ≥ 95 % de las señales del backtest del mismo periodo aparecen en el registro real;
  - el deslizamiento medio es ≤ 1.5 veces el modelado;
  - la esperanza realizada en R está dentro del intervalo de predicción del 90 % del *bootstrap*.
- **Suspender** (revisión) si:
  - el drawdown supera el 10 %;
  - o, después de 30 operaciones, la esperanza en R cae por debajo del percentil 10 del *bootstrap*;
  - o hay > 5 % de señales sin ejecutar por errores.
- **Descartar** si:
  - el drawdown supera el 15 %;
  - o la esperanza en R cae por debajo del percentil 5 después de 30 operaciones;
  - o las señales divergen de forma sistemática (> 10 % de discrepancias).

## 8. Estados del sistema (para no confundirlos)

| Estado | Significado |
|---|---|
| Implementado | El código existe en el repositorio |
| Verificado estáticamente | Pasa `tools/mql5check` (aproximado, no sustituye a MetaEditor) |
| Compilado | 0 errores en MetaEditor, confirmado por el usuario con captura |
| Probado históricamente | Resultados en el motor Python y/o en el probador de MT5, en el registro |
| Evaluado fuera de muestra | Cumple la sección 5 con walk-forward y reserva final |
| Observado prospectivamente | Cumple la sección 7 en demo |

## 9. Registro de cambios del protocolo

- 2026-09-29: versión inicial.
- 2026-09-29, **enmienda 1, antes de ver ningún dato**: cambios motivados por la revisión bibliográfica (`LITERATURA.md`). Ver el apartado 10.
- 2026-09-29, **enmienda 2, antes de ver ningún dato**: detalles operativos que el texto dejaba abiertos, fijados al escribir el ejecutor `research/kq/protocol.py`. Ver el apartado 11.
- 2026-09-29, **enmienda 3, antes de ver ningún dato**: correcciones tras la revisión independiente del motor (1 bloqueante, 7 mayores y 14 menores). Ver el apartado 12.

## 10. Enmienda 1 (antes de ver ningún dato)

1. **H3 se divide en dos:**
   - **H3a, confirmatoria (1 configuración):** compra de 00:00 a 08:00 UTC (sesión asiática), con SL de protección de 3×ATR14 de H1. Se fija de antemano por la literatura (Blose y Gondhalekar 2014 y 2018; Wei 2026), así que no hay búsqueda y cuenta como una sola prueba. Es la hipótesis de **mayor prioridad en el escenario A**: da unas 1 150 observaciones diarias.
   - **H3b, exploratoria (1 configuración):** el barrido de ventanas del apartado 3, con el *Deflated Sharpe* sobre unas 550 ventanas. No puede ser candidata final si H3a no la respalda.
2. **Nueva referencia para H1: «siempre comprado» escalado por volatilidad** (Huang et al. 2020; Kim, Tse y Wald 2016).
   - Una candidata de tendencia solo se acepta si mejora su Sharpe fuera de muestra con el mismo riesgo.
   - Esto sustituye al criterio j para H1.
   - En el escenario A, H1 en D1 tendrá del orden de 20–40 operaciones, así que **no puede alcanzar el criterio a**. Se informa, pero para evaluarla hace falta el escenario B.
3. **Controles de H2:**
   - la misma mecánica con **anclas aleatorias** (rangos de igual duración en horas aleatorias del mismo día, con muchas semillas);
   - la ruptura **sin filtro de compresión**.
   - H2 solo es candidata si supera el percentil 95 de las anclas aleatorias y si el filtro de compresión mejora la esperanza en más que el coste.
   - La prioridad de H2 baja (Fetna 2026: las rupturas de apertura no sobreviven a unos 0.25 USD/oz de coste).
4. **Regla de costes común:** no se abren entradas entre las 23:45 y las 01:15 del servidor (rollover). La aplican igual el motor Python y el EA v5 (`InpRolloverFromMin` / `InpRolloverToMin`).
   - No hay filtro de noticias: el calendario económico no existe en el probador. Queda como limitación.
5. **Orden de prioridad:**
   - Escenario A: H3a > H2 > H1 (infrapotenciada) > H4.
   - Escenario B: H1 > H3a > H2 > H4.
6. **Presupuesto:** H3 pasa de 1 a 2 configuraciones (H3a + H3b). El total de candidatas es **14**. Las demás cifras del apartado 6 no cambian.

## 11. Enmienda 2 (antes de ver ningún dato): detalles operativos

El protocolo se ejecuta con un solo comando, `python -m kq.protocol devval …` (ver `research/README.md`).
El código se sube al repositorio antes de disponer de datos reales: el historial de git lo demuestra.
Lo que sigue concreta lo que el texto anterior no fijaba. No cambia hipótesis, rejillas ni umbrales.

1. **Ventanas del walk-forward.** Empiezan el 2022-01-01 (A) o el 2008-01-01 (B), para que la última ventana de prueba termine justo al final de VAL.
   - A: 4 ventanas de prueba de 6 meses, de 2023-07-01 a 2025-07-01.
   - B: 10 ventanas de 1 año, de 2012 a 2021.
   - En la etapa DEV + VAL los datos se cortan al final de VAL: la reserva final ni se carga.
2. **Selección en cada ventana:** mayor esperanza en R con ≥ 30 operaciones de entrenamiento. Los empates los gana la configuración que va antes en la rejilla, ordenada de más simple a más compleja:
   - H2: primero sin filtro;
   - H4: primero sin régimen;
   - H1: primero H4 y N = 20.
3. **Congelado:** la mejor configuración, con la misma regla, en los últimos 18 meses (A) o 4 años (B) antes del final de VAL.
4. **Deflated Sharpe (criterio c):** N = 8 configuraciones de la fase v4 + 13 de las rejillas + 1 (H3b) + 2 por cada familia con estudio de régimen + 1 si se prueba la combinación.
   - Varianza de los Sharpe bajo la hipótesis nula: la muestral del estimador.
   - H3b además usa su propio N = número de ventanas probadas en DEV.
5. **Criterio f:** drawdown de la equidad M1 encadenada de las ventanas de prueba, más el percentil 95 de 5 000 permutaciones de las R al 1 %.
6. **Criterios g y h:** en R, para que el interés compuesto no dé más peso a los años finales.
   - Solo cuentan los semestres con al menos una operación.
   - Si el beneficio total en R es ≤ 0, no se cumplen.
7. **Criterio i (vecindario):** cada configuración de la rejilla se ejecuta fija sobre todo el periodo fuera de muestra.
   - En H3a, que no tiene rejilla: una variación cada vez de la entrada (23 o 1 UTC), de la salida (7 o 9 UTC) y del SL (2 o 4 ATR).
   - Las vecinas con menos de 10 operaciones se muestran, pero no cuentan.
8. **Criterio j:**
   - H1 y H3a: Sharpe fuera de muestra mayor que el de «siempre comprado» escalado por volatilidad (enmienda 1), en el mismo periodo y con los mismos costes.
   - H2 y H4: ventas con resultado ≥ 0, o esa misma condición de Sharpe.
9. **Criterio k y controles:** se usa la configuración más elegida en las ventanas; si hay empate, la de la última ventana.
   - Se calibra la frecuencia de entrada y se hacen 1 000 simulaciones de entradas aleatorias con las mismas salidas.
   - Se exige esperanza fuera de muestra mayor que su percentil 95.
   - H2 además exige dos cosas:
     - superar el percentil 95 de 1 000 anclas aleatorias;
     - que el filtro de compresión mejore la esperanza en más que el coste de 10 puntos expresado en R.
10. **«Supera el walk-forward»** (condición para los estudios adicionales) = cumple el criterio b.
    - Régimen:
      - H1, H2 y H3a: filtro de tendencia (ER ≥ 0.3) y terciles de volatilidad medio y alto.
      - H4: terciles bajo y medio, y rango con terciles bajo y medio.
    - Como mucho 4 configuraciones, las de las 2 familias de más prioridad.
    - Combinación: media de los rendimientos diarios de las supervivientes, si su correlación absoluta máxima es < 0.5.
    - Aprendizaje automático: no se ejecuta. En B necesitaría otra enmienda antes de ver sus resultados.
11. **H1 en el escenario A** se informa, pero no puede ser candidata (infrapotenciada, enmienda 1).
12. **Holm-Bonferroni** es informativo: el umbral de significación que decide es el Deflated Sharpe.
13. **Costes con datos de Dukascopy:** el spread adicional frente a HF Markets (E puntos, del script de auditoría) se suma como deslizamiento de E/2 puntos en cada ejecución.
14. **Reserva final:** cada ejecución se anota en `research/registry/holdout_lock.jsonl` **antes** de calcular el resultado.
    - Una segunda ejecución de la misma candidata (misma estrategia y mismos parámetros) se rechaza.
    - Solo se permite con `--contaminated-rerun`, y entonces queda marcada como contaminada y no puede aprobar.
15. **Contraste con MT5 (B1 y B2):**
    - periodo 2022-01-01 → 2025-01-01;
    - sin deslizamiento adicional, sin la regla de rollover, spread máximo de 80 puntos y sin plazo de entrada, como la v4.
16. **Validación del propio ejecutor con datos sintéticos** (misma rejilla y mismos criterios, escenario A):

    | Datos | Resultado |
    |---|---|
    | Paseo aleatorio sin ventaja | Ninguna familia es defendible |
    | Deriva plantada de +0.30 USD/h de 00 a 08 UTC | H3a cumple a–k (+0.20 R por operación). H3b encuentra la ventana 00–07. Ninguna otra familia da falso positivo |
    | Deriva de +0.15 USD/h | H3a cumple a–k (+0.09 R) |
    | Deriva de +0.08 USD/h | H3a **no** es defendible (+0.04 R): falla c, g y h |

    **Potencia del escenario A:** detecta ventajas de ≈ +0.09 R por operación con unas 500 operaciones fuera de muestra. Una ventaja real más pequeña pasaría por «no defendible».

## 12. Enmienda 3 (antes de ver ningún dato): correcciones de la revisión independiente del motor

Un revisor independiente auditó `research/` contra este protocolo y contra el EA.

**Lo que confirmó correcto:**
- sin datos futuros, con prueba de perturbación;
- ejecuciones, costes, indicadores idénticos a MT5, estadística y conversión de hora.

**Lo que obligó a corregir**, sin tocar hipótesis, rejillas ni umbrales:

1. **Prueba del mono con filtro de régimen (era bloqueante).** Las entradas aleatorias no podían operar con estrategias filtradas, así que el criterio k fallaba siempre.
   - El filtro ahora delega en la estrategia que envuelve.
   - Las entradas aleatorias se enfrentan al mismo régimen que las reales.
   - Un control sin ejecuciones aleatorias detiene el proceso en lugar de fallar en silencio.
2. **Criterio k, con comparaciones homogéneas:**
   - superan el percentil 95 de las aleatorias **tanto** la esperanza del walk-forward **como** la de la configuración modal sobre el mismo periodo;
   - el control solo vale si el stop mediano de las aleatorias está entre 0.8 y 1.25 veces el real.
   - En H2, las entradas aleatorias usan la misma distancia de riesgo que una ruptura real: (1 + margen) × ancho. Con la regla del «otro lado del rango» tenían stops mucho más cortos, y una H2 perdedora pasaba k.
3. **Calentamiento del régimen:** solo se espera a los componentes que el filtro usa. El filtro de ER no espera 250 días de percentil de ATR, igual que el EA.
4. **Terciles de volatilidad idénticos en el EA y en Python:**
   - percentil del ATR diario frente a los 250 anteriores, sin incluirse, con los empates contados como 0.5;
   - tercil = mín(⌊3·p⌋, 2).
   - El EA sustituye `InpVolPctMax` por tres casillas: `InpVolAllowLow`, `InpVolAllowMid` e `InpVolAllowHigh`.
5. **Costes en USD por onza, no en puntos**, para que valgan con 2 o 3 decimales:
   - deslizamiento de 0.03 por ejecución;
   - spread máximo para entrar de 0.60, que es regla común del motor y del EA, junto con el plazo de entrada de 90 min;
   - estrés de +0.10, +0.20 y +0.40 por operación;
   - coste del filtro de H2 de 0.10;
   - contraste con MT5: spread de 0.80.
   - El EA sustituye `InpMaxSpreadPoints` e `InpSlippagePoints` por `InpMaxSpreadUsd` e `InpMaxDeviationUsd`.
   - Esto sustituye las cifras en puntos del apartado 2 y de la enmienda 2, puntos 13 y 15.
6. **Valor por lote y hora del servidor verificados al cargar.**
   - Si `contract_size × unidades` no coincide con el valor del bróker, el ejecutor se detiene. El valor del bróker es `money_per_price_unit_per_lot` de la auditoría, o `tick_value / tick_size`.
   - También se detiene si la diferencia con GMT auditada no corresponde a NY+7.
   - Por defecto, las unidades salen de la divisa de la cuenta: 100 en USC.
7. **Spread que las velas M1 no recogen:** con `--spread-audit` se suma la diferencia media por hora entre el spread de ticks y el de M1 del script de auditoría, como deslizamiento repartido entre entrada y salida.
8. **H3 sin entradas en sábado ni domingo UTC**, igual que el EA. Afecta a la vecina con entrada a las 23 UTC y al barrido H3b.
9. **Walk-forward:** una ventana sin configuración elegible cuenta como tiempo sin posición, con rendimiento diario 0, en el Sharpe y el Deflated Sharpe.
10. **Número de pruebas del Deflated Sharpe:** el mayor entre la fórmula de la enmienda 2 y las configuraciones distintas que constan en el registro (más las 8 de la v4). Así, cada nueva ejecución del protocolo, por ejemplo el escenario B tras el A, aumenta N.
11. **Registro a prueba de manipulación:**
    - cadena de hashes;
    - archivo de cabecera `experiments.jsonl.head`, que detecta borrar o editar las últimas líneas;
    - comprobación de que la versión de git es un prefijo del archivo actual;
    - identificadores únicos.
    - El bloqueo de la reserva final va **dentro** del registro (sustituye a `holdout_lock.jsonl` de la enmienda 2, punto 14).
    - Si el registro no supera la verificación, el ejecutor no arranca.
    - Hay que hacer *commit* del registro después de cada ejecución con datos reales.
12. **Motor:**
    - un movimiento de stop también se valida contra la apertura M1 en la que llega al servidor; tras un hueco, MT5 lo rechaza;
    - el comprar y mantener escalado por volatilidad redondea el lote hacia abajo;
    - un archivo sin columna `spread`, o con un modo de swap no soportado, detiene la carga.
    - `kq.run` usa por defecto deslizamiento de 3 puntos y swap. Con N = 1 etiqueta el valor como PSR, no como Deflated Sharpe.
13. **Anclas aleatorias de H2:** se toman en las 24 h anteriores a las 07:00 UTC, no «del mismo día». Con una ventana de 7 h, dentro del mismo día solo cabría la real, así que esta es la interpretación posible.
14. **R en la fase prospectiva:** se usa la definición del motor, R = neto / (lotes × valor por 1.0 de precio y lote × |precio ejecutado − SL inicial|). Se calcula con las columnas del diario del EA:
    - de `FILL`: el precio ejecutado, el SL y el volumen;
    - de `EXIT`: el neto;
    - y `money_per_price_unit_per_lot` de la auditoría.
    - La columna `r_multiple` del EA (neto / riesgo planificado) solo se informa.
15. **Sugerencia no adoptada: varianza del Deflated Sharpe de H3b.**
    - El revisor propuso usar la dispersión de los Sharpe entre las ventanas barridas. Se probó con datos sintéticos: con una deriva plantada fuerte (+0.30 USD/h), esa dispersión incluye la propia señal, y el DSR caía a 0.05. H3b no podría aprobar nunca.
    - Decide la varianza bajo H0 (todas las ventanas sin ventaja), con N = todas las ventanas, aunque estén muy correlacionadas. Eso ya es conservador en N.
    - La otra variante se informa.
    - H3b sigue sin poder ser candidata si H3a no lo es.
16. **Nueva validación con datos sintéticos, tras las correcciones:**
    - paseo aleatorio: nada aprobado;
    - derivas de +0.30 y +0.15 USD/h: H3a aprobada;
    - deriva de +0.08 USD/h: rechazada.
    - La potencia no cambia respecto a la enmienda 2.
