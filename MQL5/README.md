# Robot XAUUSD v4 – Tendencia EMA 40/200 y Reversión RSI(2) (MetaTrader 5)

| Archivo | Qué es |
|---|---|
| `Experts/EMA_Cross_DayTrade.mq5` | **v4**: la versión actual |
| `Experts/archive/EMA_Cross_DayTrade_v3_referencia.mq5` | v3 exacta, la que generó el informe de +236 USD. **Solo para reproducirlo** |
| `Experts/archive/EMA_Cross_DayTrade_v1_original.mq5` | Versión original pedida (compra en el cruce EMA 40/200) |
| `Presets/*.set` | Parámetros de la referencia y de las 13 variantes del protocolo |
| `PROTOCOLO.md` | Recuperación del proyecto, análisis del informe, protocolo de pruebas y criterios de aceptación |

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

## Aviso de riesgo

El trading con apalancamiento conlleva un riesgo alto de pérdida. Ningún backtest garantiza
resultados futuros, y este EA no promete ninguna rentabilidad ni porcentaje de acierto.
