# Robot XAUUSD – investigación v5 (MetaTrader 5)

> **Estado (2026-09-29):**
> - Las rondas v4 terminaron **sin ninguna configuración defendible**.
> - La v5 reabre la investigación con un protocolo prerregistrado (`docs/PROTOCOLO_V5.md`) y un motor de ejecución nuevo, KatheQuant v5.
> - **Ningún sistema de este repositorio ha demostrado todavía una ventaja estadística.**

## Estructura

| Archivo | Qué es |
|---|---|
| `Experts/KatheQuant_v5.mq5` | **v5**: motor modular. En cuentas reales **solo emite señales**; opera en automático solo en el probador o en una demo habilitada |
| `Scripts/KQ_AuditoriaEntorno.mq5` | Vuelca especificaciones, sesiones, spreads, comisiones e historial disponible (solo lectura) |
| `Scripts/KQ_ExportarHistorial.mq5` | Exporta velas con spread a CSV para el motor de investigación en Python (solo lectura) |
| `Presets/v5/*.set` | Una configuración por hipótesis prerregistrada, más la referencia T0 para contrastar con la v4 |
| `docs/AUDITORIA.md` | Auditoría del trabajo existente: qué está comprobado, qué es supuesto y qué es desconocido |
| `docs/LITERATURA.md` | Revisión bibliográfica, con sus fuentes |
| `docs/PROTOCOLO_V5.md` | Hipótesis, costes, cortes de datos, criterios, presupuesto y fase de demo, fijados **antes** de ver datos |
| `docs/INSTALACION_Y_DEMO.md` | Instalación, exportación de datos, contraste v5 frente a v4 y fase prospectiva en demo |
| `../research/` | Motor de investigación en Python (backtest con costes bid/ask, walk-forward y registro de experimentos) |
| `Experts/EMA_Cross_DayTrade.mq5` | v4.01 (histórica; no usar en real) |
| `Experts/archive/` | Copias exactas de la v1, la v3 (la del +236) y la v4.00 (la que produjo todos los resultados registrados) |
| `Presets/*.set`, `PROTOCOLO.md` | Protocolo y presets de la v4 (cerrado) |

---

# Histórico: robot v4 – Tendencia EMA 40/200 y Reversión RSI(2)

## Dos estrategias, no una

- **A – Tendencia (EMA 40/200)**: entra en el cruce de las medias o en los retrocesos a la EMA 40 a favor de la tendencia.
- **B – Reversión RSI(2)** (Connors): compra con RSI(2) < 10 si el precio está sobre la EMA 200 y vende con RSI(2) > 90 si está debajo. Sale cuando el RSI vuelve a 70 / 30. **No usa la EMA 40.**

El informe de +236 USD (XAUUSD M15, sept 2025 – sept 2026) es de la **estrategia B**, con SL ATR × 1.5,
TP ATR × 6, trailing ATR × 2, filtro H1 (EMA 200) y ADX(14) ≥ 20. El análisis de `PROTOCOLO.md`
muestra que ese resultado **no es estadísticamente distinguible de cero**. Los valores por defecto de
la v4 reproducen esa configuración como **hipótesis a validar**, no como configuración probada.

## Qué añade la v4

- Lote calculado por **riesgo** con `OrderCalcProfit`: % del balance o importe en USD, con cuentas USD y USC. Si el lote mínimo supera el riesgo, **no opera**.
- Límites de **exposición** (lotes, margen, posiciones), **pérdida diaria** y **drawdown** de la cuenta, este último con bloqueo persistente.
- **Filtro H1** leído por la hora de la última vela H1 cerrada, sin datos futuros.
- Guardia contra **entradas duplicadas** en una vela.
- Toda posición tiene **SL**: si falta, se añade o se cierra la posición.
- El trailing y el breakeven **nunca amplían el riesgo** y respetan el freeze level.
- Compatible con cuentas **hedging y netting** (en netting, una sola posición y sin otros EA en el símbolo).
- **Registro** con etiquetas.
- `OnTester` imprime en el Diario la t de la esperanza, el resultado por año y una prueba de estrés de costes.
- Sin martingala, grid ni aumentos de lote tras pérdidas.

La v4 conserva **todos los parámetros de la v3** con los mismos nombres, así que
`Presets/00_referencia_v3.set` funciona en las dos versiones.

## Instalación

1. Mantén la v3 que ya tienes (por ejemplo, «robot trade») **sin tocarla**: sirve para reproducir el informe.
2. Crea un asesor nuevo (por ejemplo, «robot oro v4») y pega el contenido de `Experts/EMA_Cross_DayTrade.mq5`. Compila con F7.
3. Copia los `.set` de `Presets/` a la carpeta de datos de MT5: `MQL5/Profiles/Tester/`.
4. Para usarlos, ve a la pestaña *Parámetros de entrada* del probador → clic derecho → **Cargar**.

## Cómo evaluarlo

Sigue `PROTOCOLO.md`:
1. reproducción con la v3;
2. compatibilidad con la v4;
3. 13 variantes en 2022-2024;
4. validación en 2025.01-2025.08;
5. demo.

Los criterios de aceptación están fijados de antemano. Si ninguna variante los cumple, la
conclusión es no operar en real.

## Resultado de la evaluación (2026-09-29)

El protocolo se ejecutó completo. **Ninguna configuración cumple los criterios.** Periodo:
2022–2024, datos que no se usaron para diseñar las estrategias.

| Ronda | Qué se probó | Resultado |
|---|---|---|
| 1 (M15) | La configuración del +236 (F7), RSI(2) solo (F0), tendencia EMA 40/200 (T0, T1) | Pierden entre el 77 % y el 92 % de la cuenta, en los tres años (t de −3.9 a −5.1). Pierden 3–6 pips por operación, más o menos el coste del spread |
| 2 (H4) | Las mismas reglas en velas de 4 horas | Entre −9 % y +14 %, sin ventaja distinguible del azar (t ≤ 0.89). Las tres ganan solo en 2022 y pierden en 2023 y 2024 |

**Conclusión: no usar este EA con dinero real.** El código se deja como herramienta de prueba.

El usuario decidió operarlo igualmente con la mejor variante (T0 en H4, +13.7 % en 2022–2024,
pero t = 0.89 y pérdidas en 2023 y 2024). Para eso está `Presets/LIVE_H4_T0_tendencia.set`,
con estas protecciones:
- riesgo del 1 % por operación;
- drawdown máximo del 15 % con bloqueo persistente (la peor caída en la prueba fue del 13.3 %);
- pérdida diaria máxima del 5 %;
- registro de descartes y panel activados.

Se recomienda ejecutarlo primero en demo.
Tiene gestión de riesgo, protecciones y el informe estadístico en `OnTester`, y sirve para
evaluar otras ideas con el mismo método. El detalle está en `PROTOCOLO.md`, apartados 5 a 7.

## Aviso de riesgo

El trading con apalancamiento conlleva un riesgo alto de pérdida. Ningún backtest garantiza
resultados futuros, y este EA no promete ninguna rentabilidad ni porcentaje de acierto.
