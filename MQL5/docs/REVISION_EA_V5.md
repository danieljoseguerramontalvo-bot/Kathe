# Revisión cruzada del EA v5 (2026-09-29)

Revisión independiente, hecha por un subagente, de `Experts/KatheQuant_v5.mq5` y de los dos scripts. Cubrió tres
papeles: desarrollador de MQL5 (compilación), especialista en ejecución y responsable de riesgo. Se hizo leyendo el
código, **sin compilar**.

## Resultado

- **Compilación:** no encontró errores. Todas las firmas de la API y los nombres de constantes coinciden con MQL5. Falta la confirmación en MetaEditor.
- **Seguridad en cuentas reales:** se revisaron todos los caminos que envían órdenes y todos dependen de `g_auto`. En cuentas reales no se puede enviar ninguna orden.
- **Señales:** ninguna usa datos futuros. El lote nunca se redondea hacia arriba, el SL siempre está presente y el trailing solo se estrecha.

## Hallazgos y correcciones

| # | Gravedad | Hallazgo | Corrección aplicada |
|---|---|---|---|
| 1 | Mayor | El bloqueo de instancia no era atómico: dos copias podían sacar el mismo identificador | Identificador por gráfico (`ChartID`), variable temporal y `GlobalVariableSetOnCondition` (comparación y escritura atómicas). El latido comprueba la propiedad del bloqueo y, si se pierde, el EA se detiene. `EntryGate` exige tener el bloqueo |
| 2 | Mayor | El estado persistente no se guardaba en disco hasta cerrar el terminal | `GlobalVariablesFlush()` tras cada cambio crítico, y cada 60 s en `OnTimer` |
| 3 | Mayor | Las salidas por vela (H3, RSI, señal contraria) se intentaban una sola vez | H3 sale por reloj en cada tick. Nueva cola de cierres con reintentos cada 10 s. La nueva entrada espera a que se complete el cierre |
| 4 | Mayor | El rollover se aplicaba distinto: el EA esperaba y Python descartaba | Regla canónica: **esperar** a salir de la franja, dentro del plazo de la señal. Se pidió el cambio en el motor Python |
| 5 | Mayor | En H2, el intento del día se marcaba al ejecutarse en el EA, pero al emitirse en Python | El EA lo marca al **emitir** la señal |
| 6 | Mayor | La demo podía funcionar sin límites de riesgo, y el reinicio de bloqueos se repetía en cada recarga | En demo automática, el drawdown máximo y la pérdida diaria son obligatorios. El reinicio de bloqueos se aplica una sola vez. La guía obliga a partir de `KQ5_DEMO_plantilla.set` |
| 7 | Menor | Resultado diario arrastrado al cambiar de día | Se reinicia con el día |
| 8 | Menor | Riesgo de duplicar o piramidar posiciones | Se elimina `InpMaxPositions` (siempre una posición). Antes de reintentar se comprueba si la orden anterior llegó a ejecutarse |
| 9 | Menor | Señales pendientes que desaparecían sin quedar en el diario | Se registra «caducada» antes de evaluar una vela nueva |
| 10 | Menor | Sin retraso máximo de entrada | Nuevo `InpMaxEntryDelayMin` (90 min desde la apertura de la vela) |
| 11 | Menor | Cierres fallidos reintentados en cada tick | Esperas de 10 s en `EnsureStops`, `BreakoutFlat` y `DriftExitTick` |
| 12 | Menor | En netting, una posición ajena en el símbolo | La entrada se descarta |
| 13 | Menor | Huecos en el diario | Filas `FILL` (precio real del deal), `EXIT` con el nivel esperado de SL/TP (`DEAL_SL`/`DEAL_TP`), columnas de comisión y swap, filas `ERROR`. Diario del probador reescrito en cada prueba y desactivado al optimizar. Renovación de las variables de riesgo de las posiciones abiertas |
| 14 | Menor | El estrés de `OnTester` estaba en puntos | Estrés en precio (0.10 / 0.20 / 0.40 por onza) y coste de equilibrio. Las operaciones con resultado 0 ya no cuentan como pérdida |
| 15 | Menor | Estado heredado entre pruebas del probador | Se borran las variables globales al empezar cada prueba |
| 16 | Menor | Diferencias de parámetros entre el EA y Python | Los presets de investigación desactivan el drawdown y la pérdida diaria. Se pidió a Python aplicar el mismo tope de spread (60 puntos), el mismo plazo de entrada y el mismo mínimo de datos del rango H2 |
| 17 | Menor | H2 podía saltarse el día si el historial aún se estaba sincronizando | Espera a que el historial esté sincronizado antes de marcar el día como sin datos |
| 18 | Menor | Guardia de seguridad adicional | `OrdersAllowedNow()` al inicio de `SendMarket`, `ClosePositionTicket` y `ModifyStops` |
| 19 | Menor | El estado era compartido entre estrategias y temporalidades | El estado de estrategia usa un prefijo propio (estrategia y temporalidad). Los bloqueos siguen siendo por cuenta, símbolo y número mágico |
| 20 | Menor | `SERIES_SYNCHRONIZED` era innecesario en `SeriesReady` | Eliminado |
| 21 | Menor | Script de exportación | No exporta la vela en curso. Espera a conocer la primera fecha del historial. No insiste si no hay historial (4401). Avisa si el máximo de barras es insuficiente |
| 22 | Menor | Script de auditoría | Reintenta la sincronización de ticks. Funciones auxiliares renombradas (`Dbl`, `Int`, `Tm`). La comisión observada tiene signo negativo |

**Límite conocido:** las variables globales son de cada terminal. Dos terminales distintos (por ejemplo, el PC y un VPS) en la misma cuenta no se ven entre sí. No hay que hacerlo.
