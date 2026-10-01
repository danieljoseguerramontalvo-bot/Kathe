# Auditoría del proyecto (2026-09-29)

Este documento consolida lo verificado hasta la fecha. Separa lo **comprobado** (con su fuente)
de lo **supuesto** y de lo **desconocido**. Es la base de la fase de investigación v5.

## 1. Fuentes inspeccionadas

| Fuente | Qué contiene | Fiabilidad |
|---|---|---|
| Historial de git de esta rama (20 commits del EA) | Todas las versiones del código, los presets y el protocolo v4 | Alta: reproducible |
| Capturas del usuario: informes del probador, pestaña Diario/Expertos, parámetros | Resultados de las pruebas en MT5, estado de la cuenta real | Media: los valores se transcriben a mano desde imágenes |
| `MQL5/PROTOCOLO.md` | Protocolo v4, resultados de las rondas 1 y 2 y de las pruebas exploratorias | Alta: escrito antes de cada ronda |

**No se ha podido inspeccionar directamente**:
- el terminal MT5 del usuario (especificaciones del contrato, historial de ticks, costes reales);
- ningún historial de precios. Este entorno no tiene MetaTrader, y la política de red bloquea todas las fuentes de datos de mercado.

## 2. Versiones reproducibles del trabajo original

| Versión | Archivo | SHA-256 | Papel |
|---|---|---|---|
| v1 | `Experts/archive/EMA_Cross_DayTrade_v1_original.mq5` | `5d2420…97879a` | Petición original: cruce EMA 40/200, 0.5 lotes |
| v3 | `Experts/archive/EMA_Cross_DayTrade_v3_referencia.mq5` | `53a674…22bbb7` | Generó el informe de +236 USD |
| v4.00 | `Experts/archive/EMA_Cross_DayTrade_v4_00.mq5` | `789b74…d8b614` | Generó **todos** los resultados de las rondas 1 y 2, y es la que está en la cuenta real |
| v4.01 | `Experts/EMA_Cross_DayTrade.mq5` | `de5712…c439189` | Corrige el defecto «market closed». No se ha compilado ni ejecutado nunca |

Los presets de cada prueba están en `Presets/`, y cada resultado cita el suyo en `PROTOCOLO.md`.

## 3. Discrepancia «EMA 40/200» frente a «RSI(2)»

**El nombre del EA no describe la estrategia que generó el informe de +236 USD.**

- La v1 era un cruce EMA 40/200 (solo compras).
- La v3 añadió en el mismo archivo una segunda estrategia independiente: la reversión RSI(2) de Connors (`InpEntryMode = 2`). Esa estrategia no usa la EMA 40.
- El informe se ejecutó con esa segunda estrategia. Lo demuestran:
  - el Diario: «Señal de VENTA: RSI(2) = 98.3 sobrecomprado con el precio bajo la EMA 200», «salida por RSI»;
  - la relación SL/TP de la venta #1012: 15.68 / 62.74 = 1/4 = ATR×1.5 / ATR×6;
  - el nombre del archivo `.ini` del probador.
- El comentario de las órdenes seguía siendo «EMA40x200». Por eso el título engaña.

## 4. Entorno: comprobado, supuesto y desconocido

| Elemento | Valor | Estado | Fuente |
|---|---|---|---|
| Bróker / servidor | HF Markets (SV) Ltd., `HFMarketsGlobal-Live20` | Comprobado | Barra de título de MT5 |
| Cuenta estándar | 261065359, **hedging**, USD, ≈ 62 USD | Comprobado (el saldo lo dice el usuario) | Barra de título, [INICIO] |
| Cuenta Cent | 261065362, **hedging**, **USC** | Comprobado | Barra de título, [INICIO] «Cuenta hedging en USC» |
| Símbolos de oro | Estándar: `XAUUSD`, `XAUUSD247`. Cent: `XAUUSDc`, `XAUUSD247c` | Comprobado | Observación del mercado |
| `XAUUSD247` | Probablemente el oro que cotiza 24/7 | **Supuesto** por el nombre | — |
| Dígitos | 2 (p. ej. 4141.04); el EA usa 1 pip = 0.10 | Comprobado | Precios, [INICIO] |
| Hora del servidor | Hora de Nueva York + 7 h: la vela diaria abre al cierre de NY; primer tick de trading hacia la 01:00; hora del PC = servidor − 7 h | Comprobado de forma indirecta | Panel (09:36 servidor / 02:36 PC), rechazos 10018 a la 01:00:00 |
| Tamaño del contrato | 100 oz/lote en la estándar | **Supuesto** (coherente con el margen de 0.5 lotes a 4 328 = 2 164.23 a 1:100) | Diario de una prueba |
| Contrato Cent | Desconocido: tamaño, lote mínimo, valor del tick en USC | **Desconocido** | — |
| Apalancamiento | Estándar: 1:100 deducido. Cent: desconocido | Deducido / desconocido | — |
| Comisión | Desconocida (el probador la aplicó según la configuración del grupo) | **Desconocido** | — |
| Swaps | Desconocidos. Según fuentes externas, la Cent de HFM no tiene swap | **Desconocido / sin verificar** | — |
| Spread | 3.4–4.8 pips (0.34–0.48 USD) observados entre las 09:36 y las 10:03 del servidor | Comprobado de forma puntual | Panel del EA |
| Historial en el probador | Barras desde 2022.01.03. Ticks reales solo desde 2026.05.29: calidad del 30 % en 2025–26 y del **0 %** en 2022–24 (ticks generados desde M1) | Comprobado | Informes |
| Historial de `XAUUSDc` | T0-H4 no abrió ninguna operación en 2022 con `XAUUSDc` (sí con `XAUUSD`). Causa sin identificar | Comprobado, sin explicar | Informe |

**Una cuenta Cent no se comporta igual que una estándar**, y su contrato hay que verificarlo; no
se puede suponer. El script `Scripts/KQ_AuditoriaEntorno.mq5` vuelca todo lo que falta:
- contrato, valor del tick, volúmenes, stops y freeze level;
- swaps, sesiones y desfase respecto a GMT;
- profundidad del historial por temporalidad;
- spread por hora;
- comisiones cobradas en operaciones pasadas.

## 5. Reproducción del informe de referencia

| Afirmación | Verificación | Resultado |
|---|---|---|
| PF 1.09 | v4.00 con `00_referencia_v3.set`, XAUUSD M15, 2025.09.01–2026.09.25, ticks reales, 1 000 USD, 1:100 | ✔ 1.09 |
| +236 USD sobre 1 000 USD | Ídem | ✔ +236.02 (balance 1 236.02), 506 operaciones, 55.3 % de acierto |
| Drawdown del 25.7 % | Ídem | ✔ 25.66 % de **equidad** (384.23 USD). El de balance fue 24.59 % |

**Reproducido exactamente**, pero **no demuestra ninguna ventaja**:
- t de la esperanza = 0.74;
- IC 95 % de la esperanza por operación = [−0.76, +1.70] USD;
- una sola operación aporta el 44 % del beneficio;
- sept–dic 2025 dio −0.53 en 161 operaciones.

## 6. ¿De qué depende el resultado?

Estimaciones con las pruebas ya hechas (detalle en `PROTOCOLO.md`):

| Factor | Evidencia | Lectura |
|---|---|---|
| **Entradas** | RSI(2) sin nada (F0, M15, 2022–24): PF 0.72, t = −5.13 | La entrada por sí sola tiene esperanza **negativa** después de costes |
| **Filtros** | F0 → F7 (H1 + ADX + trailing): PF 0.72 → 0.76 | Aportan poco |
| **Salidas** | T0 frente a T1 (trailing + TP lejano): M15 0.75 frente a 0.67; H4 1.21 frente a 0.81 | El trailing ATR×2 con TP lejano **empeora** la estrategia de tendencia |
| **Dimensionamiento** | F7 con lote fijo 0.01 frente a riesgo del 1 %: mismas señales, t −3.62 frente a −4.15 | El lote fijo del informe da más peso a las operaciones con ATR alto (la mayor ganancia es el 44 % del beneficio) |
| **Coste / temporalidad** | Mismas reglas T0: M15 PF 0.75 (−77 %), H1 0.86 (−21.5 %), H4 1.21 (+13.7 %, 2022–24) | **Los costes dominan en intradía**: cuantas más operaciones, peor |
| **Periodo (régimen)** | La ganancia de referencia viene de 2026 (+236.55); T0-H4 solo gana en 2022 | Dependencia fuerte del régimen de mercado |
| **Calidad del probador** | 30 % (2025–26) y 0 % (2022–24) | Los trailings y los stops ajustados son sensibles a los ticks generados |

Queda por medir, cuando haya datos:
- la atribución dentro de 2025–26;
- el efecto del coste real (spread por hora, comisión, swap);
- una referencia de entradas aleatorias con las mismas salidas, para separar entrada y gestión.

## 7. Situación operativa actual (a corregir)

- La **cuenta real Cent** (261065362) ejecuta la v4.00 en automático: T0 en `XAUUSDc` H4, 1 % de riesgo, drawdown máximo del 15 %.
- La nueva instrucción del usuario dice que la ejecución automática se limite al probador y a una demo habilitada, y que las cuentas reales queden en **modo señales**. Hay que **quitar el EA de la cuenta real**. La v5 lo impone por código: en una cuenta real no envía órdenes, solo señales.

Incidentes observados que la v5 debe prevenir:
1. **Dos instancias del mismo EA** (gráficos M15 y H4) con el mismo número mágico en el mismo símbolo: podrían duplicar operaciones. La v5 usará un bloqueo de instancia.
2. **Bloqueo por drawdown heredado** entre instancias o cuentas, porque la variable global no incluía el número de cuenta. La v5 lo incluirá.
3. **Rechazo 10018** («market closed») al abrir la sesión: corregido en la v4.01 y heredado por la v5.
4. **Preset no cargado** (la estrategia por defecto no era la elegida). La v5 mostrará la estrategia activa en el panel y exigirá elegirla de forma explícita.

## 8. Limitaciones de esta auditoría

- Sin MetaEditor ni MetaTrader: no se compila ni se ejecuta nada aquí.
  - Toda la compilación y los backtests de MT5 los hace el usuario.
  - Como apoyo hay un verificador estático aproximado (`tools/mql5check`), que no sustituye a MetaEditor.
- Sin datos de mercado en este entorno: la investigación cuantitativa necesita que el usuario exporte el historial (`Scripts/KQ_ExportarHistorial.mq5`) o que habilite un proveedor de datos en la configuración de red.
- Algunos resultados se tienen solo como captura del informe, sin las líneas `[RESULTADO]` (por ejemplo, H1).
